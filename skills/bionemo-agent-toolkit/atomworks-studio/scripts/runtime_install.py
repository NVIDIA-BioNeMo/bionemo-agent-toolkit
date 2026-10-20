"""Candidate locked replacement for upstream native dependency installation.

Call only inside the managed runtime setup reservation/execution lock. This
module is not wired into production setup until Linux qualification succeeds.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
from runtime_bootstrap import bootstrap
from runtime_download import fetch

PROFILE=json.loads(Path(__file__).with_name('runtime_install_profile.json').read_text())
LOCK=Path(__file__).with_name('runtime_dependencies.lock')


def verify_toolchain(*, run=subprocess.run, which=shutil.which):
    """Reject an incomplete native build host before downloading dependencies."""
    paths={name:which(name) for name in ('gcc','g++','nvcc')}
    if not paths['nvcc']:
        paths['nvcc']=which('/usr/local/cuda-13.2/bin/nvcc')
    missing=[name for name,path in paths.items() if not path]
    if missing:
        raise ValueError('Native runtime setup requires compiler prerequisites: '+', '.join(missing))
    versions={}
    for name,path in paths.items():
        versions[name]=run([path,'--version'],check=True,capture_output=True,text=True,timeout=15).stdout.strip()
    # This recipe builds against the CUDA 13.2 PyTorch distribution.
    if 'release 13.2,' not in versions['nvcc']:
        raise ValueError('Native runtime setup requires CUDA compiler 13.2')
    return {'paths':paths,'versions':versions}


def scaffold(model):
    """Preserve the pinned upstream setup's minimal runtime scaffolding."""
    model=Path(model)
    script=(model/'scripts/setup_venv.sh').read_text()
    start=script.index("<< 'EOF'\n")+len("<< 'EOF'\n")
    content=script[start:script.index('\nEOF',start)]+'\n'
    expected=json.loads(Path(__file__).with_name('runtime_recipe.json').read_text())['generated_source_hashes']
    relative='configs/metrics/custom_metrics/all_custom_metrics.yaml'
    if hashlib.sha256(content.encode()).hexdigest()!=expected[relative]:
        raise ValueError('Upstream metrics scaffold differs from pinned recipe')
    destination=model/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or destination.read_bytes()!=content.encode():
            raise ValueError('Existing metrics scaffold differs from pinned recipe')
    else:
        with destination.open('x') as handle:handle.write(content)
    for relative in ('src/rfproteina/metrics/custom_metrics','src/rfproteina/transforms/sampling'):
        (model/relative).mkdir(parents=True,exist_ok=True)
    env=model/'.env.local'
    if not env.exists() and not env.is_symlink() and not (model/'.env').exists():
        descriptor=os.open(env,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as handle:handle.write((model/'.env.local.example').read_bytes())


def install(root, *, profile=PROFILE, run=subprocess.run, download=fetch, pass_fds=()):
    root=Path(root).resolve();model=root/'model';tools=root/'bootstrap'
    if hashlib.sha256(LOCK.read_bytes()).hexdigest()!=profile['lock_sha256']:
        raise ValueError('Dependency lock checksum mismatch')
    toolchain=verify_toolchain(run=run)
    uv=bootstrap(tools,profile['uv'],download)
    env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(tools/'python'),UV_CACHE_DIR=str(tools/'cache'),
             PYTHONDONTWRITEBYTECODE='1',TMOL_FORCE_BUILD='1')
    # Do not inherit user/global uv resolver configuration or arbitrary indexes.
    for key in list(env):
        if key.startswith(('UV_INDEX','UV_EXTRA_INDEX','UV_DEFAULT_INDEX','UV_CONSTRAINT','UV_OVERRIDE','PIP_')):
            del env[key]
    compiler_paths=toolchain['paths']
    cuda_home=str(Path(compiler_paths['nvcc']).resolve().parent.parent)
    env.update(CC=compiler_paths['gcc'],CXX=compiler_paths['g++'],CUDACXX=compiler_paths['nvcc'],
               CUDA_HOME=cuda_home,CUDA_PATH=cuda_home)
    env['PATH']=str(Path(compiler_paths['nvcc']).parent)+os.pathsep+env.get('PATH',os.defpath)
    def command(args, **kwargs):
        return run([str(uv),'--no-config',*args],cwd=model,env=env,check=True,pass_fds=pass_fds,**kwargs)
    command(['python','install',profile['python']['key']])
    python=model/'.venv/bin/python'
    if not python.exists():command(['venv','--python',profile['python']['key'],str(model/'.venv')])
    version=run([str(python),'-c','import platform; print(platform.python_version())'],capture_output=True,text=True,check=True).stdout.strip()
    if version!=profile['python']['version']:raise ValueError('Existing environment has a different Python version')
    command(['pip','sync','--python',str(python),'--require-hashes','--build-constraints',str(LOCK),
             '--torch-backend','cu132',str(LOCK)])
    source=tools/'tmol-0.1.59.tar.gz'
    download(profile['tmol']['url'],source,profile['tmol'])
    command(['pip','install','--python',str(python),'--no-deps','--no-build-isolation',str(source)])
    scaffold(model)
    command(['pip','install','--python',str(python),'--no-deps','--no-build-isolation','-e',str(model)])
    command(['pip','check','--python',str(python)])
    installed=json.loads(run([str(python),'-c',
        'import importlib.metadata,json; print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version for d in importlib.metadata.distributions()}))'],
        check=True,capture_output=True,text=True).stdout)
    expected=dict(profile['packages'],tmol='0.1.59')
    mismatches={name:installed.get(name.lower().replace('_','-')) for name,version in expected.items()
                if installed.get(name.lower().replace('_','-'))!=version}
    if mismatches:raise ValueError('Installed dependency versions differ from the pinned profile: '+json.dumps(mismatches))
    return {'toolchain':toolchain,'python':version,'packages':installed,'lock_sha256':profile['lock_sha256']}

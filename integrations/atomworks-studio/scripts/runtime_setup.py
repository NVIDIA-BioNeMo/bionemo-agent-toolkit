"""Install Studio's pinned runtime on the selected host, then verify and sample.

Run with the same absolute runtime/output roots supplied to check_named_target.
This explicit CLI does not provision machines, change drivers or install OS packages.
"""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile

from public_model_bundle import download_bundle, manifest
from runtime_download import fetch, valid
from runtime_recipe import RECIPE, inspect, runtime_overrides
from source_integrity import verify_source
from source_stage import stage

PROFILE=json.loads(Path(__file__).with_name('runtime_install_profile.json').read_text())
LOCK=Path(__file__).with_name('runtime_dependencies.lock')


def bootstrap(directory, spec, download=fetch):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    wheel=directory/'uv-bootstrap.whl'
    download(spec['url'],wheel,{'sha256':spec['digests']['sha256'],'size':spec['size']})
    if not valid(wheel,{'sha256':spec['digests']['sha256'],'size':spec['size']}):
        raise ValueError('Bootstrap wheel does not match the pinned release')
    executable=directory/'uv'
    expected={'sha256':spec['binary_sha256'],'size':spec['binary_size']}
    if executable.is_symlink():raise ValueError('Bootstrap executable cannot be a symlink')
    if valid(executable,expected):
        executable.chmod(0o700)
        return executable
    with zipfile.ZipFile(wheel) as archive:
        matches=[entry for entry in archive.infolist() if entry.filename==spec['binary_member']]
        if len(matches)!=1 or matches[0].file_size!=spec['binary_size']:
            raise ValueError('Bootstrap wheel member is missing, duplicated or has an unexpected size')
        payload=archive.read(matches[0])
    if hashlib.sha256(payload).hexdigest()!=spec['binary_sha256']:
        raise ValueError('Bootstrap executable checksum mismatch')
    fd,name=tempfile.mkstemp(prefix='.uv-',dir=directory)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(payload);out.flush();os.fsync(out.fileno())
        os.chmod(name,0o700)
        os.replace(name,executable)
        fd=os.open(directory,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if os.path.exists(name):os.unlink(name)
    return executable


# Locked public-release dependency installation.
#
# Invoked explicitly on the user's selected host; no machine lifecycle actions.
#
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
    if profile.get('install_mode') != 'public_wheels':
        raise ValueError('Unsupported runtime installation mode')
    uv=bootstrap(tools,profile['uv'],download)
    env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(tools/'python'),UV_CACHE_DIR=str(tools/'cache'),
             PYTHONDONTWRITEBYTECODE='1')
    # Do not inherit user/global uv resolver configuration or arbitrary indexes.
    for key in list(env):
        if key.startswith(('UV_INDEX','UV_EXTRA_INDEX','UV_DEFAULT_INDEX','UV_CONSTRAINT','UV_OVERRIDE','PIP_')):
            del env[key]
    # tmol's CUDA operations use reviewed public wheels; no compiler or sudo is needed.
    env.pop('TMOL_FORCE_BUILD', None)
    def command(args, **kwargs):
        return run([str(uv),'--no-config',*args],cwd=model,env=env,check=True,pass_fds=pass_fds,**kwargs)
    command(['python','install',profile['python']['key']])
    python=model/'.venv/bin/python'
    if not python.exists():command(['venv','--python',profile['python']['key'],str(model/'.venv')])
    version=run([str(python),'-c','import platform; print(platform.python_version())'],capture_output=True,text=True,check=True).stdout.strip()
    if version!=profile['python']['version']:raise ValueError('Existing environment has a different Python version')
    command(['pip','sync','--python',str(python),'--require-hashes','--build-constraints',str(LOCK),
             '--torch-backend','cu132','--only-binary','tmol,tmol-ops-cu13',str(LOCK)])
    scaffold(model)
    command(['pip','install','--python',str(python),'--no-deps','--no-build-isolation','-e',str(model)])
    command(['pip','check','--python',str(python)])
    installed=json.loads(run([str(python),'-c',
        'import importlib.metadata,json; print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version for d in importlib.metadata.distributions()}))'],
        check=True,capture_output=True,text=True).stdout)
    expected=profile['packages']
    mismatches={name:installed.get(name.lower().replace('_','-')) for name,version in expected.items()
                if installed.get(name.lower().replace('_','-'))!=version}
    if mismatches:raise ValueError('Installed dependency versions differ from the pinned profile: '+json.dumps(mismatches))
    return {'install_mode':profile['install_mode'],'python':version,'packages':installed,'lock_sha256':profile['lock_sha256']}


# Representative upstream short-monomer inference and structure validation.
VALIDATE = r'''import hashlib,json,sys
from pathlib import Path
import numpy as np
from biotite.structure.io.pdbx import CIFFile,get_structure
root=Path(sys.argv[1]).resolve(); evidence=[]
samples=root/'inference_samples'
if samples.is_symlink():raise ValueError('Smoke sample directory cannot be a symlink')
for path in sorted(samples.rglob('*.cif')):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Smoke output escapes its run directory')
    atoms=get_structure(CIFFile.read(path),model=1)
    if len(atoms)==0 or not np.isfinite(atoms.coord).all():
        raise ValueError('Smoke output lacks finite atomic coordinates')
    evidence.append({'path':str(path.relative_to(root)),'atoms':len(atoms),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
if not evidence:raise ValueError('Smoke inference produced no CIF structures')
print(json.dumps({'structures':evidence}))
'''


def smoke(root, run=subprocess.run, pass_fds=()):
    root=Path(root);model=root/'model'
    parent=root/'setup-smoke';parent.mkdir(exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='monomer-short-',dir=parent))
    args=[str(model/'.venv/bin/rfd4-generate'),'inputs=data/benchmarks/monomer',
          'subset_to_examples=monomer-short','num_replicates=1','batch_size=1',
          'seed=42','compile_lengths=null','out_dir='+str(output),'hydra.run.dir='+str(output/'hydra')] + runtime_overrides(str(root))
    run(args,cwd=model,check=True,pass_fds=pass_fds,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',DATA_PATH=str(model/'data_path'),HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1'))
    result=json.loads(run([str(model/'.venv/bin/python'),'-B','-c',VALIDATE,str(output)],check=True,capture_output=True,text=True).stdout)
    if not isinstance(result.get('structures'),list) or not result['structures']:
        raise ValueError('Smoke inference returned no validated structures')
    return {'example':'monomer-short','output_dir':str(output),'command':args,**result}


def host_preflight(run=subprocess.run):
    """Reject known incompatible hosts before large downloads; no driver changes."""
    if platform.system() != RECIPE['platform'] or platform.machine() != RECIPE['architecture']:
        raise ValueError('Studio runtime requires Linux x86_64')
    libc, version = platform.libc_ver()
    if libc != 'glibc' or tuple(map(int, version.split('.')[:2])) < (2, 28):
        raise ValueError('Studio runtime requires glibc 2.28 or newer')
    result = run(['nvidia-smi', '--query-gpu=driver_version,memory.total',
                  '--format=csv,noheader,nounits'], check=True, capture_output=True, text=True, timeout=30)
    devices = [line.split(',') for line in result.stdout.splitlines() if line.strip()]
    if not devices or any(int(driver.strip().split('.')[0]) < 580 for driver, memory in devices):
        raise ValueError('CUDA 13 wheels require NVIDIA driver 580 or newer; select a compatible image or review a driver upgrade')
    if not any(float(memory.strip()) * 1024**2 >= RECIPE['minimum_gpu_memory_bytes'] for driver, memory in devices):
        raise ValueError('Studio runtime requires a GPU with at least 75 GiB; multiple smaller GPUs do not satisfy this requirement')


def readiness(root, run=subprocess.run):
    """Use exactly the same nine checks as check_named_target."""
    cfg = {'remote_root': str(root), 'weight_paths': [str(root / 'model-bundle' / item['name'])
                                                   for item in RECIPE['model_bundle']['files']]}
    class LocalProbe:
        def target_exec(self, cfg, command, timeout=300):
            import shlex
            return run(shlex.split(command), check=True, capture_output=True, text=True,
                       timeout=timeout, cwd=root / 'model',
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')).stdout
    result = inspect(LocalProbe(), cfg)
    if not all(result['checks'].values()):
        raise ValueError('Studio runtime not ready: ' + ', '.join(k for k, v in result['checks'].items() if not v))
    return result


def setup(root, output_root, *, run=subprocess.run, download=fetch):
    """Install under shared setup/execution locks, preserving existing runs."""
    root = Path(root).expanduser().absolute()
    output_root = Path(output_root).expanduser().absolute()
    for path in (root, output_root):
        if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Use absolute roots without symlinks or parent traversal')
    if output_root.is_relative_to(root / 'model') or output_root.is_relative_to(root / 'model-bundle'):
        raise ValueError('Output root must be separate from model source and weights')
    host_preflight(run)
    if PROFILE['packages'] | {'rfd4-proteina': '0.0.1'} != RECIPE['packages']:
        raise ValueError('Installer dependencies differ from Studio readiness recipe')
    if PROFILE['lock_sha256'] != RECIPE['dependency_lock_sha256'] or manifest() != RECIPE['model_bundle']:
        raise ValueError('Installer lock or model bundle differs from Studio readiness recipe')
    root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        locks = []
        for path in (root / '.rfd4-setup.lock', output_root / '.rfd4-execution.lock'):
            lock = stack.enter_context(path.open('a'))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Runtime setup or a design is active; setup refused') from None
            locks.append(lock.fileno())
        print('Staging pinned model source', flush=True)
        model = stage(root, RECIPE, run=run)
        print('Installing locked Python dependencies', flush=True)
        install(root, run=run, download=download, pass_fds=tuple(locks))
        print('Downloading and verifying public model bundle', flush=True)
        download_bundle(root / 'model-bundle')
        verify_source(model, RECIPE['model_revision'], RECIPE.get('generated_source_hashes'))
        checks = readiness(root, run)
        print('All nine Studio checks passed; running short-monomer smoke test', flush=True)
        evidence = smoke(root, run, tuple(locks))
    return {'ready': True, 'runtime_root': str(root), 'output_root': str(output_root),
            'readiness': checks, 'smoke': evidence}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--output-root', required=True, type=Path,
                        help='Use the same output root as Studio so setup cannot modify an active run')
    parser.add_argument('--check', action='store_true', help='Only run Studio readiness; no installation or sampling')
    args = parser.parse_args(argv)
    try:
        for path in (args.runtime_root, args.output_root):
            if not path.is_absolute() or '..' in path.parts:
                raise ValueError('Runtime and output roots must be absolute paths without parent traversal')
        result = readiness(args.runtime_root) if args.check else setup(args.runtime_root, args.output_root)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('SETUP FAILED: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

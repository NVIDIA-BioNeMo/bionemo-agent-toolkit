# Extract one checksum-pinned uv executable; never execute an install shell script.
import hashlib
import os
from pathlib import Path
import tempfile
import zipfile
from runtime_download import fetch, valid


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
# Call only inside the managed runtime setup reservation/execution lock. This
# profile remains unqualified until Linux GPU acceptance succeeds.
#
import json
import subprocess
import shutil

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
from runtime_recipe import runtime_overrides

VALIDATE = r'''import hashlib,json,sys
from pathlib import Path
import numpy as np
from biotite.structure.io.pdbx import CIFFile,get_structure
root=Path(sys.argv[1]).resolve(); evidence=[]
for path in sorted(root.rglob('*.cif')):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Smoke output escapes its run directory')
    atoms=get_structure(CIFFile.read(path),model=1)
    if len(atoms)==0 or not np.isfinite(atoms.coord).all():
        raise ValueError('Smoke output lacks finite atomic coordinates')
    evidence.append({'path':str(path.relative_to(root)),'atoms':len(atoms),'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
if not evidence:raise ValueError('Smoke inference produced no CIF structures')
print(json.dumps({'structures':evidence}))
'''


def smoke(root, run, lock_fd):
    root=Path(root);model=root/'model'
    parent=root/'setup-smoke';parent.mkdir(exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='monomer-short-',dir=parent))
    args=[str(model/'.venv/bin/rfd4-generate'),'inputs=data/benchmarks/monomer',
          'subset_to_examples=monomer-short','num_replicates=1','batch_size=1',
          'seed=42','compile_lengths=null','out_dir='+str(output),'hydra.run.dir='+str(output/'hydra')] + runtime_overrides(str(root))
    run(args,cwd=model,check=True,pass_fds=(lock_fd,),env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',DATA_PATH=str(model/'data_path'),HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1'))
    result=json.loads(run([str(model/'.venv/bin/python'),'-B','-c',VALIDATE,str(output)],check=True,capture_output=True,text=True).stdout)
    if not isinstance(result.get('structures'),list) or not result['structures']:
        raise ValueError('Smoke inference returned no validated structures')
    return {'example':'monomer-short','output_dir':str(output),'command':args,**result}


# Install the pinned upstream recipe into an explicitly staged model checkout.
#
# The caller owns a managed setup reservation. A remote execution lock additionally
# prevents this helper from mutating a runtime used by the durable job launcher.
#
import fcntl
import sys
from runtime_recipe import RECIPE, PROBE


from source_integrity import verify_source
from source_stage import stage

def validate_setup_review(path, expected_checksum, root, operation_id, *, recipe=RECIPE, scripts=None):
    """Bind remote execution to the review authorized by the controller."""
    scripts=Path(scripts) if scripts is not None else Path(__file__).parent
    review=json.loads(Path(path).read_text())
    digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest(review)!=expected_checksum:
        raise ValueError('Remote setup review checksum changed')
    if (review.get('operation_id')!=operation_id or review.get('action')!='setup'
            or review.get('remote_root')!=str(root)
            or review.get('recipe_id')!=recipe['id'] or review.get('recipe_checksum')!=digest(recipe)
            or review.get('recipe')!=recipe):
        raise ValueError('Remote setup review identity or recipe changed')
    files=review.get('files')
    if not isinstance(files,dict) or not files:
        raise ValueError('Remote setup review has no source manifest')
    for name,expected in files.items():
        if not isinstance(name,str) or Path(name).name!=name or name in ('.','..'):
            raise ValueError('Invalid reviewed source filename')
        path=scripts/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Remote setup source changed: '+name)
    prerequisites=review.get('prerequisites',{})
    if recipe.get('install_mode')=='public_wheels':
        from public_prerequisite import bind_review
        if review.get('phase')=='prepare_archives':
            raise ValueError('Public wheel setup does not prepare privileged package archives')
        bound=bind_review(prerequisites,scripts=scripts)
        if bound['helper_hashes']!={name:files.get(name) for name in bound['helper_hashes']}:
            raise ValueError('Remote public prerequisite helper differs from reviewed source')
    else:
        profile=json.loads((scripts/'toolchain_profile.json').read_text())
        prerequisites=review.get('prerequisites',{})
        if prerequisites.get('profile_sha256')!=digest(profile):
            raise ValueError('Remote prerequisite profile changed')
        if (review.get('phase')=='prepare_archives')!=(prerequisites.get('status')=='preparation_required'):
            raise ValueError('Remote preparation phase differs from prerequisites')
        from toolchain_process import BUNDLE_FILES
        helpers={name:files.get(name) for name in BUNDLE_FILES}
        if any(value is None for value in helpers.values()) or prerequisites.get('helper_hashes')!=helpers:
            raise ValueError('Remote prerequisite helper manifest changed')
    return review


class SetupCancelled(RuntimeError):
    pass

def check_cancel(root, operation_id):
    if operation_id and (Path(root)/'setup-operations'/operation_id/'cancel-requested').exists():
        raise SetupCancelled('Cancellation received; no subsequent setup stage will start')


def write_journal(path, value):
    fd,name=tempfile.mkstemp(prefix='.setup-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as handle:
            json.dump(value,handle);handle.flush();os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def setup(root, *, recipe=RECIPE, run=subprocess.run, download=fetch, lock_path=None, operation_id=None, reviewed=None, privileged=None):
    if recipe.get('install_mode')=='public_wheels' and reviewed is not None and reviewed.get('phase')=='prepare_archives':
        raise ValueError('Public wheel setup does not prepare privileged package archives')
    root=Path(root).resolve();model=root/'model'
    lock_path=Path(lock_path) if lock_path else Path.home()/'.local/share/bionemo-rfd4/execution.lock'
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    inherited=os.environ.get('RFD4_EXECUTION_LOCK_FD')
    if inherited is not None:
        descriptor=int(inherited)
        actual=os.fstat(descriptor);expected=lock_path.stat()
        if (actual.st_dev,actual.st_ino)!=(expected.st_dev,expected.st_ino):
            raise ValueError('Inherited runtime lock does not match this executor')
        lock_handle=os.fdopen(os.dup(descriptor),'a')
    else:
        lock_handle=lock_path.open('a')
    with lock_handle as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Runtime is in use; setup refused')
        journal=root/'runtime-setup.json'
        recipe_checksum=hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        status={'recipe_checksum':recipe_checksum,'operation_id':operation_id,'recipe_id':recipe['id'],'stage':'staging','ready':False}
        write_journal(journal,status)
        try:
            check_cancel(root,operation_id)
            if reviewed is not None and reviewed.get('phase')=='prepare_archives':
                from prerequisite_setup import prepare_archives
                profile=json.loads(Path(__file__).with_name('toolchain_profile.json').read_text())
                request=reviewed['prerequisites']
                names=request['packages']
                if (request.get('status')!='preparation_required' or 'changes' in request
                        or len(set(names))!=len(names) or not names
                        or request['profile_sha256']!=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                        or request['download_bytes']!=sum(int(profile['packages'][name]['Size']) for name in names)):
                    raise ValueError('Archive preparation review changed')
                status['stage']='preparing_archives';write_journal(journal,status)
                prepare_archives(profile,names,Path.home()/'.cache/bionemo-rfd4/packages',
                                 download=download,check_cancel=lambda:check_cancel(root,operation_id))
                check_cancel(root,operation_id)
                status.update(stage='archives_prepared',ready=False,prepared_packages=names,
                              review_checksum=hashlib.sha256(json.dumps(reviewed,sort_keys=True,separators=(',',':')).encode()).hexdigest())
                write_journal(journal,status)
                return status
            if not model.exists():
                check_cancel(root,operation_id)
                stage(root,recipe,run=run)
            if model.is_symlink():raise ValueError('Model checkout cannot be a symbolic link')
            revision=run(['git','-C',str(model),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
            if revision!=recipe['model_revision']:raise ValueError('Model revision does not match setup recipe')
            for relative,digest in recipe['source_hashes'].items():
                if hashlib.sha256((model/relative).read_bytes()).hexdigest()!=digest:
                    raise ValueError('Modified installer source: '+relative)
            verify_source(model,recipe['model_revision'],recipe.get('generated_source_hashes'))
            if recipe.get('install_mode')=='public_wheels':
                if reviewed is not None:
                    from public_prerequisite import bind_review
                    bind_review(reviewed.get('prerequisites',{}))
                status['prerequisites']={'kind':'public_wheels','package_mutations':0,'requires_sudo':False}
            elif reviewed is not None:
                from prerequisite_setup import install_prerequisites
                def prerequisite_journal(stage):
                    status['stage']=stage;write_journal(journal,status)
                def privileged_action(*args):
                    from prerequisite_privileged import adapter
                    return adapter(reviewed)(*args)
                from remote_job import publish_package_intent
                from prerequisite_privileged import record_terminal_receipt
                package_directory=root/'setup-operations'/operation_id
                def record_terminal(receipt):
                    record_terminal_receipt(package_directory,operation_id,reviewed['prerequisites'],receipt)
                status['prerequisites']=install_prerequisites(root,operation_id,reviewed,
                    privileged=privileged or privileged_action,journal=prerequisite_journal,
                    publication_started=lambda:publish_package_intent(package_directory,operation_id,reviewed['prerequisites'],lock.fileno(),lock_path.parent),
                    record_terminal=record_terminal,check_cancel=lambda:check_cancel(root,operation_id))
            status['stage']='installing';write_journal(journal,status)
            check_cancel(root,operation_id)
            installation=install(root,run=run,download=download,pass_fds=(lock.fileno(),))
            status['installation']=installation
            write_journal(journal,status)
            check_cancel(root,operation_id)
            status['stage']='downloading';write_journal(journal,status)
            weights=[]
            if recipe.get('model_bundle'):
                from public_model_bundle import manifest, download_bundle
                if recipe['model_bundle']!=manifest():raise ValueError('Reviewed public model bundle differs from this installer')
                download_bundle(root/'model-bundle',check_cancel=lambda:check_cancel(root,operation_id))
                weights=[str(root/'model-bundle'/item['name']) for item in recipe['model_bundle']['files']]
            else:
                for weight in recipe['weights']:
                    check_cancel(root,operation_id)
                    destination=model/'data_path'/weight['directory']/weight['name']
                    download(recipe['weights_base_url']+'/'+weight['directory']+'/'+weight['name'],destination,weight)
                    weights.append(str(destination))
            check_cancel(root,operation_id)
            status['stage']='verifying';write_journal(journal,status)
            cfg={'remote_root':str(root),'weight_paths':weights}
            evidence=json.loads(run([str(model/'.venv/bin/python'),'-B','-c',PROBE,json.dumps(cfg),json.dumps(recipe)],check=True,capture_output=True,text=True).stdout)
            required={'platform','python','revision','source','dependencies','entrypoint','weights','cuda','gpu'}
            if evidence.get('recipe_id')!=recipe['id'] or set(evidence.get('checks',{}))!=required or any(value is not True for value in evidence['checks'].values()):
                raise ValueError('Installed runtime failed recipe verification')
            check_cancel(root,operation_id)
            status.update(stage='smoke_running',evidence=evidence,weight_paths=weights)
            write_journal(journal,status)
            smoke_evidence=smoke(root,run,lock.fileno())
            post_evidence=json.loads(run([str(model/'.venv/bin/python'),'-B','-c',PROBE,json.dumps(cfg),json.dumps(recipe)],check=True,capture_output=True,text=True).stdout)
            if post_evidence.get('recipe_id')!=recipe['id'] or set(post_evidence.get('checks',{}))!=required or any(value is not True for value in post_evidence['checks'].values()):
                raise ValueError('Runtime changed or failed verification after smoke inference')
            status['post_smoke_evidence']=post_evidence
            smoke_evidence.update(operation_id=operation_id,recipe_checksum=recipe_checksum)
            status.update(stage='accepted',ready=True,smoke=smoke_evidence)
            write_journal(journal,status)
            return status
        except BaseException as error:
            status.update(stage='cancelled' if isinstance(error,SetupCancelled) else 'needs_attention',error=str(error),ready=False)
            write_journal(journal,status)
            raise


if __name__=='__main__':
    if len(sys.argv)!=5:raise ValueError('Managed setup requires its reviewed input and checksum')
    reviewed=validate_setup_review(sys.argv[3],sys.argv[4],sys.argv[1],sys.argv[2])
    print(json.dumps(setup(sys.argv[1],operation_id=sys.argv[2],reviewed=reviewed)))

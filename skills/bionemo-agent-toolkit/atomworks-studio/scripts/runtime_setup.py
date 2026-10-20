"""Install the pinned upstream recipe into an explicitly staged model checkout.

The caller owns a managed setup reservation. A remote execution lock additionally
prevents this helper from mutating a runtime used by the durable job launcher.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from runtime_download import fetch
from runtime_recipe import RECIPE, PROBE
from runtime_smoke import smoke
from runtime_install import install
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
        from toolchain_launch import BUNDLE_FILES
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
                from toolchain_download import prepare_archives
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

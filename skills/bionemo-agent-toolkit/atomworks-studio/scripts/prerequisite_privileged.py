"""Checksum-bound privileged adapter for the single managed setup coordinator.

Root executes verified in-memory modules, never imports a user-writable directory.
The durable worker receives a separate verified root-owned bundle.
"""
import hashlib
import json
from pathlib import Path
import subprocess

MODULES=('toolchain_paths','remote_job','toolchain_review','toolchain_process','toolchain_bundle')

BOOTSTRAP=r'''
import sys,json,hashlib,types,os
from pathlib import Path
payload=json.load(sys.stdin)
if os.geteuid()!=0:raise ValueError('Privileged prerequisite action requires root')
for name in payload['modules']:
    source=payload['sources'][name]
    if hashlib.sha256(source.encode()).hexdigest()!=payload['hashes'][name+'.py']:
        raise ValueError('Privileged source checksum changed: '+name)
# Verify the whole payload before executing any helper, including dependencies.
for name in payload['modules']:
    module=types.ModuleType(name);module.__file__='<reviewed:'+name+'>'
    sys.modules[name]=module
    exec(compile(payload['sources'][name],module.__file__,'exec'),module.__dict__)
from toolchain_paths import protected_directory,read_record
from toolchain_process import BUNDLE_FILES,launch
from toolchain_bundle import publish_bundle
from toolchain_process import publish
from toolchain_process import recover_preparation
from toolchain_process import observe
from remote_job import pending_machine_package
base=Path('/var/lib/bionemo-rfd4/prerequisites')
bundles=Path('/var/lib/bionemo-rfd4/helpers')
action=payload['action'];job=payload['job_id'];tx=payload['transaction'];profile=payload['profile']
digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
if profile.get('status')!='qualified' or tx['profile_sha256']!=digest(profile):
    raise ValueError('Prerequisite profile is not qualified or changed')
hashes={name:payload['hashes'][name] for name in BUNDLE_FILES}
if tx['helper_hashes']!=hashes:raise ValueError('Reviewed worker manifest changed')
if action in ('publish','recover'):
    for path in (base.parent,base,bundles):
        with protected_directory(path.parent) as parent:
            try:os.mkdir(path.name,0o755,dir_fd=parent)
            except FileExistsError:pass
        with protected_directory(path):pass
if action=='publish':
    bundle=publish_bundle(bundles,payload['source_directory'],hashes)
    result=publish(base,job,tx,digest(tx))
    result['bundle']=bundle
else:
    try:
        with protected_directory(base/job) as directory:
            intent=read_record(directory,'package-intent.json')
    except FileNotFoundError:
        if action!='recover':raise
        publish(base,job,tx,digest(tx))
        with protected_directory(base/job) as directory:
            intent=read_record(directory,'package-intent.json')
    if intent['transaction']!=tx or intent['transaction_sha256']!=digest(tx):
        raise ValueError('Protected prerequisite transaction changed')
    if action=='launch':
        bundle=bundles/digest(hashes)
        result=launch(base,job,bundle,hashes,profile,payload['archives'])
    elif action=='recover':
        with protected_directory(base) as directory:
            try:owner=read_record(directory,'package-owner.json')
            except FileNotFoundError:owner=None
        if owner is None or owner.get('job_id')!=job:
            # Reconcile the durable intent-to-owner boundary through the same
            # ownership lock; never overwrite a superseding/live owner.
            publish(base,job,tx,digest(tx))
        result=recover_preparation(base,job,profile=profile,reconcile_reboot=True)
    elif action=='fence':
        result=recover_preparation(base,job)
    elif action=='observe':
        pending=pending_machine_package(base)
        with protected_directory(base/job) as directory:
            try:receipt=read_record(directory,'package-stage.json')
            except FileNotFoundError:receipt=None
        if receipt is None:
            result={'job_id':job,'transaction_sha256':digest(tx),'state':'pending'}
        elif receipt.get('state') in ('succeeded','failed'):
            result=dict(receipt,state='pending') if pending is not None else receipt
        elif not receipt.get('scope'):
            result=dict(receipt,state='pending')
        else:
            saved=receipt['scope'];state=observe(saved['unit'],invocation=saved['invocation'])
            if state['state'] not in ('empty','absent'):
                result=dict(receipt,state='running')
            else:
                normal=(receipt.get('package_manager_waited') is True and type(receipt.get('exit_code')) is int and receipt['exit_code']==0)
                result=recover_preparation(base,job,profile=profile,finalize_success=normal)
    else:raise ValueError('Unsupported prerequisite action')
print(json.dumps(result))
'''


def adapter(reviewed, *, scripts=None, run=subprocess.run):
    scripts=Path(scripts) if scripts is not None else Path(__file__).parent
    hashes=reviewed['files'];sources={}
    for name in MODULES:
        path=scripts/(name+'.py')
        if path.is_symlink():raise ValueError('Privileged source cannot be a symlink')
        source=path.read_text()
        if hashlib.sha256(source.encode()).hexdigest()!=hashes.get(name+'.py'):
            raise ValueError('Privileged source differs from setup review: '+name)
        sources[name]=source
    def call(action,job_id,transaction,profile,archives):
        if action not in ('publish','launch','observe','fence','recover'):raise ValueError('Unsupported prerequisite action')
        if job_id!=reviewed['operation_id'] or transaction!=reviewed['prerequisites']:
            raise ValueError('Privileged request differs from authorized setup')
        payload={'modules':MODULES,'sources':sources,'hashes':hashes,'action':action,
                 'job_id':job_id,'transaction':transaction,'profile':profile,
                 'archives':{name:str(path) for name,path in archives.items()},'source_directory':str(scripts)}
        result=run(['/usr/bin/sudo','-n','/usr/bin/python3','-I','-S','-B','-c',BOOTSTRAP],
                   input=json.dumps(payload),capture_output=True,text=True,check=True,timeout=180,
                   env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'})
        return json.loads(result.stdout)
    return call


def record_terminal_receipt(directory,operation_id,transaction,receipt):
    from remote_job import write,pending_package_stage
    digest=hashlib.sha256(json.dumps(transaction,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if (receipt.get('job_id')!=operation_id or receipt.get('transaction_sha256')!=digest
            or receipt.get('state') not in ('succeeded','failed')):
        raise ValueError('Protected terminal receipt does not match the local publication')
    directory=Path(directory)
    intent=json.loads((directory/'package-intent.json').read_text())
    if intent.get('job_id')!=operation_id or intent.get('transaction_sha256')!=digest or intent.get('transaction')!=transaction:
        raise ValueError('Local prerequisite publication changed')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='.receipt-check-',dir=directory) as check:
        check=Path(check)
        write(check/'package-intent.json',intent)
        (check/'package-dispatch.lock').touch()
        write(check/'package-stage.json',receipt)
        if pending_package_stage(check,operation_id):
            raise ValueError('Protected receipt is not terminal')
    existing_path=directory/'package-stage.json'
    if existing_path.exists():
        previous=json.loads(existing_path.read_text())
        if previous.get('state') in ('succeeded','failed') and previous!=receipt:
            raise ValueError('A different terminal prerequisite receipt is already recorded')
    (directory/'package-dispatch.lock').touch(exist_ok=True)
    write(directory/'package-stage.json',receipt)
    if pending_package_stage(directory,operation_id):
        raise ValueError('Protected receipt did not resolve local publication')


def reconcile_reviewed_setup(action, root, operation_id, review_path, review_checksum, *, run=subprocess.run, lease_path=None):
    """Recovery must hold the ordinary executor lease before fencing root work."""
    import fcntl
    from runtime_setup import validate_setup_review
    reviewed=validate_setup_review(review_path,review_checksum,root,operation_id)
    profile=json.loads(Path(__file__).with_name('toolchain_profile.json').read_text())
    if action not in ('observe','recover'):raise ValueError('Unsupported reconciliation action')
    call=adapter(reviewed,run=run)
    if action=='observe':return call(action,operation_id,reviewed['prerequisites'],profile,{})
    lease=Path(lease_path) if lease_path is not None else Path.home()/'.local/share/bionemo-rfd4/execution.lock'
    # A dispatched supervisor necessarily created the lease. Missing lease is
    # not proof of inactivity, so recovery never creates a replacement here.
    with lease.open('r+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {'job_id':operation_id,'state':'pending','detail':'Setup or another executor still owns the machine lease; no package recovery was performed'}
        receipt=call(action,operation_id,reviewed['prerequisites'],profile,{})
        if receipt.get('state') in ('succeeded','failed'):
            record_terminal_receipt(Path(root)/'setup-operations'/operation_id,operation_id,reviewed['prerequisites'],receipt)
        return receipt


if __name__=='__main__':
    import sys
    if len(sys.argv)!=6:raise ValueError('Reconciliation requires action, root, operation, reviewed input and checksum')
    print(json.dumps(reconcile_reviewed_setup(*sys.argv[1:])))

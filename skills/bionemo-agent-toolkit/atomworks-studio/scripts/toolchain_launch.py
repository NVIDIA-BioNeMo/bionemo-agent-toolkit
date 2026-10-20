"""One-shot privileged scope dispatch. No launch acknowledgment permits retry."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from contextlib import ExitStack
from toolchain_paths import protected_directory,read_record,write_record
from toolchain_scope import scope_name
from toolchain_review import package_environment
from remote_job import pending_machine_package

BUNDLE_FILES=frozenset({'toolchain_launch.py','toolchain_stage.py','toolchain_scope.py',
    'toolchain_review.py','toolchain_plan.py','toolchain_paths.py','toolchain_archives.py','remote_job.py'})
BOOT_ID=Path('/proc/sys/kernel/random/boot_id')


def verify_bundle(bundle, hashes):
    if set(hashes)!=BUNDLE_FILES:raise ValueError('Incomplete reviewed package helper bundle')
    with protected_directory(bundle) as directory:
        if set(os.listdir(directory))!=BUNDLE_FILES:
            raise ValueError('Package helper directory contains unreviewed files or bytecode')
        for name,digest in hashes.items():
            descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            with os.fdopen(descriptor,'rb') as handle:
                metadata=os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_mode & 0o022:
                    raise ValueError('Package helper must be a protected root-owned file')
                if hashlib.sha256(handle.read()).hexdigest()!=digest:
                    raise ValueError('Reviewed package helper changed: '+name)


def launch(base,job_id,bundle,hashes,profile,archives,*,process=subprocess.Popen):
    if os.geteuid()!=0:raise ValueError('Package dispatch requires authorized sudo')
    base=Path(base);bundle=Path(bundle)
    verify_bundle(bundle,hashes)
    with ExitStack() as stack:
        parent=stack.enter_context(protected_directory(base))
        directory=stack.enter_context(protected_directory(base/job_id))
        descriptor=os.open('package-dispatch.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=directory)
        lock=stack.enter_context(os.fdopen(descriptor,'a'))
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Package worker is active; observe it without redispatch')
        intent=read_record(directory,'package-intent.json')
        owner=read_record(parent,'package-owner.json')
        if owner.get('job_id')!=job_id or owner.get('directory')!=str(base/job_id):
            raise ValueError('Package launch does not own the protected transaction')
        pending_machine_package(base)
        if intent['transaction'].get('helper_hashes')!=hashes:
            raise ValueError('Package helper hashes are not bound to the authorized review')
        digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=intent['transaction'].get('profile_sha256'):
            raise ValueError('Package profile differs from the authorized review')
        try:stage=read_record(directory,'package-stage.json')
        except FileNotFoundError:stage=None
        if stage is not None:return {'state':'already_dispatched','stage':stage}
        try:previous=read_record(directory,'package-launch.json')
        except FileNotFoundError:previous=None
        if previous is not None:return {'state':'dispatch_uncertain','launch':previous}
        record={'job_id':job_id,'transaction_sha256':intent['transaction_sha256'],
                'boot':BOOT_ID.read_text().strip(),
                'unit':scope_name(job_id,intent['transaction_sha256']),
                'bundle':str(bundle),'hashes':hashes,'profile':profile,
                'archives':{name:str(path) for name,path in archives.items()}}
        write_record(directory,'package-launch.json',record)
        log_fd=os.open('package-launch.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    # The journal precedes dispatch. Recovery can win this boundary and write a
    # stage fence; the delayed worker checks that fence under the same lock.
    with os.fdopen(log_fd,'ab') as log:
        child=process(['/usr/bin/systemd-run','--system','--scope','--unit='+record['unit'],
            '/usr/bin/python3','-I','-S','-B','-c',
            'import sys;sys.path.insert(0,sys.argv[1]);from toolchain_launch import worker;worker(sys.argv[2],sys.argv[3])',
            str(bundle),str(base),job_id],stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            env=package_environment(),start_new_session=True,close_fds=True)
    return {'state':'dispatch_uncertain','job_id':job_id,'launcher_pid':child.pid}


def worker(base,job_id):
    # Scope containment is verified again by execute before any package command.
    with protected_directory(Path(base)/job_id) as directory:
        launch_record=read_record(directory,'package-launch.json')
    if launch_record['job_id']!=job_id:raise ValueError('Package worker job mismatch')
    if BOOT_ID.read_text().strip()!=launch_record['boot']:
        raise ValueError('Package worker belongs to an earlier boot')
    verify_bundle(launch_record['bundle'],launch_record['hashes'])
    from toolchain_stage import execute
    execute(Path(base)/job_id,job_id,launch_record['profile'],launch_record['archives'],base)

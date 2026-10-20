"""Protected package recovery; never repairs packages or redispatches work."""
import fcntl
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from contextlib import ExitStack
from toolchain_paths import protected_directory,read_record,write_record
from remote_job import pending_machine_package
from toolchain_scope import observe,scope_name
from toolchain_stage import verify_installed
from toolchain_review import package_environment


BOOT_ID_PATH=Path('/proc/sys/kernel/random/boot_id')
PACKAGE_LOCKS=(Path('/var/lib/dpkg/lock-frontend'),Path('/var/lib/dpkg/lock'))


def recover_preparation(base, job_id, *, reconcile_reboot=False, profile=None, finalize_success=False, run=subprocess.run):
    if os.geteuid()!=0:raise ValueError('Protected package recovery requires authorized sudo')
    base=Path(base)
    with ExitStack() as stack:
        parent=stack.enter_context(protected_directory(base))
        for name in ('ownership.lock',):
            fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=parent)
            handle=stack.enter_context(os.fdopen(fd,'a'))
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Package ownership is changing; retry recovery')
        owner=read_record(parent,'package-owner.json')
        if owner.get('job_id')!=job_id or owner.get('directory')!=str(base/job_id):
            raise ValueError('Recovery does not match the protected package owner')
        directory=stack.enter_context(protected_directory(base/job_id))
        fd=os.open('package-dispatch.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=directory)
        handle=stack.enter_context(os.fdopen(fd,'a'))
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Package stage is still active; recovery made no changes')
        intent=read_record(directory,'package-intent.json')
        if intent.get('protocol')!=1:raise ValueError('Package recovery cannot prove this older preparation protocol')
        # Verifies immutable transaction correlation; never resolves based on PID absence.
        pending_machine_package(base)
        try:receipt=read_record(directory,'package-stage.json')
        except FileNotFoundError:receipt=None
        if receipt and receipt.get('state') in ('succeeded','failed') and receipt.get('scope_quiescent') is True:
            # pending_machine_package above validated this durable terminal receipt.
            # Never upgrade an interrupted/failed outcome on a later call.
            return receipt
        if receipt and (receipt.get('dispatch_started') or receipt.get('package_process') or receipt.get('package_manager_waited')):
            if not reconcile_reboot and profile is None:
                raise ValueError('Package installation may have started; process and package-state reconciliation is required')
            prior=receipt.get('supervisor',{}).get('boot')
            current=BOOT_ID_PATH.read_text().strip()
            try:uuid.UUID(prior);uuid.UUID(current)
            except (ValueError,TypeError,AttributeError):raise ValueError('No valid boot identity proves the original processes ended')
            if prior==current:
                if profile is None:raise ValueError('Same-boot package recovery requires surviving-process reconciliation')
                return reconcile_scope(directory,intent,receipt,current,profile,stack,run,finalize_success=finalize_success)
            if not reconcile_reboot:raise ValueError('Boot changed; use explicit reboot reconciliation')
            for path in PACKAGE_LOCKS:
                fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
                package_lock=stack.enter_context(os.fdopen(fd,'r+'))
                try:fcntl.lockf(package_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise ValueError('Package manager is active; recovery made no changes')
            audit=run(['dpkg','--audit'],check=True,capture_output=True,text=True,timeout=60,
                      env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'}).stdout.strip()
            if audit:raise ValueError('Package database requires repair; ownership retained: '+audit)
            result=dict(receipt,state='failed',execution_outcome='unknown',recovery='reboot_reconciled',
                        recovery_boot=current,package_database_clean=True,package_locks_verified=True)
            write_record(directory,'package-stage.json',result)
            return result
        if receipt and receipt.get('dispatch_not_started') is True:return receipt
        result={'job_id':job_id,'transaction_sha256':intent['transaction_sha256'],
                'state':'failed','dispatch_not_started':True,
                'preparation_error':'Interrupted preparation was fenced before package dispatch; review a new setup to retry',
                'recovery':'undispatched_preparation_fenced'}
        write_record(directory,'package-stage.json',result)
        return result


def reconcile_scope(directory,intent,receipt,current,profile,stack,run,*,finalize_success=False):
    """Caller holds owner/dispatch locks; existing stage fences delayed workers."""
    digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if intent['transaction'].get('profile_sha256')!=digest:
        raise ValueError('Recovery profile differs from the reviewed transaction')
    saved=receipt.get('scope',{})
    unit=scope_name(intent['job_id'],intent['transaction_sha256'])
    if (saved.get('unit')!=unit or saved.get('control_group')!='/system.slice/'+unit
            or saved.get('populated') is not True or saved.get('active_state')!='active'
            or saved.get('sub_state')!='running' or not saved.get('invocation')):
        raise ValueError('No verified pre-install scope membership; ownership retained')
    observed=observe(unit,invocation=saved['invocation'],run=run)
    if observed['state'] not in ('empty','absent'):
        raise ValueError('Package scope still has activity; ownership retained')
    # This lock remains held through postcondition checks and the final receipt.
    # A delayed worker must acquire it and then refuses the existing stage.
    for path in PACKAGE_LOCKS:
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
        lock=stack.enter_context(os.fdopen(fd,'r+'))
        try:fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Package manager is active; ownership retained')
    installed=verify_installed(profile,run,package_environment())
    result=dict(receipt,state='failed',recovery='same_boot_reconciled',
                recovery_boot=current,execution_outcome='unknown',
                scope_quiescent=True,scope_observation=observed,
                package_database_clean=True,package_locks_verified=True,
                installed_packages=installed,needs_reconciliation=False,
                detail='Interrupted setup reconciled without retry; review setup again to verify the runtime')
    if finalize_success:
        process=receipt.get('package_process',{})
        if (receipt.get('dispatch_started') is not True
                or receipt.get('package_manager_waited') is not True
                or type(receipt.get('exit_code')) is not int or receipt['exit_code']!=0
                or type(process.get('pid')) is not int or process['pid']<=0
                or not str(process.get('start','')).isdigit() or process.get('boot')!=current):
            raise ValueError('Normal package completion lacks a matching successful process receipt')
        for stale in ('needs_attention','verification_error','preparation_error'):
            result.pop(stale,None)
        result.update(state='succeeded',recovery='normal_completion',execution_outcome='succeeded',
                      detail='Reviewed prerequisites completed and independently verified; runtime setup is not yet complete')
    # Preserve an observed apt exit separately. This is not a setup success or
    # readiness claim, including when all package versions happen to match.
    write_record(directory,'package-stage.json',result)
    return result

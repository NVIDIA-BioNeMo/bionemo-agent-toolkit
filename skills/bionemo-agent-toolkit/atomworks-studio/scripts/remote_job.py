"""Linux-side durable job launcher. Standard library only; never retries dispatch."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def write(path, value):
    temporary = path.with_name('.' + uuid.uuid4().hex)
    with temporary.open('w') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    fd = os.open(str(path.parent), os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def identity(pid):
    # stat field 22 is process start time; comm can contain spaces/parentheses.
    text = Path('/proc/' + str(pid) + '/stat').read_text()
    fields = text[text.rindex(')') + 2:].split()
    return {'pid': pid, 'start': fields[19],
            'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'process_state': fields[0]}



def terminal_package_available(directory, record):
    """A terminal marker alone cannot release a still-running stage."""
    descriptor=os.open(directory/'package-dispatch.lock',os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,'r') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(record,state='running',detail='Package stage still owns its dispatch lock')
    return None


def pending_package_stage(directory, job_id):
    """A privileged child may outlive sudo and all ordinary executor leases.

    The installer must write intent before sudo dispatch and write a terminal
    receipt only after waiting for the package manager. Missing terminal proof
    must never be converted to a fenced/safely released setup reservation.
    """
    intent_path = directory / 'package-intent.json'
    path = directory / 'package-stage.json'
    if not intent_path.exists():
        if path.exists(): raise ValueError('Package stage has no reviewed intent')
        return None
    intent = json.loads(intent_path.read_text())
    if intent.get('job_id') != job_id or not isinstance(intent.get('transaction'), dict):
        raise ValueError('Package intent identity mismatch')
    digest = hashlib.sha256(json.dumps(intent['transaction'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if intent.get('transaction_sha256') != digest:
        raise ValueError('Package intent checksum mismatch')
    if not path.exists():
        return {'job_id':job_id,'state':'intent','transaction_sha256':digest}
    record = json.loads(path.read_text())
    if record.get('job_id') != job_id or record.get('transaction_sha256') != digest:
        raise ValueError('Package stage identity mismatch')
    if record.get('state') not in ('intent','running','succeeded','failed'):
        raise ValueError('Invalid package stage receipt')
    if record['state'] in ('succeeded','failed'):
        if record['state']=='failed' and record.get('recovery')=='same_boot_reconciled':
            validate_scope_reconciliation(intent,record)
            if record.get('execution_outcome')!='unknown':
                raise ValueError('Recovery must preserve the uncertain installation outcome')
            return terminal_package_available(directory,record)
        if record['state']=='failed' and record.get('recovery')=='reboot_reconciled':
            try:
                old=uuid.UUID(record.get('supervisor',{}).get('boot'))
                new=uuid.UUID(record.get('recovery_boot'))
            except (ValueError,TypeError,AttributeError):raise ValueError('Invalid package reboot recovery evidence')
            if old==new or record.get('package_database_clean') is not True or record.get('package_locks_verified') is not True or record.get('execution_outcome')!='unknown':
                raise ValueError('Inconsistent package reboot recovery evidence')
            return terminal_package_available(directory,record)
        if record['state']=='failed' and record.get('dispatch_not_started') is True:
            if record.get('dispatch_started') or record.get('package_process') or not record.get('preparation_error'):
                raise ValueError('Inconsistent package preparation failure')
            return terminal_package_available(directory,record)
        if record['state']!='succeeded' or record.get('package_manager_waited') is not True:
            raise ValueError('Package stage has no terminal process evidence')
        validate_scope_reconciliation(intent,record)
        process=record.get('package_process',{})
        if (record.get('dispatch_started') is not True or type(record.get('exit_code')) is not int
                or record['exit_code']!=0 or type(process.get('pid')) is not int or process['pid']<=0
                or not str(process.get('start','')).isdigit() or not process.get('boot')):
            raise ValueError('Inconsistent successful package process receipt')
        installed=record.get('installed_packages')
        if not isinstance(installed,dict) or any(installed.get(name)!=change['version']
                for name,change in intent['transaction'].get('changes',{}).items()):
            raise ValueError('Successful package receipt lacks reviewed installed versions')
        return terminal_package_available(directory,record)
    return record


def validate_scope_reconciliation(intent,record):
    """A terminal installer receipt must include external descendant checks."""
    try:
        old=uuid.UUID(record.get('supervisor',{}).get('boot'))
        new=uuid.UUID(record.get('recovery_boot'))
    except (ValueError,TypeError,AttributeError):raise ValueError('Invalid scope recovery boot evidence')
    if (old!=new or record.get('scope_quiescent') is not True
            or record.get('package_database_clean') is not True
            or record.get('package_locks_verified') is not True):
        raise ValueError('Incomplete scope reconciliation evidence')
    unit='rfd4-package-'+hashlib.sha256((intent['job_id']+'\0'+intent['transaction_sha256']).encode()).hexdigest()[:32]+'.scope'
    saved=record.get('scope',{});observed=record.get('scope_observation',{})
    invocation=saved.get('invocation')
    if (saved.get('unit')!=unit or saved.get('control_group')!='/system.slice/'+unit
            or saved.get('populated') is not True or saved.get('active_state')!='active'
            or saved.get('sub_state')!='running' or not isinstance(invocation,str)
            or len(invocation)!=32 or any(c not in '0123456789abcdef' for c in invocation)
            or observed.get('unit')!=unit or observed.get('state') not in ('empty','absent')):
        raise ValueError('Invalid scope identity or emptiness evidence')
    if observed['state']=='empty' and (observed.get('invocation')!=invocation
            or observed.get('control_group')!=saved['control_group']
            or observed.get('populated') is not False or observed.get('active_state')!='inactive'
            or observed.get('sub_state')!='dead'):
        raise ValueError('Inconsistent empty scope evidence')
    installed=record.get('installed_packages')
    if not isinstance(installed,dict) or any(installed.get(name)!=change['version']
            for name,change in intent['transaction'].get('changes',{}).items()):
        raise ValueError('Reconciled package versions differ from review')


def pending_machine_package(lease_dir):
    owner_path = lease_dir / 'package-owner.json'
    if not owner_path.exists(): return None
    owner = json.loads(owner_path.read_text())
    directory = Path(owner['directory'])
    if not directory.is_absolute(): raise ValueError('Package owner directory must be absolute')
    if not (directory/'package-intent.json').is_file():
        raise ValueError('Machine package owner has lost its intent; reconciliation required')
    pending = pending_package_stage(directory, owner['job_id'])
    intent = json.loads((directory/'package-intent.json').read_text())
    if intent['transaction_sha256'] != owner['transaction_sha256']:
        raise ValueError('Machine package transaction identity mismatch')
    return dict(pending, directory=str(directory)) if pending else None


def publish_package_intent(directory, job_id, transaction, execution_fd, lease_dir):
    """Publish under the inherited machine lease before any privileged dispatch."""
    actual=os.fstat(execution_fd);expected=(lease_dir/'execution.lock').stat()
    if (actual.st_dev,actual.st_ino)!=(expected.st_dev,expected.st_ino):
        raise ValueError('Package publication requires this executor lease')
    fcntl.flock(execution_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if pending_machine_package(lease_dir):
        raise ValueError('A prior package transaction remains unresolved')
    intent_path=directory/'package-intent.json'
    if intent_path.exists():raise ValueError('This package intent is immutable; reconcile the original transaction')
    digest=hashlib.sha256(json.dumps(transaction,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write(intent_path,{'job_id':job_id,'transaction':transaction,'transaction_sha256':digest})
    write(lease_dir/'package-owner.json',{'job_id':job_id,'directory':str(directory.resolve()),'transaction_sha256':digest})
    return digest


PROTECTED_PACKAGE_ROOT = Path('/var/lib/bionemo-rfd4/prerequisites')


def pending_protected_package():
    base=PROTECTED_PACKAGE_ROOT
    if not base.exists() and not base.is_symlink():return None
    from toolchain_paths import protected_directory,read_record
    with protected_directory(base) as descriptor:
        try:owner=read_record(descriptor,'package-owner.json')
        except FileNotFoundError:return None
        job_id=owner.get('job_id','')
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',job_id):raise ValueError('Invalid protected package owner')
        if owner.get('directory')!=str(base/job_id):raise ValueError('Protected package owner escaped its root')
        with protected_directory(base/job_id) as transaction:
            read_record(transaction,'package-intent.json')
            try:read_record(transaction,'package-stage.json')
            except FileNotFoundError:pass
        return pending_machine_package(base)


def status(directory, job_id):
    protected=pending_protected_package()
    if protected and protected['job_id']==job_id:
        return {'job_id':job_id,'state':'unknown','package_stage':protected,'detail':'Protected package transaction remains unresolved; reconcile before releasing this machine'}
    pending = pending_package_stage(directory, job_id)
    if pending:
        return {'job_id':job_id, 'state':'unknown', 'package_stage':pending,
                'detail':'Privileged package installation has no terminal receipt. Reconcile that installation before releasing this machine; do not retry installation.'}
    marker = directory / 'job-state.json'
    if not marker.exists(): return {'job_id': job_id, 'state': 'unknown'}
    record = json.loads(marker.read_text())
    if record.get('job_id') != job_id:
        raise ValueError('Remote job identity mismatch')
    if record['state'] == 'running':
        try:
            current = identity(record['process']['pid'])
            if any(current[k] != record['process'][k] for k in ('pid','start','boot')) or current['process_state'] in ('Z','X'):
                record['state'] = 'unknown'
        except (FileNotFoundError, ProcessLookupError):
            record['state'] = 'unknown'
    if record['state'] == 'accepted': record['state'] = 'unknown'
    return record


def verify_execution_payload(directory, job_id, expected):
    """New payload protocol; legacy history is never silently converted."""
    import re
    from execution_payload import verify_path
    from executor_ownership import checksum, inspect, validate
    verify_path(directory / 'payload', expected)
    binding = expected['binding']
    if (set(binding) != {'kind', 'id', 'review_checksum', 'executor_ownership'}
            or binding.get('kind') not in ('run', 'setup') or binding.get('id') != job_id
            or not isinstance(binding.get('review_checksum'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', binding['review_checksum'])):
        raise ValueError('Execution payload review identity differs')
    proof = binding['executor_ownership']
    if not isinstance(proof, dict) or not isinstance(proof.get('owner'), dict):
        raise ValueError('Execution payload has no executor ownership proof')
    owner = validate(proof['owner'])
    if proof.get('owner_checksum') != checksum(owner):
        raise ValueError('Execution payload ownership checksum differs')
    if inspect(owner).get('state') != 'owned':
        raise ValueError('Protected executor ownership is not committed')


def launch(directory, job_id, *, expected_payload=None):
    with (directory / 'dispatch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if pending_package_stage(directory, job_id): return status(directory, job_id)
        marker = directory / 'job-state.json'
        if marker.exists(): return status(directory, job_id)
        accepted = {'job_id': job_id, 'state': 'accepted'}
        if expected_payload is None and any(path.exists() or path.is_symlink()
                                           for path in (directory / 'payload', directory / '.payload-publish.lock')):
            raise ValueError('Published execution requires its reviewed payload protocol; legacy dispatch refused')
        if expected_payload is not None:
            verify_execution_payload(directory, job_id, expected_payload)
            if (directory / 'cancel-requested').exists():
                record = {'job_id': job_id, 'state': 'failed', 'reason': 'cancelled_before_launch', 'dispatch_not_started': True}
                write(marker, record)
                return record
            accepted['payload'] = expected_payload
        write(marker, accepted)
        # Crash before/after spawn leaves an accepted marker, never permission to relaunch.
        with (directory / 'supervisor.log').open('ab') as log:
            command = [sys.executable, '-B', str(Path(__file__).resolve()), 'supervise', str(directory), job_id]
            if expected_payload is not None:
                command[3] = 'supervise-published'
                command.append(json.dumps(expected_payload, sort_keys=True, separators=(',', ':')))
            subprocess.Popen(command,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        return {'job_id': job_id, 'state': 'accepted'}


def recover(directory, job_id):
    """Fence an orphaned dispatch, never rerun it or claim its work was undone.

    All three locks are needed: a delayed launcher, supervisor or surviving
    model child must not race the terminal fence. Children inherit both leases.
    """
    from contextlib import ExitStack
    lease_dir = Path.home() / '.local/share/bionemo-rfd4'
    lease_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as stack:
        for path in (directory/'dispatch.lock', directory/'supervisor.lock', lease_dir/'execution.lock'):
            handle = stack.enter_context(path.open('a'))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'job_id':job_id, 'state':'unknown', 'recovery':'busy',
                        'detail':'A dispatcher, supervisor or model still owns a lease. No state was changed.'}
        previous = status(directory, job_id)
        if previous.get('package_stage'):
            return dict(previous, recovery='package_installation_unresolved')
        if previous['state'] in ('completed','failed'):
            return previous
        if previous['state'] != 'unknown':
            return dict(previous, recovery='busy')
        record = {'job_id':job_id, 'state':'failed', 'reason':'orphaned_dispatch_fenced',
                  'execution_outcome':'unknown', 'previous':previous,
                  'detail':'No executor lease remains. This dispatch is permanently fenced; prior effects are not rolled back. Review a new setup before retrying.'}
        write(directory/'job-state.json', record)
        return record


def supervise(directory, job_id, *, expected_payload=None):
    lease_dir = Path.home() / '.local/share/bionemo-rfd4'
    lease_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = directory / 'job-state.json'
    with (directory / 'supervisor.lock').open('a') as job_lock, (lease_dir / 'execution.lock').open('a') as lock:
        try: fcntl.flock(job_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        accepted = {'job_id': job_id, 'state': 'accepted'}
        if expected_payload is not None: accepted['payload'] = expected_payload
        if json.loads(marker.read_text()) != accepted:
            raise ValueError('Job is not awaiting its first supervisor')
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            write(marker, {'job_id':job_id, 'state':'failed', 'reason':'Another model job owns this executor'})
            return
        pending = pending_protected_package() or pending_machine_package(lease_dir)
        if pending:
            write(marker, {'job_id':job_id,'state':'failed','reason':'Unresolved privileged package transaction blocks this executor','package_owner':pending})
            return
        script = directory / 'run.sh'
        if expected_payload is not None:
            verify_execution_payload(directory, job_id, expected_payload)
            if (directory / 'cancel-requested').exists():
                write(marker, {'job_id': job_id, 'state': 'failed', 'reason': 'cancelled_before_execution', 'dispatch_not_started': True})
                return
            script = directory / 'payload' / 'run.sh'
        write(marker, {'job_id':job_id, 'state':'running', 'process':identity(os.getpid())})
        with (directory / 'run.log').open('ab') as log:
            # The model inherits the lock too: killing only the supervisor does not free GPU ownership.
            result = subprocess.run(['bash', str(script)], stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=log, pass_fds=(lock.fileno(), job_lock.fileno()),
                                    env=dict(os.environ,RFD4_EXECUTION_LOCK_FD=str(lock.fileno())))
        write(marker, {'job_id':job_id, 'state':'completed' if result.returncode == 0 else 'failed',
                       'exit_code':result.returncode})


if __name__ == '__main__':
    action, folder, job_id = sys.argv[1:4]
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', job_id): raise ValueError('Invalid job ID')
    directory = Path(folder).resolve()
    if action in ('launch-published', 'supervise-published'):
        if len(sys.argv) != 5: raise ValueError('Expected published execution identity')
        expected_payload = json.loads(sys.argv[4])
        if action == 'launch-published': print(json.dumps(launch(directory, job_id, expected_payload=expected_payload)))
        else: supervise(directory, job_id, expected_payload=expected_payload)
    elif len(sys.argv) != 4: raise ValueError('Unexpected legacy job arguments')
    elif action == 'launch': print(json.dumps(launch(directory, job_id)))
    elif action == 'status': print(json.dumps(status(directory, job_id)))
    elif action == 'recover': print(json.dumps(recover(directory, job_id)))
    elif action == 'supervise': supervise(directory, job_id)
    else: raise ValueError('Unknown action')

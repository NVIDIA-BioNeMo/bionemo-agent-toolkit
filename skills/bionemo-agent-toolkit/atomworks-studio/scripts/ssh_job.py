"""Remote-only durable execution. No provisioning, ownership or local daemon."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def write(path, value):
    temporary = path.with_name('.' + uuid.uuid4().hex)
    with temporary.open('x') as handle:
        json.dump(value, handle, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return [Path('/proc/sys/kernel/random/boot_id').read_text().strip(), fields[19]]
    except (OSError, IndexError):
        return None


def status(directory, digest):
    receipt = directory / 'receipt.json'
    if not receipt.exists():
        return {'state': 'not_launched', 'launch_checksum': digest}
    record = json.loads(receipt.read_text())
    if record['launch_checksum'] != digest:
        raise ValueError('Remote receipt belongs to different input or settings')
    if record['state'] == 'running' and identity(record['pid']) != record['process_identity']:
        return dict(record, state='submission_unknown', detail='Supervisor ended without a terminal receipt; inspect logs before retrying')
    return record


def supervise(directory, digest):
    # Global execution lock is scoped to this output root, not machine ownership.
    with (directory.parent / '.rfd4-execution.lock').open('a') as execution:
        try:
            fcntl.flock(execution, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            write(directory / 'receipt.json', {'state': 'failed', 'launch_checksum': digest,
                  'exit_code': None, 'detail': 'Another RFD4 run uses this output root'})
            return
        record = {'state': 'running', 'launch_checksum': digest, 'pid': os.getpid(),
                  'process_identity': identity(os.getpid())}
        write(directory / 'receipt.json', record)
        try:
            manifest = json.loads((directory / 'launch.json').read_text())
            if hashlib.sha256((directory / 'input.cif').read_bytes()).hexdigest() != manifest['input_sha256']:
                raise ValueError('Uploaded input changed')
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1',
                               HF_HUB_DISABLE_TELEMETRY='1')
            with (directory / 'run.log').open('ab') as log:
                result = subprocess.run(manifest['argv'], cwd=manifest['cwd'], env=environment,
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                        pass_fds=(execution.fileno(),))
            record.update(state='completed' if result.returncode == 0 else 'failed', exit_code=result.returncode)
        except Exception as error:
            record.update(state='failed', detail=str(error))
        write(directory / 'receipt.json', record)


def launch(directory, bundle):
    digest = bundle['launch_checksum']
    manifest = bundle['manifest']
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Launch manifest checksum mismatch')
    if hashlib.sha256(bundle['helper'].encode()).hexdigest() != manifest['helper_sha256']:
        raise ValueError('Remote helper checksum mismatch')
    content = base64.b64decode(bundle['input'], validate=True)
    if hashlib.sha256(content).hexdigest() != manifest['input_sha256']:
        raise ValueError('Upload checksum mismatch')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise ValueError('Run directory must not be a symlink')
    with (directory / '.launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        observed = status(directory, digest)
        if observed['state'] != 'not_launched':
            return observed
        # Never overwrite a prior launch, even if a client interrupted publication.
        previous = directory / 'launch.json'
        if previous.exists() and json.loads(previous.read_text()) != manifest:
            raise ValueError('Run identity already contains different settings')
        write(previous, manifest)
        (directory / 'input.cif').write_bytes(content)
        (directory / 'ssh_job.py').write_text(bundle['helper'])
        # Persist uncertainty BEFORE spawning. A crash here cannot cause duplicate inference.
        write(directory / 'receipt.json', {'state': 'submission_unknown', 'launch_checksum': digest,
              'detail': 'Launch pending; check this receipt before retrying'})
        with (directory / 'supervisor.log').open('ab') as log:
            subprocess.Popen([sys.executable, '-B', str(directory / 'ssh_job.py'), 'supervise',
                              str(directory), digest], stdin=subprocess.DEVNULL, stdout=log,
                             stderr=log, start_new_session=True, close_fds=True)
    for _ in range(20):
        observed = status(directory, digest)
        if observed['state'] != 'submission_unknown':
            return observed
        time.sleep(0.05)
    return observed


if __name__ == '__main__':
    action, path, payload = sys.argv[1:]
    directory = Path(path)
    if action == 'supervise':
        supervise(directory, payload)
    elif action == 'launch':
        print(json.dumps(launch(directory, json.loads(base64.b64decode(payload)))))
    elif action == 'launch-file':
        upload = Path(payload)
        bundle = json.loads(upload.read_text())
        result = launch(directory, bundle)
        upload.unlink(missing_ok=True)
        print(json.dumps(result))
    elif action == 'status':
        print(json.dumps(status(directory, payload)))
    else:
        raise ValueError('Unknown job action')

"""Execution on a named SSH target; lifecycle actions remain in chat/CLI."""
import base64
import fcntl
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex

from registry import atomic
from runtime_recipe import RECIPE, inspect, overrides, runtime_overrides


def target(value):
    if not isinstance(value, dict) or set(value) - {'ssh_alias', 'runtime_root', 'output_root', 'organization_id', 'instance_id'}:
        raise ValueError('Supply an SSH alias, runtime_root and output_root; optional Brev organization_id and instance_id')
    result = dict(value)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,200}', result.get('ssh_alias', '')):
        raise ValueError('Name a configured SSH alias')
    for key in ('runtime_root', 'output_root'):
        value = result.get(key, '')
        path = PurePosixPath(value)
        if not path.is_absolute() or '..' in path.parts or not re.fullmatch(r'/[A-Za-z0-9_./-]+', value) or str(path) != value:
            raise ValueError(key + ' must be a normalized absolute path')
    if bool(result.get('organization_id')) != bool(result.get('instance_id')):
        raise ValueError('Brev targets require both organization and immutable instance ID')
    return result


def ssh_options():
    # Explicit paths override Brev aliases that otherwise discard known host keys.
    return ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'RequestTTY=no', '-o', 'ForwardAgent=no', '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
            '-o', 'UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'),
            '-o', 'GlobalKnownHostsFile=/etc/ssh/ssh_known_hosts']


class ChatExecution:
    def target_suggestions(self):
        """Read convenience/legacy records without migration, activation or probing."""
        candidates = []
        last = self.root / 'last-chat-target.json'
        if last.exists():
            candidates.append(('last chosen host', json.loads(last.read_text())))
        for name in ('state.json', 'compute-targets.json', 'config.json'):
            path = self.root / name
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            configs = ([row.get('config', {}) for row in data.get('machines', {}).values()] if name == 'state.json'
                       else list(data.get('targets', {}).values()) if name == 'compute-targets.json' else [data])
            for cfg in configs:
                if cfg.get('kind', 'brev') not in ('ssh', 'brev') or not cfg.get('remote_root'):
                    continue
                item = {'ssh_alias': cfg.get('ssh_host') if cfg.get('kind') == 'ssh' else cfg.get('instance'),
                        'runtime_root': cfg['remote_root'], 'output_root': cfg['remote_root'] + '/runs'}
                if cfg.get('kind', 'brev') == 'brev':
                    item.update(organization_id=cfg.get('organization_id'), instance_id=cfg.get('instance_id'))
                candidates.append(('legacy ' + name, item))
        suggestions = []
        seen = set()
        for source, value in candidates:
            try:
                value = target(value)
            except (TypeError, ValueError):
                continue
            key = json.dumps(value, sort_keys=True)
            if key not in seen:
                seen.add(key)
                suggestions.append({'source': source, 'target': value, 'verified': False})
        return {'suggestions': suggestions, 'detail': 'Suggestions only. Ask which host to use if unclear, then verify readiness.'}

    def named_exec(self, destination, command, timeout=60):
        return self.run(['ssh', *ssh_options(), '--', destination['ssh_alias'], command], timeout)

    def check_named_target(self, destination):
        destination = target(destination)
        if destination.get('instance_id'):
            from brev_provider import Brev
            row = Brev(self.run).check_context(destination['organization_id'], destination['instance_id'])
            if row.get('name') != destination['ssh_alias']:
                raise ValueError('The SSH alias must match the selected Brev instance name; refresh access using Brev CLI')
        physical = self.named_exec(destination, 'cat /etc/machine-id', 15).strip()
        if not re.fullmatch('[0-9a-f]{32}', physical):
            raise ValueError('Remote machine identity unavailable')
        cfg = {'remote_root': destination['runtime_root'], 'weight_paths': [destination['runtime_root'] + '/model-bundle/' + item['name'] for item in RECIPE['model_bundle']['files']]}
        class Probe:
            def target_exec(_, cfg, command, timeout=60):
                return self.named_exec(destination, command, timeout)
        result = inspect(Probe(), cfg)
        return dict(result, ready=all(result['checks'].values()), target=destination,
                    machine_identity=hashlib.sha256(physical.encode()).hexdigest())

    def submit_design_request(self, request_id, destination, compute_note=""):
        if not isinstance(compute_note, str) or len(compute_note) > 4000:
            raise ValueError('Keep the compute approval/context note under 4000 characters')
        request = self.get_design_request(request_id)
        destination = target(destination)
        directory = self.state / request_id
        # A short local lock freezes the host. No network call runs under it.
        with (directory / 'submission.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = directory / 'job.json'
            if path.exists():
                record = json.loads(path.read_text())
                if record.get('runtime_protocol') != 4 or record['target'] != destination:
                    raise ValueError('This request already belongs to another run or target')
            else:
                record = dict(job_id=request_id, snapshot_id=request_id, runtime_protocol=4,
                              target=destination, instance=destination['ssh_alias'], status='prepared', compute_note=compute_note,
                              request_checksum=request['request_checksum'], samples=request['samples'],
                              seed=request['seed'], generation=request['generation'], remote_dispatch_started=False)
                atomic(path, record)
        if record['remote_dispatch_started']:
            return self.check_chat_job(request_id)
        readiness = self.check_named_target(destination)
        if not readiness['ready']:
            raise ValueError('RFD4 setup required: ' + ', '.join(k for k, v in readiness['checks'].items() if not v))
        root = destination['runtime_root']
        remote = destination['output_root'] + '/' + request_id
        helper = Path(__file__).with_name('ssh_job.py').read_text()
        manifest = dict(request_checksum=request['request_checksum'], input_sha256=request['sha256'],
                        helper_sha256=hashlib.sha256(helper.encode()).hexdigest(), cwd=root + '/model',
                        argv=[root + '/model/.venv/bin/rfd4-generate', 'inputs=' + remote + '/input.cif',
                              'out_dir=' + remote + '/output', 'hydra.run.dir=' + remote + '/hydra',
                              'num_replicates=' + str(request['samples']), 'seed=' + str(request['seed']),
                              'batch_size=1', 'compile_lengths=null', 'prevalidate_inputs=true'] +
                             runtime_overrides(root) + overrides(request['generation']))
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        bundle = dict(manifest=manifest, launch_checksum=digest, helper=helper,
                      input=base64.b64encode((directory / 'input.cif').read_bytes()).decode())
        # Transfer the CIF as a file, not a giant SSH command-line argument.
        # Unique upload names prevent concurrent retries from replacing each other.
        import uuid
        upload_name = '.request-' + uuid.uuid4().hex + '.json'
        upload = directory / upload_name
        atomic(upload, bundle)
        remote_upload = destination['output_root'] + '/' + upload_name
        try:
            self.named_exec(destination, shlex.join(['mkdir', '-p', '--', destination['output_root']]), 30)
            self.run(['scp', *ssh_options(), '--', str(upload), destination['ssh_alias'] + ':' + remote_upload], 120)
        finally:
            upload.unlink(missing_ok=True)
        with (directory / 'submission.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            record = json.loads((directory / 'job.json').read_text())
            if record['remote_dispatch_started']:
                # Another caller owns this dispatch. Reconcile outside the lock.
                dispatch = False
            else:
                record.update(status='submitting', remote_dispatch_started=True, remote_dir=remote,
                              launch_checksum=digest, machine_identity=readiness['machine_identity'])
                atomic(directory / 'job.json', record)
                dispatch = True
        if not dispatch:
            return self.check_chat_job(request_id)
        atomic(self.root / 'last-chat-target.json', destination)
        command = shlex.join(['python3', '-B', '-c', helper, 'launch-file', remote, remote_upload])
        try:
            observed = json.loads(self.named_exec(destination, command, 120))
            return self.accept_chat_observation(record, observed)
        except Exception as error:
            # Launch may have happened. Leave the original record for reconciliation.
            record.update(status='submission_unknown', detail=str(error))
            return self.save_chat_job(record)

    def accept_chat_observation(self, record, observed):
        if observed.get('launch_checksum') != record['launch_checksum']:
            raise ValueError('Remote launch receipt mismatch')
        state = observed.get('state')
        if state not in ('running', 'completed', 'failed', 'submission_unknown', 'not_launched'):
            raise ValueError('Invalid remote job state')
        record.update(status='prepared' if state == 'not_launched' else state, receipt=observed)
        if state == 'not_launched':
            record['remote_dispatch_started'] = False
            record['detail'] = 'Original host confirms no launch receipt. The same request can retry; remote locking prevents duplicate execution.'
        elif observed.get('detail'):
            record['detail'] = observed['detail']
        else:
            record.pop('detail', None)
        return self.save_chat_job(record)

    def save_chat_job(self, record):
        directory = self.state / record['job_id']
        with (directory / 'submission.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = json.loads((directory / 'job.json').read_text())
            if current['status'] in ('completed', 'failed'):
                return current
            atomic(directory / 'job.json', record)
            return record

    def check_chat_job(self, job_id):
        record = self.read(job_id, 'job.json')
        if not record.get('remote_dispatch_started') or record['status'] in ('completed', 'failed'):
            return record
        destination = target(record['target'])
        physical = self.named_exec(destination, 'cat /etc/machine-id', 15).strip()
        if hashlib.sha256(physical.encode()).hexdigest() != record['machine_identity']:
            raise ValueError('SSH target changed; preserve the original run and inspect the connection')
        helper = Path(__file__).with_name('ssh_job.py').read_text()
        observed = json.loads(self.named_exec(destination, shlex.join(['python3', '-B', '-c', helper,
                              'status', record['remote_dir'], record['launch_checksum']])))
        return self.accept_chat_observation(record, observed)

    def collect_chat_job(self, job_id):
        import shutil
        import uuid
        from artifacts import REMOTE_MANIFEST, validate_manifest, verify
        record = self.check_chat_job(job_id)
        if record['status'] not in ('completed', 'failed'):
            raise ValueError('Wait for a confirmed terminal state before collecting or stopping compute')
        destination = target(record['target'])
        directory = self.state / job_id
        cached = directory / 'collection.json'
        if cached.exists():
            saved = json.loads(cached.read_text())
            if saved.get('state') == 'complete' and saved.get('log_hashes'):
                try:
                    for name, digest in saved['log_hashes'].items():
                        if name not in ('run.log', 'supervisor.log', 'receipt.json', 'launch.json'):
                            raise ValueError('Invalid saved log name')
                        if hashlib.sha256((directory / 'logs' / name).read_bytes()).hexdigest() != digest:
                            raise ValueError('Saved log changed')
                    files = verify(directory / 'results', saved['manifest']) if saved.get('manifest') else []
                    return {'job_id': job_id, 'status': record['status'], 'collection': 'complete',
                            'files': [str(p) for p in files], 'logs': [str(directory / 'logs' / n) for n in saved['log_hashes']]}
                except (OSError, ValueError):
                    pass  # Re-fetch corrupted local files if the original host is still reachable.
        physical = self.named_exec(destination, 'cat /etc/machine-id', 15).strip()
        if hashlib.sha256(physical.encode()).hexdigest() != record['machine_identity']:
            raise ValueError('SSH target changed; collect from the original run host')
        staging = directory / ('.collection-' + uuid.uuid4().hex)
        staging.mkdir(mode=0o700)
        try:
            remote = record['remote_dir']
            # Collect complete logs, including failure logs. Large logs remain on the
            # host for explicit retrieval rather than silently being truncated.
            log_reader = """import base64,json,sys
from pathlib import Path
root=Path(sys.argv[1]); logs={}
for name in ('run.log','supervisor.log','receipt.json','launch.json'):
 p=root/name
 if p.is_symlink(): raise ValueError('Symlinked log')
 if p.exists():
  if p.stat().st_size>32000000: raise ValueError('Log exceeds inline limit; retrieve it through SSH before stopping')
  logs[name]=base64.b64encode(p.read_bytes()).decode()
print(json.dumps(logs))
"""
            logs = json.loads(self.named_exec(destination, shlex.join(['python3', '-c', log_reader, remote]), 120))
            if 'receipt.json' not in logs:
                raise ValueError('Remote terminal receipt is missing')
            for name, data in logs.items():
                if name not in ('run.log', 'supervisor.log', 'receipt.json', 'launch.json'):
                    raise ValueError('Unexpected log name')
                (staging / name).write_bytes(base64.b64decode(data, validate=True))
            receipt = json.loads((staging / 'receipt.json').read_text())
            if receipt.get('launch_checksum') != record['launch_checksum'] or receipt.get('state') != record['status']:
                raise ValueError('Collected receipt does not match this terminal job')
            manifest = None
            if record['status'] == 'completed':
                source = remote + '/output/inference_samples'
                manifest = validate_manifest(json.loads(self.named_exec(destination,
                    shlex.join(['python3', '-c', REMOTE_MANIFEST, source]), 180)))
                self.run(['scp', '-r', *ssh_options(), '--', destination['ssh_alias'] + ':' + source, str(staging)], 300)
                verify(staging / 'inference_samples', manifest)
                atomic(staging / 'inference_samples' / '.manifest.json', manifest)
            # Only local atomic publication is locked; network and verification above are not.
            with (directory / 'collection.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result_dir = directory / 'results'
                if manifest:
                    if result_dir.exists():
                        verify(result_dir, manifest)
                    else:
                        (staging / 'inference_samples').rename(result_dir)
                log_dir = directory / 'logs'
                log_dir.mkdir(exist_ok=True)
                for name in logs:
                    (staging / name).replace(log_dir / name)
                atomic(directory / 'collection.json', {'state': 'complete', 'job_status': record['status'],
                       'manifest': manifest, 'log_hashes': {name: hashlib.sha256((log_dir / name).read_bytes()).hexdigest() for name in logs}})
            return {'job_id': job_id, 'collection': 'complete', 'status': record['status'],
                    'files': [str(directory / 'results' / item['path']) for item in manifest['files']] if manifest else [],
                    'logs': [str(directory / 'logs' / name) for name in logs]}
        finally:
            shutil.rmtree(staging)

"""BioNeMo-owned, process-safe compute catalog. No external plugin or daemon."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import uuid


def atomic(path, value):
    temp = path.with_name(uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w') as handle:
            temp.chmod(0o600)
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    finally:
        temp.unlink(missing_ok=True)


def effective_access(alias, run):
    # ssh -G resolves configuration without contacting the remote machine.
    output = run(['ssh', '-G', '-o', 'BatchMode=yes', '--', alias], timeout=10)
    values = {}
    for line in output.splitlines():
        key, _, value = line.partition(' ')
        values.setdefault(key, []).append(value)
    one = lambda key, default='': values.get(key, [default])[0]
    if not one('hostname') or not one('user') or not one('port'):
        raise ValueError('Cannot resolve SSH configuration; reconnect this target in chat')
    digest = lambda value: 'sha256:' + hashlib.sha256(value.encode()).hexdigest()
    return dict(alias=alias, host=one('hostname'), user=one('user'), port=int(one('port')),
        host_key_policy=one('stricthostkeychecking', 'unknown'),
        proxy_fingerprint=digest(one('proxycommand', 'none') + '\0' + one('proxyjump', 'none')),
        identity_fingerprint=digest(json.dumps({k: values.get(k, []) for k in
            ['identityfile', 'certificatefile', 'identityagent', 'identitiesonly', 'userknownhostsfile', 'globalknownhostsfile']})))


def verify_access(expected, run):
    current = effective_access(expected['alias'], run)
    # Historical job records have fewer fields. Validate every field they pinned.
    if any(current.get(k) != v for k, v in expected.items()):
        raise ValueError('SSH identity changed since registration; reconnect in chat and review again')


class Catalog:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'compute-targets.json'

    def read(self):
        if not self.path.exists(): return {'version': 1, 'targets': {}}
        data = json.loads(self.path.read_text())
        if data.get('version') != 1 or not isinstance(data.get('targets'), dict):
            raise ValueError('Unsupported BioNeMo compute catalog; preserve it and check the plugin version')
        return data

    def put(self, cfg, target_id=None, preserve=False):
        clean = {k:v for k,v in cfg.items() if k != 'target_id'}
        target_id = target_id or cfg['instance']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', target_id):
            raise ValueError('Invalid compute target ID')
        with (self.root / 'compute-targets.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = self.read()
            if preserve and target_id in data['targets'] and data['targets'][target_id] != clean:
                suffix = hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()[:12]
                target_id = target_id[:80] + '-' + suffix
            data['targets'][target_id] = clean
            atomic(self.path, data)
        return dict(clean, target_id=target_id)

    def resolve(self, target_id):
        value = self.read()['targets'].get(target_id)
        if value is None: raise ValueError('Compute target is no longer registered; select another in chat')
        return dict(value, target_id=target_id)

    def verify(self, cfg):
        if cfg.get('target_id') and self.resolve(cfg['target_id']) != cfg:
            raise ValueError('Compute configuration changed; select the target and review again')

    def migrate(self, path):
        # Only plugin-owned selected configs; immutable plans/jobs are never rewritten.
        with (self.root / 'compute-migration.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            cfg = json.loads(path.read_text())
            if cfg.get('target_id'): return cfg
            old = cfg.pop('registry_target', None)
            if old:
                if old.get('executor') != 'local_process':
                    raise ValueError('This saved target requires a scheduler; direct GPU execution is required')
                cfg['title'] = old.get('title', cfg['instance'])
                if old.get('host_access'): cfg['ssh_access'] = old['host_access']
            cfg = self.put(cfg, preserve=True)
            backup = path.with_suffix(path.suffix + '.before-standalone')
            if not backup.exists():
                backup.write_bytes(path.read_bytes()); backup.chmod(0o600)
            atomic(path, cfg)
            return cfg


def linux_machine_identity(cfg, run):
    """Identify the Linux executor through its authenticated transport.

    Host aliases and client key paths are mutable access settings, not identity.
    A copied OS machine-id conservatively shares a reservation rather than
    permitting two launches. No credentials or raw machine-id are persisted.
    """
    command = 'cat /etc/machine-id'
    if cfg['kind'] == 'ssh':
        from ssh_transport import execute
        return machine_identity_from_output(execute(cfg, command, run, 15))
    elif cfg['kind'] == 'local':
        args = ['cat', '/etc/machine-id']
    else:
        raise ValueError('Resolve Brev identity through its explicit organization and instance')
    return machine_identity_from_output(run(args, timeout=15))


def machine_identity_from_output(output):
    value = output.strip().lower()
    if not re.fullmatch(r'[0-9a-f]{32}', value) or value == '0' * 32:
        raise ValueError('Cannot verify Linux machine identity; connect to a supported Linux GPU host')
    return {'linux_machine_id_sha256': hashlib.sha256(value.encode()).hexdigest()}

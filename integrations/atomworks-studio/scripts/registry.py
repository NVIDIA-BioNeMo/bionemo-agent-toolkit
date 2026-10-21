# Data-plane SSH never delegates to a provider command that can start a VM.
from pathlib import Path
import re

import registry as registry


def access(cfg, run, *, trust_on_first_use=False):
    brev = cfg.get('kind') == 'brev'
    if trust_on_first_use and not brev:
        raise ValueError('Automatic first-use trust is supported only during Brev access refresh')
    alias = cfg['instance'] if brev else cfg['ssh_host']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,200}', alias):
        raise ValueError('Invalid saved SSH alias')
    expected = cfg.get('ssh_access')
    if brev and not expected:
        raise ValueError('Refresh and verify this Brev machine’s SSH access in chat before connecting; no machine was started')
    if expected and expected.get('alias') != alias:
        raise ValueError('Saved SSH access belongs to a different alias; reconnect and verify this target')
    if expected:
        registry.verify_access(expected, run)
    options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
               '-o', 'StrictHostKeyChecking=' + ('accept-new' if trust_on_first_use else 'yes'), '-o', 'ForwardAgent=no',
               '-o', 'ControlMaster=no', '-o', 'ControlPath=none']
    if brev:
        # Brev-generated aliases discard host keys. Use the user's established
        # trust store instead. Only explicit access refresh can enroll a new key;
        # changed keys fail in both modes. Jobs/copies always use strict checking.
        options += ['-o', 'UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'),
                    '-o', 'GlobalKnownHostsFile=/etc/ssh/ssh_known_hosts']
    return alias, options


def execute(cfg, command, run, timeout, *, trust_on_first_use=False):
    alias, options = access(cfg, run, trust_on_first_use=trust_on_first_use)
    return run(['ssh', *options, '--', alias, command], timeout)


def copy(cfg, source, destination, download, run, timeout):
    alias, options = access(cfg, run)
    paths = ([f'{alias}:{source}', str(destination)] if download
             else [str(source), f'{alias}:{destination}'])
    return run(['scp', '-r', *options, '--', *paths], timeout)


# BioNeMo-owned, process-safe compute catalog. No external plugin or daemon.
import fcntl
import hashlib
import json
import os
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
        pass
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


# Explicit, non-provisioning Brev refresh with approved first-use key trust.
from brev_provider import Brev

from contextlib import contextmanager


@contextmanager
def lease(backend,operation_id):
    op=backend.managed.operation(operation_id)
    directory=backend.state/'access-refresh-locks'
    directory.mkdir(exist_ok=True)
    with (directory/(op['id']+'.lock')).open('a') as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('The original access refresh is still running; wait before recovery') from None
        yield handle


def recover(backend,operation_id):
    """Fence a dead synchronous controller; never repeat its local side effects."""
    with lease(backend,operation_id):
        state=backend.managed
        op=state.operation(operation_id)
        if op['action']!='connect':
            raise ValueError('Not an access refresh operation')
        if op['state'] in ('succeeded','failed','cancelled'):
            return op
        if op['state']=='requested':
            raise ValueError('Access refresh has not started; no recovery is needed')
        return state.transition(operation_id,'failed',evidence={
            'kind':'access_refresh_controller_ended',
            'detail':'Original refresh controller lease is free. Local SSH configuration may have changed; access was not accepted. Use a new explicitly approved refresh operation.'},release_reservation=True)


def refresh(backend, operation_id, machine_id):
    with lease(backend,operation_id) as handle:
        return _refresh_locked(backend,operation_id,machine_id,handle.fileno())


def _refresh_locked(backend, operation_id, machine_id,lease_fd):
    state=backend.managed
    original=state.operation(operation_id)
    if original['state'] in ('succeeded','failed','cancelled'):
        return original
    if original['dispatched'] or original['state']=='authorized':
        raise ValueError('Recover the original access refresh before requesting a new attempt; refresh was not repeated')
    machine=state.machine(machine_id)
    cfg=machine['config']
    if cfg['kind']!='brev' or not cfg.get('organization_id'):
        raise ValueError('Access refresh requires a saved Brev organization and instance')
    provider=Brev(backend.run)
    def verify_provider():
        if provider.current_org()!=cfg['organization_id']:
            raise ValueError('Select the saved Brev organization before refreshing; no context was changed')
        row=provider.check_context(cfg['organization_id'],cfg['instance_id'])
        if row.get('name')!=cfg['instance'] or row.get('status')!='RUNNING':
            raise ValueError('The saved Brev instance must be running with its verified name; refresh never starts a machine')
        return row
    verify_provider()
    op=state.choose(operation_id,'connect',machine_id)
    if op['machine_revision']!=machine['revision']:
        raise ValueError('Machine changed before access refresh')
    state.transition(operation_id,'authorized',evidence={'kind':'explicit_access_refresh_tool_call','machine_id':machine_id})
    try:
        state.reserve(machine_id,operation_id,'connect')
        jobs=backend.machine_jobs(machine_id)
        if jobs['active_jobs'] or jobs['unresolved_active_jobs']:
            raise ValueError('Reconcile active or unknown jobs before refreshing SSH access')
        verify_provider()
        state.transition(operation_id,'dispatched')
        # Local SSH/key/helper configuration may change. No exec, copy, power,
        # provisioning command is permitted here. The following SSH probe may
        # remember a first-use key, but can never replace an existing key.
        # The CLI inherits the lease: if this controller dies, recovery remains
        # blocked until that child exits, not merely until its parent disappears.
        backend.run(['brev','refresh'],timeout=60,pass_fds=(lease_fd,))
        current=state.operation(operation_id)
        if current['cancel_requested'] or state.selection(op['session_id'])['revision']!=op['selection_revision']:
            raise ValueError('Access refresh changed or was cancelled; access was not accepted')
        verify_provider()
        access=registry.effective_access(cfg['instance'],backend.run)
        if access['host']==cfg['instance']:
            raise ValueError('Brev did not resolve the saved SSH alias; no connection was attempted')
        candidate=dict(cfg,ssh_access=access)
        identity=registry.machine_identity_from_output(execute(candidate,'cat /etc/machine-id',backend.run,15,trust_on_first_use=True))
        verify_provider()
        # Verify again after the probe, but commit the original probed snapshot.
        registry.verify_access(access,backend.run)
        return state.accept_access(operation_id,candidate,identity)
    except Exception as error:
        current=state.operation(operation_id)
        if current['state'] not in ('succeeded','failed','cancelled'):
            state.transition(operation_id,'failed',evidence={'kind':'access_not_accepted','detail':str(error)},release_reservation=True)
        raise

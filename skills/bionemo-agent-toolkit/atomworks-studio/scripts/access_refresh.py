"""Explicit, non-provisioning Brev refresh with approved first-use key trust."""
from brev_provider import Brev
import registry
from ssh_transport import execute
from contextlib import contextmanager
import fcntl


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

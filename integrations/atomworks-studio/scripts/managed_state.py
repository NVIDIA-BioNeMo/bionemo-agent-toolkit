"""Versioned single-executor compute state; no provider or process side effects.

All transactions serialize through the maintenance gate. Durable reservations
outlive this short filesystem lock and are never released by elapsed time.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import hashlib
from pathlib import Path
import re
import uuid

from registry import atomic

SCHEMA = 2
BACKEND_PROTOCOL = 3
TERMINAL = {'succeeded', 'failed', 'cancelled'}
ACTIONS = {'connect', 'create', 'start', 'setup', 'stop', 'claim'}
TRANSITIONS = {
    'requested': {'authorized', 'cancelled', 'needs_attention'},
    'authorized': {'dispatched', 'cancelled', 'failed', 'needs_attention', 'succeeded'},
    'dispatched': {'succeeded', 'failed', 'needs_attention'},
    'needs_attention': {'authorized', 'succeeded', 'failed', 'cancelled'},
}


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value):
        raise ValueError('Invalid compute identifier')
    return value


def legacy_snapshot(root):
    paths = [root / 'compute-targets.json', root / 'config.json']
    paths += sorted((root / 'sessions').glob('*.compute.json'))
    paths += sorted((root / 'state').glob('*/job.json'))
    sources = {}
    for path in paths:
        if path.exists():
            raw = path.read_bytes()
            sources[str(path.relative_to(root))] = (raw, json.loads(raw))
    return sources


class State:
    def __init__(self, root):
        # A distinct directory prevents legacy binaries from interpreting v2 data.
        self.root = Path(root) / 'managed-v2'
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'state.json'

    @contextmanager
    def transaction(self):
        with (self.root / 'maintenance.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text()) if self.path.exists() else {
                'schema': SCHEMA, 'minimum_backend_protocol': BACKEND_PROTOCOL, 'executor_id': uuid.uuid4().hex,
                'machines': {}, 'sessions': {}, 'operations': {}, 'reservations': {}}
            if data.get('schema') != SCHEMA:
                raise ValueError('Incompatible compute schema; update the plugin before changing state')
            required = data.get('minimum_backend_protocol', SCHEMA)
            if type(required) is not int or required > BACKEND_PROTOCOL or required < 1:
                raise ValueError('Incompatible backend protocol; update the plugin before changing state')
            yield data
            atomic(self.path, data)

    def snapshot(self):
        with self.transaction() as data:
            return json.loads(json.dumps(data))

    def machine(self, machine_id):
        with self.transaction() as data:
            return dict(data['machines'][identifier(machine_id)])

    @staticmethod
    def _physical(machine):
        return machine.get('physical_identity') or machine['identity'].get('linux_machine_id_sha256')

    def bind_physical_identity(self, machine_id, identity):
        """Attach transport-verified identity without rewriting provider identity.

        Separate SSH/Brev access records share the same reservation domain.
        A changed physical host is never silently accepted.
        """
        fingerprint=identity.get('linux_machine_id_sha256')
        if not isinstance(fingerprint,str) or not fingerprint:
            raise ValueError('A verified Linux machine identity is required')
        with self.transaction() as data:
            machine=data['machines'][identifier(machine_id)]
            previous=self._physical(machine)
            if previous and previous!=fingerprint:
                raise ValueError('Physical machine identity changed; reconnect and review a new target')
            if machine_id in data['reservations']:
                for key,other in data['machines'].items():
                    if key!=machine_id and self._physical(other)==fingerprint and key in data['reservations']:
                        raise ValueError('This physical machine is reserved through another saved connection: '+key)
            machine['physical_identity']=fingerprint
            return dict(machine)

    def accept_access(self, operation_id, config, physical_identity):
        """Commit the exact access snapshot probed by a reserved connect action."""
        fingerprint=physical_identity.get('linux_machine_id_sha256')
        if not fingerprint:
            raise ValueError('Verified physical identity required')
        with self.transaction() as data:
            op=data['operations'][identifier(operation_id)]
            machine=data['machines'][op['machine_id']]
            selection=self._selection(data,op['session_id'])
            reservation=data['reservations'].get(machine['id'],{})
            if (op['action']!='connect' or op['state']!='dispatched' or op['cancel_requested']
                    or selection['revision']!=op['selection_revision']
                    or machine['revision']!=op['machine_revision']
                    or reservation.get('owner_id')!=operation_id):
                raise ValueError('Access refresh changed or was cancelled; inspect the current operation')
            previous=self._physical(machine)
            if previous and previous!=fingerprint:
                raise ValueError('Physical machine identity changed; do not reuse this target')
            for key,other in data['machines'].items():
                if key!=machine['id'] and self._physical(other)==fingerprint and key in data['reservations']:
                    raise ValueError('Physical machine busy through another saved connection')
            # Only access metadata can change; runtime/provider identity stays fixed.
            expected=dict(machine['config'],ssh_access=config.get('ssh_access'))
            if config!=expected:
                raise ValueError('Access refresh cannot change runtime or provider configuration')
            machine.update(config=config,physical_identity=fingerprint,revision=machine['revision']+1)
            op.update(state='succeeded',updated_at=now())
            op['attempts'].append({'from':'dispatched','to':'succeeded','at':now(),
                                   'evidence':{'kind':'trusted_access_verified','machine_revision':machine['revision']}})
            del data['reservations'][machine['id']]
            return json.loads(json.dumps(op))

    def register(self, identity, config, session_id=None, expected_revision=None):
        """Identity is verified transport/provider identity, never a display name."""
        if not identity:
            raise ValueError('A verified machine identity is required')
        with self.transaction() as data:
            if session_id is not None and self._selection(data, session_id)['revision'] != expected_revision:
                raise ValueError('Selection changed; inspect the current session')
            matches = [m for m in data['machines'].values() if m['identity'] == identity]
            if matches:
                machine = matches[0]
                if machine['config'] != config:
                    if machine['id'] in data['reservations']:
                        raise ValueError('Machine is reserved; reconcile its operation before updating')
                    machine.update(config=config, revision=machine['revision'] + 1)
            else:
                machine = {'id': uuid.uuid4().hex, 'identity': identity,
                           'revision': 1, 'config': config, 'created_at': now()}
                data['machines'][machine['id']] = machine
            if session_id is not None:
                self._select(data, session_id, machine['id'], expected_revision)
            return json.loads(json.dumps(machine))

    @staticmethod
    def _identify(data, machine_id, identity):
        machine = data['machines'][identifier(machine_id)]
        previous = machine['identity']
        if previous == identity:
            return dict(machine)
        if 'linux_machine_id_sha256' in previous:
            raise ValueError('Machine identity changed; do not reuse this target')
        duplicate = next((m for m in data['machines'].values()
                          if m['id'] != machine_id and m['identity'] == identity), None)
        if duplicate:
            raise ValueError('This machine already exists as ' + duplicate['id'] + '; reconcile duplicate legacy records')
        if machine_id in data['reservations']:
            raise ValueError('Reconcile the reserved operation before changing identity')
        machine.update(identity=identity, revision=machine['revision'] + 1)
        return dict(machine)


    @staticmethod
    def _selection(data, session_id):
        return data['sessions'].get(identifier(session_id), {
            'session_id': session_id, 'machine_id': None, 'previous_machine_id': None,
            'revision': 0})

    def selection(self, session_id):
        with self.transaction() as data:
            return dict(self._selection(data, session_id))

    @classmethod
    def _select(cls, data, session_id, machine_id, expected_revision):
        previous = cls._selection(data, session_id)
        if previous['revision'] != expected_revision:
            raise ValueError('Selection changed; inspect the current session')
        if machine_id is not None and identifier(machine_id) not in data['machines']:
            raise ValueError('Unknown machine')
        selection = dict(previous, machine_id=machine_id,
            previous_machine_id=previous['machine_id'] or previous['previous_machine_id'],
            revision=expected_revision + 1, updated_at=now())
        data['sessions'][session_id] = selection
        for op in data['operations'].values():
            if op['session_id'] != session_id or op['state'] in TERMINAL:
                continue
            if (op['action'] == 'connect' and not op['dispatched'] and machine_id
                    and op['selection_revision'] == expected_revision
                    and op['machine_id'] in (None, machine_id)):
                op.update(state='succeeded', updated_at=now(),
                          detail='Saved machine selected; connection and model checks are separate.')
            else:
                op.update(cancel_requested=True, state='needs_attention' if op['dispatched'] else 'cancelled',
                          updated_at=now(), detail='Session selection changed; reconcile any dispatched action.')
            if not op['dispatched'] and op['state'] in TERMINAL:
                key=op['machine_id'] or 'create:' + op['id']
                reservation=data['reservations'].get(key)
                if reservation and reservation['owner_id']==op['id']:
                    del data['reservations'][key]
        return dict(selection)

    def select(self, session_id, machine_id, expected_revision, identity=None, machine_revision=None):
        with self.transaction() as data:
            if self._selection(data, session_id)['revision'] != expected_revision:
                raise ValueError('Selection changed; inspect the current session')
            if machine_revision is not None and data['machines'][machine_id]['revision'] != machine_revision:
                raise ValueError('Machine changed during identity verification')
            if identity is not None:
                self._identify(data, machine_id, identity)
            return self._select(data, session_id, machine_id, expected_revision)

    def request(self, session_id, action, machine_id, expected_revision):
        if action not in ACTIONS:
            raise ValueError('Unsupported compute action')
        with self.transaction() as data:
            selection = self._selection(data, session_id)
            if selection['revision'] != expected_revision:
                raise ValueError('Selection changed; inspect the current session')
            if action != 'create' and not (action == 'connect' and machine_id is None) and machine_id not in data['machines']:
                raise ValueError('Select a saved machine')
            for op in data['operations'].values():
                if op['session_id'] == session_id and op['state'] not in TERMINAL:
                    if (op['action'], op['machine_id'], op['selection_revision']) == (action, machine_id, expected_revision):
                        return dict(op)
                    raise ValueError('Another operation needs reconciliation: ' + op['id'])
            op = {'id': uuid.uuid4().hex, 'session_id': session_id, 'action': action,
                  'machine_id': machine_id, 'selection_revision': expected_revision,
                  'machine_revision': data['machines'][machine_id]['revision'] if machine_id else None,
                  'state': 'requested', 'cancel_requested': False, 'dispatched': False,
                  'created_at': now(), 'updated_at': now(), 'attempts': []}
            data['operations'][op['id']] = op
            return dict(op)

    def choose(self, operation_id, action, machine_id):
        if action not in ACTIONS:
            raise ValueError('Unsupported compute action')
        with self.transaction() as data:
            op = data['operations'][identifier(operation_id)]
            if op['dispatched'] or op['cancel_requested'] or op['state'] not in ('requested','needs_attention'):
                raise ValueError('Reconcile this operation before choosing another action')
            if self._selection(data, op['session_id'])['revision'] != op['selection_revision']:
                raise ValueError('Session selection changed')
            if machine_id not in data['machines'] and not (action=='create' and machine_id is None):
                raise ValueError('Unknown machine')
            op.update(action=action, machine_id=machine_id,
                      machine_revision=data['machines'][machine_id]['revision'] if machine_id else None,
                      state='requested', updated_at=now())
            op.pop('review', None)
            return dict(op)

    def operation(self, operation_id):
        with self.transaction() as data:
            op = data['operations'][identifier(operation_id)]
            if op['state'] == 'requested' and (datetime.now(timezone.utc) - datetime.fromisoformat(op['updated_at'])).total_seconds() > 120:
                op.update(state='needs_attention', updated_at=now(),
                          detail='Chat has not completed this request. Resume it in chat; no machine was started.')
            return json.loads(json.dumps(op))

    def transition(self, operation_id, state, *, evidence=None, expected_review_checksum=None, release_reservation=False):
        with self.transaction() as data:
            op = data['operations'][identifier(operation_id)]
            if expected_review_checksum is not None:
                actual = hashlib.sha256(json.dumps(op.get('review'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                if actual != expected_review_checksum:
                    raise ValueError('Review changed before action authorization or dispatch')
            if state not in TRANSITIONS.get(op['state'], set()):
                raise ValueError('Invalid operation transition')
            if state == 'succeeded' and op['state']=='authorized':
                desired={'start':'running','stop':'stopped'}.get(op['action'])
                observation=(evidence or {}).get('observation',{})
                review=op.get('review',{})
                if not desired or not expected_review_checksum or (evidence or {}).get('kind')!='already_at_provider_state' or observation.get('power')!=desired or observation.get('instance_id')!=review.get('instance_id') or observation.get('organization_id')!=review.get('organization_id'):
                    raise ValueError('Fresh matching provider evidence is required for a no-op completion')
            if state in {'authorized', 'dispatched'}:
                if op['cancel_requested']:
                    raise ValueError('Cancellation requested; reconcile the external outcome')
                selection = self._selection(data, op['session_id'])
                if selection['revision'] != op['selection_revision']:
                    raise ValueError('Stale operation; session selection changed')
                if op['machine_id'] and data['machines'][op['machine_id']]['revision'] != op['machine_revision']:
                    raise ValueError('Stale operation; machine changed')
            if state == 'authorized' and not evidence:
                raise ValueError('Explicit action authorization is required')
            if op['dispatched'] and state in {'authorized', 'cancelled', 'succeeded', 'failed'} and not evidence:
                raise ValueError('Reconcile dispatched effects before continuing')
            if state == 'dispatched':
                owner = data['reservations'].get(op['machine_id'] or 'create:' + op['id'])
                if not owner or owner['owner_id'] != op['id']:
                    raise ValueError('Reserve the machine before dispatch')
                op['dispatched'] = True
                if op['action']=='setup' and op.get('review',{}).get('phase')!='prepare_archives':
                    data['machines'][op['machine_id']]['runtime_setup_operation']=op['id']
            op['attempts'].append({'from': op['state'], 'to': state, 'at': now(), 'evidence': evidence})
            op.update(state=state, updated_at=now())
            if release_reservation:
                if state not in TERMINAL or not evidence:
                    raise ValueError('Reservation release requires a reconciled terminal outcome')
                key=op['machine_id'] or 'create:' + op['id']
                reservation=data['reservations'].get(key)
                if reservation and reservation['owner_id']==op['id']:
                    del data['reservations'][key]
            return json.loads(json.dumps(op))

    def cancel(self, operation_id):
        with self.transaction() as data:
            op = data['operations'][identifier(operation_id)]
            if op['state'] in TERMINAL:
                return dict(op)
            op['cancel_requested'] = True
            op['state'] = 'needs_attention' if op['dispatched'] else 'cancelled'
            op['updated_at'] = now()
            if not op['dispatched']:
                key=op['machine_id'] or 'create:' + op['id']
                reservation=data['reservations'].get(key)
                if reservation and reservation['owner_id']==op['id']:
                    del data['reservations'][key]
            return dict(op)

    def dispatch_executor_confirmation(self, operation_id, review_checksum):
        """Authorize one noncreating confirmation at its actual dispatch boundary."""
        from executor_ownership import checksum
        with self.transaction() as data:
            op=data['operations'][identifier(operation_id)]
            machine=data['machines'][op['machine_id']]
            reservation=data['reservations'].get(machine['id'],{})
            selection=self._selection(data,op['session_id'])
            if (op['action']!='claim' or not op['dispatched'] or op['state'] not in ('dispatched','needs_attention')
                    or op['cancel_requested'] or op.get('confirmation_dispatched')
                    or checksum(op.get('review'))!=review_checksum
                    or reservation.get('owner_id')!=operation_id or reservation.get('purpose')!='claim'
                    or machine['revision']!=op['machine_revision'] or selection['revision']!=op['selection_revision']):
                raise ValueError('Ownership confirmation was cancelled, changed or already dispatched; inspect the original operation')
            op['confirmation_dispatched']=True
            op['attempts'].append({'at':now(),'evidence':{'kind':'ownership_confirmation_dispatched','review_checksum':review_checksum}})

    def complete_executor_claim(self, operation_id, review_checksum, observation):
        """Commit a verified owner receipt and reconciled terminal outcome together."""
        from executor_ownership import checksum,validate
        with self.transaction() as data:
            op=data['operations'][identifier(operation_id)];review=op.get('review',{})
            owner=validate(observation.get('owner'))
            if (op['action']!='claim' or not op['dispatched'] or op['state'] not in ('dispatched','needs_attention')
                    or checksum(review)!=review_checksum or observation.get('state')!='owned'
                    or observation.get('owner_checksum')!=checksum(owner) or owner!=review.get('owner')):
                raise ValueError('Executor ownership receipt does not match its dispatched review')
            machine=data['machines'][op['machine_id']]
            reservation=data['reservations'].get(machine['id'],{})
            if reservation.get('owner_id')!=operation_id or machine['revision']!=op['machine_revision']:
                raise ValueError('Executor claim no longer owns the reviewed machine')
            receipt={'owner':owner,'owner_checksum':checksum(owner),'brev':review.get('brev'),'operation_id':operation_id}
            prior=machine.get('executor_ownership')
            if prior and (prior['owner']!=owner or prior.get('brev')!=receipt['brev']):
                raise ValueError('Existing executor ownership cannot be replaced')
            machine['executor_ownership']=receipt
            op['attempts'].append({'from':op['state'],'to':'succeeded','at':now(),'evidence':{'kind':'protected_executor_owner_observed','owner_checksum':checksum(owner)}})
            op.update(state='succeeded',updated_at=now())
            del data['reservations'][machine['id']]
            return json.loads(json.dumps(op))

    def complete_setup(self, operation_id, review_checksum, acceptance, weight_paths):
        """Commit the verified runtime and terminal receipt together."""
        with self.transaction() as data:
            op=data['operations'][identifier(operation_id)]
            review=op.get('review',{})
            actual=hashlib.sha256(json.dumps(review,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if op['action']!='setup' or not op['dispatched'] or op['state'] not in ('dispatched','needs_attention') or actual!=review_checksum:
                raise ValueError('Setup operation changed before completion')
            from setup_acceptance import validate
            if validate(review,acceptance)!=weight_paths:
                raise ValueError('Setup checkpoint paths changed')
            machine=data['machines'][op['machine_id']]
            owner=data['reservations'].get(machine['id'])
            if not owner or owner['owner_id']!=operation_id or machine['revision']!=op['machine_revision']:
                raise ValueError('Setup no longer owns the reviewed machine revision')
            if acceptance.get('operation_id')!=operation_id or acceptance.get('ready') is not True or acceptance.get('stage')!='accepted' or acceptance.get('recipe_id')!=review['recipe_id'] or acceptance.get('weight_paths')!=weight_paths:
                raise ValueError('Setup acceptance does not match the reviewed runtime')
            machine['config'].update(weight_paths=list(weight_paths),runtime_recipe=review['recipe_id'])
            machine['revision']+=1
            machine['setup_acceptance']=acceptance
            op['attempts'].append({'from':op['state'],'to':'succeeded','at':now(),'evidence':{'kind':'setup_smoke_accepted','acceptance':acceptance}})
            op.update(state='succeeded',updated_at=now())
            del data['reservations'][machine['id']]
            return json.loads(json.dumps(op))

    def reserve(self, machine_id, owner_id, purpose):
        if purpose not in ACTIONS | {'run'}:
            raise ValueError('Unsupported reservation purpose')
        identifier(owner_id)
        with self.transaction() as data:
            if machine_id not in data['machines'] and machine_id != 'create:' + owner_id:
                raise ValueError('Unknown machine')
            operation=data['operations'].get(owner_id)
            if operation:
                expected_machine=operation['machine_id'] or 'create:' + owner_id
                selection=self._selection(data,operation['session_id'])
                if operation['state']!='authorized' or operation['cancel_requested'] or operation['action']!=purpose or expected_machine!=machine_id or selection['revision']!=operation['selection_revision']:
                    raise ValueError('Operation no longer authorizes this reservation')
            previous = data['reservations'].get(machine_id)
            machine=data['machines'].get(machine_id)
            physical=self._physical(machine) if machine else None
            if physical:
                for key,other in data['machines'].items():
                    if key!=machine_id and self._physical(other)==physical and key in data['reservations']:
                        raise ValueError('Physical machine busy through another saved connection: '+key)
            if previous and previous['owner_id'] != owner_id:
                raise ValueError('Machine busy or outcome unknown: ' + previous['owner_id'])
            reservation = previous or {'owner_id': owner_id, 'purpose': purpose, 'created_at': now()}
            data['reservations'][machine_id] = reservation
            return dict(reservation)

    def reconcile_undispatched_run(self, record):
        """Release only this failed run's lease using explicit no-dispatch evidence."""
        if record.get('status')!='failed' or record.get('dispatch_not_started') is not True or record.get('remote_dispatch_started') is not False:
            raise ValueError('Missing authoritative no-dispatch evidence')
        job_id=identifier(record['job_id']);machine_id=identifier(record['machine_id'])
        with self.transaction() as data:
            reservation=data['reservations'].get(machine_id)
            if not reservation:return False
            if reservation.get('owner_id')!=job_id or reservation.get('purpose')!='run':return False
            del data['reservations'][machine_id]
            return True

    def release(self, machine_id, owner_id, evidence):
        if not evidence:
            raise ValueError('Reconciled completion evidence is required')
        with self.transaction() as data:
            previous = data['reservations'].get(machine_id)
            if not previous or previous['owner_id'] != owner_id:
                raise ValueError('Reservation owner changed')
            op = data['operations'].get(owner_id)
            if op and op['state'] not in TERMINAL:
                raise ValueError('Operation still needs reconciliation')
            del data['reservations'][machine_id]

    def migrate_legacy(self):
        """Import legacy metadata once, without selecting compute or touching jobs.

        Caller must quiesce legacy writers before activation. Original files are
        retained; backups and journal are inside the isolated v2 directory.
        Unknown identities remain unresolved, never guessed from a name.
        """
        legacy = self.root.parent
        with self.transaction() as data:
            if data.get('migration', {}).get('state') == 'complete':
                return dict(data['migration'])
            sources = legacy_snapshot(legacy)
            backups = self.root / 'legacy-backup'
            for relative, (raw, _) in sources.items():
                backup = backups / relative
                backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if backup.exists() and backup.read_bytes() != raw:
                    raise ValueError('Legacy state changed during migration; stop old backends and reconcile')
                if not backup.exists():
                    with backup.open('xb') as handle:
                        handle.write(raw)
                    backup.chmod(0o600)
            unresolved = []
            mapping = {}

            def import_config(cfg, source):
                if not isinstance(cfg, dict):
                    unresolved.append({'source': source, 'reason': 'Invalid legacy configuration'})
                    return None
                kind = cfg.get('kind', 'brev')
                old = cfg.get('registry_target') or {}
                if old and old.get('executor') != 'local_process':
                    unresolved.append({'source': source, 'reason': 'Legacy scheduler target is unsupported'})
                    return None
                access = cfg.get('ssh_access') or old.get('host_access')
                if kind == 'ssh' and access:
                    identity = {'transport': 'ssh', 'access': access}
                elif kind == 'brev' and cfg.get('instance_id') and cfg.get('organization_id'):
                    identity = {'provider': 'brev', 'organization_id': cfg['organization_id'], 'instance_id': cfg['instance_id']}
                elif kind == 'local':
                    identity = {'transport': 'local', 'executor_id': data['executor_id']}
                else:
                    unresolved.append({'source': source, 'reason': 'Verified identity or Brev organization missing'})
                    return None
                matches = [m for m in data['machines'].values() if m['identity'] == identity]
                if matches:
                    machine = matches[0]
                    # Different runtime settings cannot silently replace the first.
                    ignored = {'target_id', 'title', 'registry_target', 'instance'}
                    normalized = lambda c: {k: v for k, v in c.items() if k not in ignored}
                    if normalized(machine['config']) != normalized(cfg):
                        unresolved.append({'source': source, 'reason': 'Conflicting settings for the same machine'})
                        return None
                else:
                    machine = {'id': uuid.uuid4().hex, 'identity': identity,
                               'revision': 1, 'config': cfg, 'created_at': now()}
                    data['machines'][machine['id']] = machine
                if cfg.get('target_id'):
                    key = cfg['target_id']
                    if key in mapping and mapping[key] != machine['id']:
                        mapping[key] = None
                    else:
                        mapping[key] = machine['id']
                return machine['id']

            catalog = sources.get('compute-targets.json', (None, {'targets': {}}))[1]
            if catalog.get('version', 1) != 1:
                raise ValueError('Unsupported legacy catalog version')
            for key, cfg in catalog.get('targets', {}).items():
                import_config(dict(cfg, target_id=key), 'catalog:' + key)
            for source, (_, cfg) in sources.items():
                if source == 'config.json' or source.endswith('.compute.json'):
                    machine_id = import_config(cfg, source)
                    session = 'workspace' if source == 'config.json' else Path(source).name[:-len('.compute.json')]
                    identifier(session)
                    data['sessions'].setdefault(session, {
                        'session_id': session, 'machine_id': None,
                        'previous_machine_id': machine_id, 'revision': 0})
            # Bind immutable runs from their own snapshot, never a reused catalog name.
            bindings = {}
            for source, (_, job) in sources.items():
                if source.startswith('state/') and source.endswith('/job.json'):
                    job_id = Path(source).parent.name
                    machine_id = import_config(job.get('target'), source)
                    bindings[job_id] = {'machine_id': machine_id, 'source': source}
            data['legacy_run_bindings'] = bindings
            data['legacy_target_mapping'] = mapping
            # Detect added, removed and modified metadata, not just a change to
            # an already backed-up file. This complements, never replaces, the
            # requirement to quiesce legacy writers before activation.
            current = legacy_snapshot(legacy)
            if {key: raw for key, (raw, _) in current.items()} != {key: raw for key, (raw, _) in sources.items()}:
                raise ValueError('Legacy state changed during migration; stop old backends and reconcile')
            data['migration'] = {'state': 'complete', 'completed_at': now(),
                'unresolved': unresolved,
                'sources': {key: hashlib.sha256(raw).hexdigest() for key, (raw, _) in sources.items()}}
            return dict(data['migration'])

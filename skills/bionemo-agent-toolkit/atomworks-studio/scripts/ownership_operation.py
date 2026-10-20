"""Explicit controller claim and conservative lost-response reconciliation."""
import hashlib
import json
from executor_ownership import checksum,validate
import ownership_adapter

class OwnershipRequired(ValueError):
    code='executor_ownership_required'


class OwnershipOperation:
    def ownership_identity(self, machine_id):
        data=self.managed.snapshot();machine=data['machines'][machine_id]
        physical=self.managed._physical(machine)
        owner={'protocol':1,'executor_id':data['executor_id'],
               'controller_root_sha256':hashlib.sha256(str(self.root.resolve()).encode()).hexdigest(),
               'linux_machine_id_sha256':physical,'brev':None}
        return validate(owner)

    def ownership_status(self, machine_id, cfg=None):
        machine=self.managed.machine(machine_id)
        cfg=cfg or dict(machine['config'],target_id=machine_id)
        expected=self.ownership_identity(machine_id)
        result=json.loads(self.target_exec(cfg,ownership_adapter.command('inspect',expected),timeout=30))
        if result.get('state') in ('owned','pending'):
            if result.get('owner')!=expected or result.get('owner_checksum')!=checksum(expected):
                raise ValueError('Executor ownership response does not match this controller')
        elif result.get('state')!='unclaimed':raise ValueError('Unknown executor ownership response')
        return result

    def local_ownership_proof(self, cfg):
        machine_id=cfg.get('target_id')
        if not machine_id:raise OwnershipRequired('Reconnect a saved machine and review its executor ownership claim.')
        machine=self.managed.machine(machine_id);receipt=machine.get('executor_ownership')
        if not receipt:raise OwnershipRequired('Review this installation’s machine ownership claim in chat before running or managing compute.')
        try:owner=self.ownership_identity(machine_id)
        except ValueError as error:raise OwnershipRequired(str(error)) from error
        provider=({'organization_id':cfg['organization_id'],'instance_id':cfg['instance_id']} if cfg['kind']=='brev' else None)
        if receipt.get('owner')!=owner or receipt.get('owner_checksum')!=checksum(owner) or receipt.get('brev')!=provider:
            raise OwnershipRequired('Saved ownership belongs to another executor, state directory or Brev instance. Use its owning installation; no transfer is supported.')
        return {'owner':owner,'owner_checksum':checksum(owner),'brev':provider}

    def require_executor_ownership(self, cfg, expected=None):
        proof=self.local_ownership_proof(cfg)
        if expected is not None and proof!=expected:
            raise OwnershipRequired('Executor ownership changed since review; preserve the request and review again.')
        self.verify_target(cfg)
        observed=self.ownership_status(cfg['target_id'],cfg)
        if observed['state']!='owned':
            raise OwnershipRequired('Protected ownership is missing or publication is pending. Resolve the original claim in chat; no compute action was dispatched.')
        return proof

    def prepare_executor_claim(self, operation_id, machine_id):
        state=self.managed;machine=state.machine(machine_id)
        cfg=dict(machine['config'],target_id=machine_id)
        self.verify_target(cfg)
        machine=state.machine(machine_id)
        expected=self.ownership_identity(machine_id)
        observed=self.ownership_status(machine_id)
        prior=machine.get('executor_ownership')
        if prior and observed['state']=='unclaimed':
            raise ValueError('Previously established ownership is missing; automatic replacement is not supported')
        op=state.choose(operation_id,'claim',machine_id)
        provider=({'organization_id':cfg['organization_id'],'instance_id':cfg['instance_id']}
                  if cfg['kind']=='brev' else None)
        review={'action':'claim','operation_id':operation_id,'machine_id':machine_id,
                'machine_revision':machine['revision'],'session_id':op['session_id'],
                'selection_revision':op['selection_revision'],'owner':expected,
                'brev':provider,'allow_initial':observed['state']=='unclaimed' and prior is None,
                'files':ownership_adapter.manifest(),
                'effect':'Use sudo noninteractively to establish or confirm one protected machine-wide controller ownership record. No installation, power change or inference. Ownership persists after disconnect; transfer and state-directory relocation are unsupported.'}
        with state.transaction() as data:
            current=data['operations'][operation_id]
            if current['state']!='requested' or current['action']!='claim' or current['machine_id']!=machine_id or current['machine_revision']!=machine['revision'] or current['cancel_requested']:
                raise ValueError('Executor ownership operation changed; review again')
            current['review']=review
            # Older binaries lack ownership gates and must not mutate this root
            # after an ownership operation has been introduced.
            data['minimum_backend_protocol']=max(data.get('minimum_backend_protocol',2),3)
        return dict(review,review_checksum=checksum(review))

    def execute_executor_claim(self, operation_id, review_checksum):
        state=self.managed;op=state.operation(operation_id);review=op.get('review')
        if not review or op['action']!='claim' or checksum(review)!=review_checksum:
            raise ValueError('Executor ownership review changed')
        if op['state'] in ('succeeded','failed','cancelled'):return op
        if op['dispatched']:return self.reconcile_executor_claim(operation_id)
        if op['state']!='authorized':
            state.transition(operation_id,'authorized',evidence={'kind':'reviewed_tool_call','checksum':review_checksum},expected_review_checksum=review_checksum)
        cfg=dict(state.machine(op['machine_id'])['config'],target_id=op['machine_id'])
        try:
            state.reserve(op['machine_id'],operation_id,'claim')
            self.verify_target(cfg)
            if self.ownership_identity(op['machine_id'])!=review['owner']:
                raise ValueError('Controller or physical identity changed before ownership claim')
            jobs=self.machine_jobs(op['machine_id'])
            if jobs['active_jobs'] or jobs['unresolved_active_jobs']:
                raise ValueError('Active or unresolved runs must be reconciled before claiming ownership')
            command=ownership_adapter.command('claim',review['owner'],files=review['files'],allow_initial=review['allow_initial'])
            state.transition(operation_id,'dispatched',expected_review_checksum=review_checksum)
        except Exception:
            current=state.operation(operation_id)
            if current['state']=='authorized' and not current['dispatched']:
                state.transition(operation_id,'failed',evidence={'kind':'claim_not_dispatched'},release_reservation=True)
            raise
        try:
            # Treat even a syntactically successful response as provisional:
            # reconcile through an independent ordinary ownership inspection.
            self.target_exec(cfg,command,timeout=60)
            return self.reconcile_executor_claim(operation_id)
        except Exception as error:
            current=state.operation(operation_id)
            if current['state']=='dispatched':
                state.transition(operation_id,'needs_attention',evidence={'kind':'claim_outcome_unknown','detail':str(error)})
            raise

    def reconcile_executor_claim(self, operation_id):
        state=self.managed;op=state.operation(operation_id);review=op.get('review')
        if not review or op['action']!='claim':raise ValueError('No executor ownership claim to reconcile')
        if op['state'] in ('succeeded','failed','cancelled'):return op
        if not op['dispatched']:raise ValueError('Ownership claim has not been dispatched')
        machine_id=op['machine_id'];machine=state.machine(machine_id)
        cfg=dict(machine['config'],target_id=machine_id)
        self.verify_target(cfg)
        if self.ownership_identity(machine_id)!=review['owner']:
            raise ValueError('Claim belongs to another controller or physical machine; preserve the operation')
        observed=self.ownership_status(machine_id)
        if observed['state']!='owned':
            if op['state']=='dispatched':
                state.transition(operation_id,'needs_attention',evidence={'kind':'ownership_not_observed'})
            return dict(state.operation(operation_id),detail='Ownership outcome is unresolved. No claim was repeated; preserve the reservation and inspect the original administrative action.')
        return state.complete_executor_claim(operation_id,checksum(review),observed)

    def confirm_executor_claim(self, operation_id, review_checksum):
        """Explicit approved durability repair; cannot create a missing owner."""
        state=self.managed;op=state.operation(operation_id);review=op.get('review')
        if not review or op['action']!='claim' or checksum(review)!=review_checksum:
            raise ValueError('Executor ownership review changed')
        if op['state'] in ('succeeded','failed','cancelled'):return op
        if not op['dispatched']:raise ValueError('No dispatched owner publication to confirm')
        if op.get('confirmation_dispatched'):
            return self.reconcile_executor_claim(operation_id)
        cfg=dict(state.machine(op['machine_id'])['config'],target_id=op['machine_id'])
        self.verify_target(cfg)
        if self.ownership_identity(op['machine_id'])!=review['owner']:
            raise ValueError('Controller identity changed; no ownership confirmation was sent')
        observed=self.ownership_status(op['machine_id'])
        if observed['state']=='unclaimed':
            raise ValueError('No matching owner exists; preserve the unresolved claim. Confirmation never creates an owner.')
        if observed['state']=='owned':return self.reconcile_executor_claim(operation_id)
        command=ownership_adapter.command('claim',review['owner'],files=review['files'],allow_initial=False)
        state.dispatch_executor_confirmation(operation_id,review_checksum)
        self.target_exec(cfg,command,timeout=60)
        return self.reconcile_executor_claim(operation_id)

# Reviewed lifecycle actions. Provider calls never originate from app text.
import hashlib
import json
from brev_provider import Brev
from brev_provider import NotDispatched
from activity import check_idle


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Lifecycle:
    def prepare_stop(self, operation_id, machine_id, dedicated_machine=False):
        if dedicated_machine is not True:
            raise ValueError('Managed stop requires confirmation that this is a dedicated single-user machine')
        return self._prepare_power(operation_id, machine_id, 'stop')

    def prepare_start(self, operation_id, machine_id):
        return self._prepare_power(operation_id, machine_id, 'start')

    def _prepare_power(self, operation_id, machine_id, action):
        state = self.managed
        machine = state.machine(machine_id)
        cfg = machine['config']
        if cfg['kind'] != 'brev' or not cfg.get('organization_id'):
            raise ValueError('Managed start requires a saved Brev organization and instance')
        observation = Brev(self.run).observe(cfg['organization_id'], cfg['instance_id'])
        if observation['power'] not in ('stopped','running'):
            raise ValueError('Resolve the unknown or deleted provider instance before starting')
        cfg=dict(cfg,target_id=machine_id)
        ownership=(self.local_ownership_proof(cfg) if action=='start' or observation['power']=='stopped'
                   else self.require_executor_ownership(cfg))
        op = state.choose(operation_id, action, machine_id)
        review = {'operation_id':op['id'], 'action':action, 'machine_id':machine_id,
                  'machine_revision':machine['revision'], 'session_id':op['session_id'],
                  'selection_revision':op['selection_revision'], 'organization_id':cfg['organization_id'],
                  'instance_id':cfg['instance_id'], 'name':observation['name'],
                  'instance_type':observation['instance_type'], 'observed_power':observation['power'],'executor_ownership':ownership,
                  'cost':'Starting resumes provider charges. Current price is not available from this inventory.'}
        if action == 'stop':
            review.update(dedicated_machine=True, cost='Stop this dedicated machine through Brev after activity checks. Disconnect alone does not stop billing.')
        with state.transaction() as data:
            current = data['operations'][op['id']]
            if current['action'] != action or current['machine_id'] != machine_id or current['state'] != 'requested' or current['machine_revision'] != machine['revision'] or current['cancel_requested']:
                raise ValueError('Operation changed; review again')
            current['review'] = review
        return dict(review, review_checksum=digest(review))

    def reconcile_power(self, operation_id):
        state = self.managed
        op = state.operation(operation_id)
        if op['action'] not in ('start','stop') or not op.get('review'):
            raise ValueError('No reviewed power action to reconcile')
        if op['state'] in ('succeeded','failed','cancelled'):
            return op
        review = op['review']
        observation = Brev(self.run).observe(review['organization_id'], review['instance_id'])
        desired = 'running' if op['action'] == 'start' else 'stopped'
        if op['dispatched'] and observation['power'] == desired:
            result = state.transition(operation_id, 'succeeded', evidence={'kind':'provider_observation','observation':observation}, release_reservation=True)
            return result
        return dict(op, observation=observation, detail='Outcome is not confirmed. No action was repeated.')

    def execute_start(self, operation_id, review_checksum):
        return self._execute_power(operation_id, review_checksum, 'start')

    def execute_stop(self, operation_id, review_checksum):
        return self._execute_power(operation_id, review_checksum, 'stop')

    def _execute_power(self, operation_id, review_checksum, action):
        """Agent-only host-approved tool entry point, never exposed to the app."""
        state = self.managed
        op = state.operation(operation_id)
        review = op.get('review')
        if not review or op['action'] != action or review['action'] != action or review['machine_id'] != op['machine_id'] or review['machine_revision'] != op['machine_revision'] or digest(review) != review_checksum:
            raise ValueError('Review changed; prepare and review the power action again')
        if op['state'] in ('succeeded','failed','cancelled'):
            return op
        if op['dispatched']:
            return self.reconcile_power(operation_id)
        # Host execution approval is tied to the exact reviewed checksum. An app
        # message alone cannot call this model-only tool or set operation state.
        if op['state'] != 'authorized':
            state.transition(operation_id, 'authorized', evidence={'kind':'reviewed_tool_call','checksum':review_checksum}, expected_review_checksum=review_checksum)
        try:
            state.reserve(op['machine_id'], operation_id, action)
        except Exception:
            current=state.operation(operation_id)
            if current['state']=='authorized':
                state.transition(operation_id, 'needs_attention', evidence={'kind':'reservation_conflict'})
            raise
        try:
            provider = Brev(self.run)
            cfg=dict(state.machine(op['machine_id'])['config'],target_id=op['machine_id'])
            if not review.get('executor_ownership') or self.local_ownership_proof(cfg)!=review['executor_ownership']:
                raise ValueError('Power review has no matching prior executor ownership receipt; review ownership before power management.')
            provider.check_context(review['organization_id'], review['instance_id'])
            observation=provider.observe(review['organization_id'],review['instance_id'])
            desired='running' if action=='start' else 'stopped'
            if observation['power']==desired:
                return state.transition(operation_id,'succeeded',
                    evidence={'kind':'already_at_provider_state','observation':observation},
                    expected_review_checksum=review_checksum,release_reservation=True)
            if action == 'stop':
                if review.get('dedicated_machine') is not True:
                    raise ValueError('Dedicated ownership was not confirmed')
                status=self.machine_jobs(op['machine_id'])
                if status.get('active_jobs') or status.get('unresolved_active_jobs'):
                    raise ValueError('Active or unresolved jobs block managed stop')
                self.require_executor_ownership(cfg,review['executor_ownership'])
                status=self.machine_jobs(op['machine_id'])
                if status.get('active_jobs') or status.get('unresolved_active_jobs'):
                    raise ValueError('Active or unresolved jobs on the verified host block managed stop')
                check_idle(self,cfg)
                # The reservation remains held while the final inventory is
                # taken. Work appearing since the first observation must block.
                check_idle(self,cfg)
                self.require_executor_ownership(cfg,review['executor_ownership'])
            state.transition(operation_id, 'dispatched', expected_review_checksum=review_checksum)
        except Exception:
            current = state.operation(operation_id)
            if not current['dispatched'] and current['state'] == 'authorized':
                state.transition(operation_id, 'failed', evidence={'kind':'pre_dispatch_failure'}, release_reservation=True)
            raise
        try:
            provider.dispatch(action, review['organization_id'], review['instance_id'])
            return self.reconcile_power(operation_id)
        except Exception as error:
            current = state.operation(operation_id)
            if current['state'] == 'dispatched' and isinstance(error, NotDispatched):
                state.transition(operation_id, 'failed', evidence={'kind':'provider_not_dispatched','code':error.code,'detail':str(error)}, release_reservation=True)
            elif current['state'] == 'dispatched':
                state.transition(operation_id, 'needs_attention', evidence={'kind':'unknown_provider_outcome','detail':str(error)})
            raise


# One reviewed Brev creation intent; retries reconcile, never recreate.

from brev_provider import require_type
from brev_provider import creation_spec, creation_payload

class CreateOperation:
    def list_compute_creation_options(self, organization_id):
        provider=Brev(self.run)
        provider.organization_name(organization_id)
        options=[]
        for row in provider.catalog(organization_id):
            try: options.append(creation_spec(row))
            except ValueError: continue
        return {'organization_id':organization_id,'options':options,
                'note':'Select an explicit type for review. Catalog availability is not a capacity reservation.'}

    def prepare_compute_creation(self, operation_id, organization_id, instance_type):
        provider=Brev(self.run)
        organization_name=provider.organization_name(organization_id)
        before=provider.inventory(organization_id)
        specification=creation_spec(require_type(provider.catalog(organization_id), instance_type))
        state=self.managed
        op=state.choose(operation_id,'create',None)
        name='rfd4-'+op['id']
        if any(row.get('name')==name for row in before):
            raise ValueError('Creation name already exists; reconcile it before continuing')
        review={'operation_id':op['id'],'action':'create','session_id':op['session_id'],
                'selection_revision':op['selection_revision'],'organization_id':organization_id,
                'organization_name':organization_name,'name':name,'instance_type':instance_type,'specification':specification,
                'disk_storage':'120Gi','install_jupyter':False,
                'request_payload':creation_payload(name,specification),
                'storage_price':'Unresolved: provider chooses the default disk type. The 120Gi request may be added to included base storage; allocated total is reported separately. Listed rates are alternatives, not a selected rate.',
                'previous_instance_ids':sorted(row['id'] for row in before),
                'cost':'Creates a billable A100 80 GB instance. Catalog base price and storage rates are included in the specification; they are estimates, not a total charge quote. Charges continue until explicitly stopped.',
                'effect':'Create one machine only. Registration, model setup and design submission are separate steps.'}
        with state.transaction() as data:
            current=data['operations'][op['id']]
            if current['state']!='requested' or current['action']!='create' or current['cancel_requested'] or current['selection_revision']!=op['selection_revision']:
                raise ValueError('Creation request changed; review again')
            current['review']=review
        return dict(review,review_checksum=digest(review))

    def execute_compute_creation(self, operation_id, review_checksum):
        state=self.managed;op=state.operation(operation_id);review=op.get('review')
        if not review or op['action']!='create' or review.get('action')!='create' or digest(review)!=review_checksum:
            raise ValueError('Creation review changed')
        if op['state'] in ('succeeded','failed','cancelled'):return op
        if op['dispatched']:return self.reconcile_compute_creation(operation_id)
        if op['state']!='authorized':
            state.transition(operation_id,'authorized',evidence={'kind':'reviewed_tool_call','checksum':review_checksum},expected_review_checksum=review_checksum)
        state.reserve('create:'+operation_id,operation_id,'create')
        provider=Brev(self.run)
        try:
            prepared=provider.preflight_creation(review['organization_id'],review['name'],review['instance_type'])
            if prepared['organization_name']!=review['organization_name'] or prepared['specification']!=review['specification'] or prepared['request_payload']!=review['request_payload']:
                raise ValueError('Organization, machine specification or price changed; review again')
            state.transition(operation_id,'dispatched',expected_review_checksum=review_checksum)
        except Exception:
            current=state.operation(operation_id)
            if current['state']=='authorized':
                state.transition(operation_id,'failed',evidence={'kind':'not_dispatched'},release_reservation=True)
            raise
        try:
            provider.dispatch_creation(prepared)
            return self.reconcile_compute_creation(operation_id)
        except Exception as error:
            current=state.operation(operation_id)
            if current['state']=='dispatched':
                state.transition(operation_id,'needs_attention',evidence={'kind':'unknown_creation_outcome','detail':str(error)})
            raise

    def reconcile_compute_creation(self, operation_id):
        state=self.managed;op=state.operation(operation_id);review=op.get('review')
        if op['action']!='create' or not review:raise ValueError('No reviewed creation request')
        if not op['dispatched'] or op['state'] in ('succeeded','failed','cancelled'):return op
        provider=Brev(self.run)
        observation=provider.observe_creation(review['organization_id'],review['name'],review['instance_type'])
        if observation['state']=='observed':
            if observation['instance_id'] in review['previous_instance_ids']:
                raise ValueError('Observed instance predates this creation; explicit resolution required')
            verification=provider.verify_created_allocation(observation,review)
            if verification['status']!='verified':
                if op['state']=='dispatched':
                    state.transition(operation_id,'needs_attention',evidence={'kind':'allocation_not_verified','verification':verification})
                return dict(state.operation(operation_id),observation=observation,allocation_verification=verification,
                            detail='Machine creation was observed, but its reviewed allocation is not verified. No replacement or deletion was requested.')
            return state.transition(operation_id,'succeeded',evidence={'kind':'creation_observed','observation':observation,'allocation_verification':verification},release_reservation=True)
        return dict(op,observation=observation,detail='Creation outcome is unknown. No additional machine was requested.')

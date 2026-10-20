"""Reviewed lifecycle actions. Provider calls never originate from app text."""
import hashlib
import json
from brev_provider import Brev
from brev_control import NotDispatched
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

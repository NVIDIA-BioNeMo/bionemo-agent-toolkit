"""One reviewed Brev creation intent; retries reconcile, never recreate."""
from brev_provider import Brev
from lifecycle import digest
from brev_catalog import require_type
from brev_control import creation_spec, creation_payload

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

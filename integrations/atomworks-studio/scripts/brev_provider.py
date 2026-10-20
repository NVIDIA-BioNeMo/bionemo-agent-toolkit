"""Brev CLI control-plane observations and immutable-ID lifecycle dispatch.

Pinned contract: v0.6.332. Inventory always specifies organization. Mutations
use organization-scoped creation and immutable-ID power requests; never switch CLI context.
"""
import json
from pathlib import Path
import re
from brev_catalog import available_types, require_type
from brev_control import creation_spec, create_workspace, power_action, creation_payload, workspace_allocation, verify_allocation


class ProviderError(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


class Brev:
    def __init__(self, run, active_org=None, catalog=None, create_request=None, power_request=None):
        self.run = run
        self.active_org = active_org or self.current_org
        self.catalog = catalog or available_types
        self.create_request = create_request or create_workspace
        self.power_request = power_request or power_action

    def organizations(self):
        rows = json.loads(self.run(['brev', 'ls', 'orgs', '--json'], timeout=30))
        if not isinstance(rows, list):
            raise ProviderError('invalid_response', 'Unexpected Brev organization list')
        return rows

    def current_org(self):
        active = [row['id'] for row in self.organizations() if row.get('is_active')]
        if len(active) != 1:
            raise ProviderError('organization_required', 'Explicitly select the intended Brev organization')
        return active[0]

    @staticmethod
    def validate(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
            raise ValueError('Invalid Brev organization or instance identifier')
        return value

    def inventory(self, organization_id):
        organization_id = self.validate(organization_id)
        try:
            organizations = self.organizations()
            matches = [row for row in organizations if row.get('id') == organization_id]
            if len(matches) != 1 or sum(row.get('name') == matches[0]['name'] for row in organizations) != 1:
                raise ProviderError('organization_mismatch', 'Saved Brev organization is unavailable or ambiguous')
            name = matches[0]['name']
            payload = json.loads(self.run(['brev', 'ls', '--org', name, '--json'], timeout=30))
            if not any(row.get('id') == organization_id and row.get('name') == name for row in self.organizations()):
                raise ProviderError('context_changed', 'Brev organization changed during inventory')
        except ProviderError:
            raise
        except Exception as error:
            detail = str(error)
            code = 'authentication_required' if any(word in detail.lower() for word in ('login','unauthorized','unauthenticated','credential','token')) else 'provider_unavailable'
            raise ProviderError(code, detail) from error
        rows = payload.get('workspaces')
        if not isinstance(rows, list):
            raise ProviderError('invalid_response', 'Brev returned an unexpected inventory format')
        return rows

    def observe(self, organization_id, instance_id):
        self.validate(instance_id)
        matches = [row for row in self.inventory(organization_id) if row.get('id') == instance_id]
        if not matches:
            return {'power': 'deleted', 'organization_id': organization_id, 'instance_id': instance_id}
        if len(matches) != 1:
            raise ProviderError('ambiguous_identity', 'Brev returned duplicate instance IDs')
        row = matches[0]
        return {'power': {'RUNNING':'running','STOPPED':'stopped'}.get(row.get('status'), 'unknown'),
                'organization_id':organization_id, 'instance_id':instance_id,
                'name': row.get('name'), 'instance_type':row.get('instance_type'),
                'shell_status':row.get('shell_status'), 'health_status':row.get('health_status')}

    def check_context(self, organization_id, instance_id):
        # Resolve using explicit org and reject name/ID ambiguity before mutation.
        rows = self.inventory(organization_id)
        matches = [row for row in rows if row.get('id') == instance_id]
        if len(matches) != 1 or any(row.get('name') == instance_id and row.get('id') != instance_id for row in rows):
            raise ProviderError('ambiguous_identity', 'Cannot uniquely resolve the saved Brev instance')
        return matches[0]

    def dispatch(self, action, organization_id, instance_id):
        if action not in ('start','stop'):
            raise ValueError('Unsupported Brev power action')
        self.validate(organization_id); self.validate(instance_id)
        row = self.check_context(organization_id, instance_id)
        desired = 'RUNNING' if action == 'start' else 'STOPPED'
        if row.get('status') == desired:
            return self.observe(organization_id, instance_id)
        required = 'STOPPED' if action == 'start' else 'RUNNING'
        if row.get('status') != required:
            raise ProviderError('power_unknown', 'Reconcile provider power state before dispatch')
        # Never use the mutable display name or --all. The caller persists intent
        # and a reservation first; timeout is ambiguous and must not be retried.
        self.power_request(organization_id, instance_id, action)
        return self.observe(organization_id, instance_id)

    def organization_name(self, organization_id):
        self.validate(organization_id)
        rows=self.organizations()
        matches=[row for row in rows if row.get('id')==organization_id]
        if len(matches)!=1 or sum(row.get('name')==matches[0].get('name') for row in rows)!=1:
            raise ProviderError('organization_mismatch','Organization is missing or ambiguous')
        return matches[0]['name']

    def observe_creation(self, organization_id, name, instance_type):
        self.validate(name)
        matches=[row for row in self.inventory(organization_id) if row.get('name')==name]
        if not matches:
            return {'state':'unknown','organization_id':organization_id,'name':name}
        if len(matches)!=1 or matches[0].get('instance_type')!=instance_type:
            raise ProviderError('ambiguous_creation','Creation cannot be uniquely matched to the reviewed specification')
        return {'state':'observed','organization_id':organization_id,'instance_id':matches[0]['id'],
                'name':name,'instance_type':instance_type,'provider_status':matches[0].get('status')}

    def verify_created_allocation(self, observation, review):
        allocation=workspace_allocation(review['organization_id'],observation['instance_id'])
        return verify_allocation(allocation,review)

    def preflight_creation(self, organization_id, name, instance_type):
        """Read-only validation; definitive failures precede durable dispatch."""
        self.validate(name)
        org_name=self.organization_name(organization_id)
        if any(row.get('name')==name for row in self.inventory(organization_id)):
            raise ProviderError('name_exists','Reconcile the existing operation; do not create another instance')
        if self.organization_name(organization_id)!=org_name:
            raise ProviderError('context_changed','Organization changed before creation')
        specification=creation_spec(require_type(self.catalog(organization_id), instance_type))
        return {'organization_id':organization_id,'organization_name':org_name,'name':name,'instance_type':instance_type,'specification':specification,'request_payload':creation_payload(name,specification)}

    def dispatch_creation(self, prepared):
        organization_id=prepared['organization_id'];org_name=prepared['organization_name']
        name=prepared['name'];instance_type=prepared['instance_type']
        self.create_request(organization_id,name,prepared['specification'],expected_payload=prepared['request_payload'])
        return self.observe_creation(organization_id,name,instance_type)

    def create(self, organization_id, name, instance_type):
        return self.dispatch_creation(self.preflight_creation(organization_id,name,instance_type))

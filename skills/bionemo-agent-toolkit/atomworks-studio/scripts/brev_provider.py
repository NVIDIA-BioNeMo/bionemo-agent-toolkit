"""Read-only identity checks through the user-installed Brev CLI."""
import json
import re

class ProviderError(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


class Brev:
    def __init__(self, run):
        self.run = run

    def organizations(self):
        rows = json.loads(self.run(['brev', 'ls', 'orgs', '--json'], timeout=30))
        if not isinstance(rows, list):
            raise ProviderError('invalid_response', 'Unexpected Brev organization list')
        return rows


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

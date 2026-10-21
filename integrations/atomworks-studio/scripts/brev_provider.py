# Read-only, organization-scoped catalog used by Brev CLI v0.6.332.
#
# Contract source: pkg/store/instancetypes.go at 6b111e1f041d354d682541cc489375431f195fcf.
# Authentication remains owned by Brev; this reader never refreshes or stores tokens.
#
import json
from pathlib import Path
import re
import httpx

CATALOG_URL = 'https://api.brev.dev/devplaneapi.v1.InstanceService/ListOrganizationAvailableInstanceTypes'


class CatalogError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def access_token(organization_id, credentials_path=None):
    if not isinstance(organization_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', organization_id):
        raise ValueError('Invalid organization ID')
    path = credentials_path or Path.home() / '.brev' / 'credentials.json'
    try:
        credentials = json.loads(Path(path).read_text())
        if not isinstance(credentials, dict):
            raise ValueError()
    except (OSError, ValueError):
        raise CatalogError('authentication_required', 'Run brev login on the executor, then retry.') from None
    api_key = credentials.get('api_key')
    if api_key and credentials.get('api_key_org_id') != organization_id:
        raise CatalogError('organization_mismatch', 'Brev API key belongs to another organization.')
    token = api_key or credentials.get('access_token')
    if not isinstance(token, str) or not token or any(c in token for c in '\r\n'):
        raise CatalogError('authentication_required', 'Run brev login on the executor, then retry.')
    return token


def available_types(organization_id, *, credentials_path=None, transport=None):
    token = access_token(organization_id, credentials_path)
    try:
        with httpx.Client(transport=transport, follow_redirects=False, timeout=30, trust_env=False) as client:
            response = client.post(CATALOG_URL,
                headers={'Authorization': 'Bearer ' + token, 'Connect-Protocol-Version': '1'},
                json={'organizationId': organization_id, 'options': {
                    'includeUnavailable': False, 'includePreemptible': False,
                    'includeCpu': True, 'uniqueInstanceType': True, 'skipAccessFilter': False}})
    except httpx.HTTPError:
        raise CatalogError('provider_unavailable', 'Cannot reach the Brev catalog; no machine was requested.') from None
    if response.status_code in (401, 403):
        raise CatalogError('authentication_required', 'Brev catalog access denied; check login and organization access.')
    if response.status_code != 200:
        raise CatalogError('provider_unavailable', 'Brev catalog is unavailable; no machine was requested.')
    try:
        payload = response.json()
        rows = payload['items']
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('type'), str) for row in rows):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise CatalogError('invalid_response', 'Brev returned an invalid machine catalog.') from None
    # Explicit allowlist keeps credentials and unrelated response data out of tool results.
    return [{key: row.get(key) for key in ('type', 'stoppable', 'basePrice',
                'supportedGpus', 'supportedArchitectures', 'supportedStorage', 'cloudCredId', 'provider', 'location', 'subLocation')}
            for row in rows]


def require_type(rows, instance_type):
    matches = [row for row in rows if row['type'] == instance_type]
    if len(matches) != 1:
        raise CatalogError('instance_type_unavailable',
            'The reviewed machine type is unavailable or ambiguous in this organization. Select and review an available type; no machine was requested.')
    return matches[0]


# Brev creation contract from CLI v0.6.332 store/workspace.go.
#
# Only explicit-org creation is exposed. No arbitrary URLs, retries or ambient-org use.
# Callers must persist reviewed intent before invoking create_workspace.
#


class NotDispatched(CatalogError):
    """The adapter proves that it did not send a mutation request."""


BASE_URL = 'https://brevapi.us-west-2-prod.control-plane.brev.dev'


def creation_spec(row):
    """Restrict this release to the one A100-80GB, stoppable Linux recipe."""
    gpus = row.get('supportedGpus') or []
    if (len(gpus) != 1 or gpus[0].get('name') != 'A100'
            or gpus[0].get('count') != 1
            or gpus[0].get('memoryBytes', {}).get('value') != '80'
            or gpus[0].get('memoryBytes', {}).get('unit') not in ('GB', 'GIB')
            or row.get('stoppable') is not True
            or 'x86_64' not in (row.get('supportedArchitectures') or [])):
        raise ValueError('Select a stoppable, single A100 80 GB x86_64 machine for this recipe.')
    reference = row.get('cloudCredId')
    if not isinstance(reference, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', reference):
        raise ValueError('Brev catalog did not supply an unambiguous provider account reference.')
    return {key: row.get(key) for key in ('type', 'cloudCredId', 'provider', 'location',
                'subLocation', 'basePrice', 'supportedStorage', 'supportedGpus',
                'supportedArchitectures', 'stoppable')}


def creation_payload(name, specification):
    spec = creation_spec(specification)
    if not isinstance(name, str) or not re.fullmatch(r'rfd4-[a-zA-Z0-9_-]{1,64}', name):
        raise ValueError('Invalid managed machine name')
    body = {'name': name, 'cloudCredId': spec['cloudCredId'], 'instanceType': spec['type'],
            'workspaceClassId': '2x8', 'workspaceTemplateId': '4nbb4lg2s',
            'workspaceVersion': 'v1', 'diskStorage': '120Gi', 'isStoppable': True,
            'vmBuild': {'forceJupyterInstall': False}, 'launchJupyterOnStart': False,
            'portMappings': {}, 'reposV1': {}, 'execsV1': {}}
    for field in ('location', 'subLocation'):
        if spec.get(field): body[field] = spec[field]
    return body


def create_workspace(organization_id, name, specification, *, expected_payload=None, credentials_path=None, transport=None):
    body = creation_payload(name, specification)
    if expected_payload is None or body != expected_payload:
        raise ValueError('Creation request changed; review the complete payload again.')
    token = access_token(organization_id, credentials_path)
    try:
        with httpx.Client(transport=transport, follow_redirects=False, timeout=60, trust_env=False) as client:
            response = client.post(f'{BASE_URL}/api/organizations/{organization_id}/workspaces',
                headers={'Authorization': 'Bearer ' + token}, json=body)
    except httpx.HTTPError:
        raise CatalogError('creation_outcome_unknown',
            'Brev creation response was lost. Reconcile the original operation; do not create another machine.') from None
    if response.status_code not in (200, 201, 202):
        # Even server errors are uncertain after request dispatch; do not retry here.
        raise CatalogError('creation_outcome_unknown',
            f'Brev returned HTTP {response.status_code}. Reconcile the original creation operation.')
    # Authoritative success is established by independent scoped inventory, not this response.
    return {'request_acknowledged': True}


def power_action(organization_id, instance_id, action, *, credentials_path=None, transport=None):
    """Verify immutable instance ownership, then dispatch exactly one power request."""
    if action not in ('start', 'stop') or not isinstance(instance_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', instance_id):
        raise ValueError('Invalid managed power action')
    try:
        token = access_token(organization_id, credentials_path)
    except CatalogError as error:
        raise NotDispatched(error.code, str(error)) from None
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    url = f'{BASE_URL}/api/workspaces/{instance_id}'
    with httpx.Client(transport=transport, follow_redirects=False, timeout=60, trust_env=False) as client:
        try:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                raise NotDispatched('identity_unverified', 'Cannot verify the saved Brev instance; no power action dispatched.')
            row = response.json()
        except (httpx.HTTPError, ValueError):
            raise NotDispatched('identity_unverified', 'Cannot verify the saved Brev instance; no power action dispatched.') from None
        if not isinstance(row, dict) or row.get('id') != instance_id or row.get('organizationId') != organization_id:
            raise NotDispatched('identity_mismatch', 'Brev instance identity does not match the reviewed machine; no power action dispatched.')
        try:
            result = client.put(url + '/' + action, headers=headers)
        except httpx.HTTPError:
            raise CatalogError('power_outcome_unknown', 'Brev power response was lost; reconcile the original operation.') from None
        if result.status_code not in (200, 202, 204):
            raise CatalogError('power_outcome_unknown', f'Brev returned HTTP {result.status_code}; reconcile the original power operation.')
    return {'request_acknowledged': True}


def workspace_allocation(organization_id, instance_id, *, credentials_path=None, transport=None):
    """Fetch only allocation metadata; never return provider passwords or tunnels."""
    if not isinstance(instance_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', instance_id):
        raise ValueError('Invalid instance ID')
    token=access_token(organization_id, credentials_path)
    try:
        with httpx.Client(transport=transport,follow_redirects=False,timeout=30,trust_env=False) as client:
            response=client.get(f'{BASE_URL}/api/workspaces/{instance_id}',headers={'Authorization':'Bearer '+token})
        if response.status_code!=200:
            raise CatalogError('allocation_unverified','Brev allocation could not be inspected; retain the original operation.')
        row=response.json()
    except (httpx.HTTPError, ValueError):
        raise CatalogError('allocation_unverified','Brev allocation could not be inspected; retain the original operation.') from None
    if not isinstance(row,dict) or row.get('id')!=instance_id or row.get('organizationId')!=organization_id:
        raise CatalogError('identity_mismatch','Brev allocation belongs to a different identity.')
    info=row.get('instanceTypeInfo') or {}
    if not isinstance(info,dict):info={}
    environment=row.get('environment') or {}
    instance=environment.get('instance') or {}
    provision=(environment.get('provision') or {}).get('Directive',{}).get('CreateInstanceRequest',{})
    return {'id':row['id'],'organization_id':row['organizationId'],'name':row.get('name'),
            'instance_type':row.get('instanceType'),'disk_storage':provision.get('disk_size'),
            'allocated_disk_storage':instance.get('disk_size'),
            'cloud_reference':instance.get('cloud_cred_id'),
            'provision_cloud_reference':provision.get('cloud_cred_id'),
            'provision_instance_type':provision.get('instance_type'),
            'provider':(instance.get('instance_type_info') or {}).get('provider'),'location':instance.get('location'),
            'sub_location':instance.get('sub_location'),
            # Workspace isStoppable controls automatic stop; catalog capability is distinct.
            'stoppable':instance.get('is_stoppable')}


def disk_bytes(value):
    match=re.fullmatch(r'(\d+)(GiB|Gi|TiB|Ti|MiB|Mi)',str(value))
    if not match:return None
    power={'G':3,'T':4,'M':2}[match[2][0]]
    return int(match[1])*1024**power


def verify_allocation(allocation, review):
    spec=review['specification'];payload=review['request_payload']
    expected={'organization_id':review['organization_id'],'name':review['name'],
        'instance_type':review['instance_type'],'disk_storage':payload['diskStorage'],
        'cloud_reference':spec['cloudCredId'],'provision_cloud_reference':spec['cloudCredId'],
        'provision_instance_type':review['instance_type'],'stoppable':True}
    for target,source in [('provider','provider'),('location','location'),('sub_location','subLocation')]:
        if spec.get(source):expected[target]=spec[source]
    allocation=dict(allocation)
    if disk_bytes(allocation.get('disk_storage')) == disk_bytes(payload['diskStorage']) and disk_bytes(payload['diskStorage']) is not None:
        allocation['disk_storage']=payload['diskStorage']
    missing=[k for k in expected if allocation.get(k) is None]
    mismatches={k:{'expected':v,'observed':allocation[k]} for k,v in expected.items()
                if allocation.get(k) is not None and allocation[k]!=v}
    actual_disk=disk_bytes(allocation.get('allocated_disk_storage'))
    requested_disk=disk_bytes(payload['diskStorage'])
    included={disk_bytes(storage.get('size'))*storage['count'] for storage in (spec.get('supportedStorage') or [])
              if type(storage.get('count')) is int and storage['count']>0 and disk_bytes(storage.get('size'))}
    if len(included)>1:
        missing.append('unambiguous_included_storage')
    expected_disk=(requested_disk or 0)+(next(iter(included)) if len(included)==1 else 0)
    if actual_disk is None:missing.append('allocated_disk_storage')
    elif requested_disk is None or actual_disk != expected_disk:
        mismatches['allocated_disk_storage']={'expected_bytes':expected_disk,'observed':allocation.get('allocated_disk_storage')}
    return {'status':'mismatch' if mismatches else 'unverified' if missing else 'verified',
            'missing_fields':missing,'mismatches':mismatches,'observed':allocation}


# Brev CLI control-plane observations and immutable-ID lifecycle dispatch.
#
# Pinned contract: v0.6.332. Inventory always specifies organization. Mutations
# use organization-scoped creation and immutable-ID power requests; never switch CLI context.
#




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

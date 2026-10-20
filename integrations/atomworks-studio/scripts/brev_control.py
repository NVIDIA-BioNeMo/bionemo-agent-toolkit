"""Brev creation contract from CLI v0.6.332 store/workspace.go.

Only explicit-org creation is exposed. No arbitrary URLs, retries or ambient-org use.
Callers must persist reviewed intent before invoking create_workspace.
"""
import re
import httpx
from brev_catalog import access_token, CatalogError

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

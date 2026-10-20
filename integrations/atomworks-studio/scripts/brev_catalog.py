"""Read-only, organization-scoped catalog used by Brev CLI v0.6.332.

Contract source: pkg/store/instancetypes.go at 6b111e1f041d354d682541cc489375431f195fcf.
Authentication remains owned by Brev; this reader never refreshes or stores tokens.
"""
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

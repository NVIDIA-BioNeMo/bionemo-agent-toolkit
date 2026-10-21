import json
from pathlib import Path
import sys
import tempfile
import unittest
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from brev_provider import available_types, require_type, CatalogError

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'credentials.json'
        self.path.write_text(json.dumps({'access_token':'test-secret'}))
        self.requests = []

    def fetch(self, status=200, payload=None):
        def handler(request):
            self.requests.append(request)
            return httpx.Response(status, json=payload if payload is not None else {'items':[]}, headers={'Location':'https://example.com/'})
        return available_types('org-test', credentials_path=self.path, transport=httpx.MockTransport(handler))

    def test_exact_scoped_request_and_redacted_result(self):
        result=self.fetch(payload={'items':[{'type':'gpu-a100','stoppable':True,'api_key':'should-not-return'}]})
        r=self.requests[0]
        self.assertEqual(str(r.url),'https://api.brev.dev/devplaneapi.v1.InstanceService/ListOrganizationAvailableInstanceTypes')
        self.assertEqual(json.loads(r.content)['organizationId'],'org-test')
        self.assertEqual(r.headers['authorization'],'Bearer test-secret')
        self.assertNotIn('api_key',result[0])

    def test_redirect_never_followed(self):
        with self.assertRaises(CatalogError): self.fetch(302)
        self.assertEqual(len(self.requests),1)

    def test_denied_has_no_retry_or_response_leak(self):
        with self.assertRaises(CatalogError) as caught: self.fetch(403, {'error':'test-secret'})
        self.assertEqual(caught.exception.code,'authentication_required')
        self.assertNotIn('test-secret',str(caught.exception))
        self.assertEqual(len(self.requests),1)

    def test_wrong_api_key_org_has_no_network(self):
        self.path.write_text(json.dumps({'api_key':'test-secret','api_key_org_id':'other'}))
        with self.assertRaises(CatalogError): self.fetch()
        self.assertEqual(self.requests,[])

    def test_bad_credentials_have_no_network(self):
        self.path.write_text('[]')
        with self.assertRaises(CatalogError): self.fetch()
        self.assertEqual(self.requests,[])

    def test_invalid_shapes_are_rejected(self):
        for payload in ([],{}, {'items':{}}, {'items':[None]}):
            with self.subTest(payload=payload), self.assertRaises(CatalogError): self.fetch(payload=payload)

    def test_missing_and_duplicate_type_never_substitute(self):
        for rows in ([], [{'type':'other'}], [{'type':'a100'},{'type':'a100'}]):
            with self.assertRaises(CatalogError): require_type(rows,'a100')
        self.assertEqual(require_type([{'type':'a100'}],'a100')['type'],'a100')

from test_managed_create import SPEC
from brev_provider import create_workspace, creation_spec, creation_payload
from brev_provider import CatalogError

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'auth.json';self.path.write_text(json.dumps({'access_token':'secret'}))
        self.requests=[]
    def call(self,status=201):
        def handler(req):
            self.requests.append(req)
            return httpx.Response(status,json={'secret':'must not expose'},headers={'Location':'https://example.org'})
        return create_workspace('org-target','rfd4-test',SPEC,expected_payload=creation_payload('rfd4-test',SPEC),credentials_path=self.path,transport=httpx.MockTransport(handler))
    def test_fixed_org_endpoint_and_exact_payload(self):
        self.assertTrue(self.call()['request_acknowledged'])
        r=self.requests[0]
        self.assertEqual(str(r.url),'https://brevapi.us-west-2-prod.control-plane.brev.dev/api/organizations/org-target/workspaces')
        payload=json.loads(r.content)
        self.assertEqual(payload['instanceType'],SPEC['type'])
        self.assertEqual(payload['cloudCredId'],SPEC['cloudCredId'])
        self.assertEqual(payload['diskStorage'],'120Gi')
        self.assertEqual(payload['vmBuild'],{'forceJupyterInstall':False})
        self.assertNotIn('secret',str(payload))
    def test_redirect_and_server_failure_are_uncertain_no_retry(self):
        for status in (302,401,409,500):
            self.requests=[]
            with self.assertRaises(CatalogError) as e:self.call(status)
            self.assertEqual(e.exception.code,'creation_outcome_unknown')
            self.assertEqual(len(self.requests),1)
            self.assertNotIn('secret',str(e.exception))
    def test_nonstoppable_or_wrong_gpu_refused(self):
        for replacement in ({'stoppable':False},{'supportedGpus':[]},{'supportedArchitectures':['arm64']},{'cloudCredId':None}):
            with self.assertRaises(ValueError):creation_spec(dict(SPEC,**replacement))
    def test_missing_credentials_never_dispatch(self):
        self.path.unlink()
        with self.assertRaises(CatalogError):self.call()
        self.assertEqual(self.requests,[])

    def test_power_verifies_owner_and_uses_immutable_id(self):
        from brev_provider import power_action
        def handler(req):
            self.requests.append(req)
            return httpx.Response(200,json={'id':'machine','organizationId':'org-target'})
        power_action('org-target','machine','stop',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertEqual([r.method for r in self.requests],['GET','PUT'])
        self.assertEqual(self.requests[1].url.path,'/api/workspaces/machine/stop')
        self.assertEqual(self.requests[1].headers['content-type'],'application/json')

    def test_wrong_owner_never_powers_machine(self):
        from brev_provider import power_action
        def handler(req):
            self.requests.append(req)
            return httpx.Response(200,json={'id':'machine','organizationId':'other'})
        with self.assertRaises(CatalogError):
            power_action('org-target','machine','start',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertEqual([r.method for r in self.requests],['GET'])

    def test_lost_power_ack_is_not_retried(self):
        from brev_provider import power_action
        def handler(req):
            self.requests.append(req)
            if req.method=='PUT':raise httpx.ReadTimeout('secret',request=req)
            return httpx.Response(200,json={'id':'machine','organizationId':'org-target'})
        with self.assertRaises(CatalogError) as e:
            power_action('org-target','machine','start',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertEqual(e.exception.code,'power_outcome_unknown')
        self.assertEqual([r.method for r in self.requests],['GET','PUT'])
        self.assertNotIn('secret',str(e.exception))

    def test_allocation_comparison_preserves_missing_and_mismatch(self):
        from brev_provider import verify_allocation
        review={'organization_id':'org','name':'rfd4-test','instance_type':SPEC['type'],
                'specification':dict(SPEC,supportedStorage=[{'size':'128GiB','count':1}]),'request_payload':creation_payload('rfd4-test',SPEC)}
        allocation={'organization_id':'org','name':'rfd4-test','instance_type':SPEC['type'],
                    'disk_storage':'120GiB','allocated_disk_storage':'248GiB','cloud_reference':SPEC['cloudCredId'],
                    'provision_cloud_reference':SPEC['cloudCredId'],'provision_instance_type':SPEC['type'],'stoppable':True}
        self.assertEqual(verify_allocation(allocation,review)['status'],'verified')
        for changes in ({'disk_storage':'60Gi'},{'cloud_reference':'wrong'},{'stoppable':False},{'allocated_disk_storage':'100TiB'}):
            self.assertEqual(verify_allocation(dict(allocation,**changes),review)['status'],'mismatch')
        missing=dict(allocation,cloud_reference=None)
        self.assertEqual(verify_allocation(missing,review)['missing_fields'],['cloud_reference'])
        self.assertEqual(verify_allocation(missing,review)['status'],'unverified')

    def test_workspace_allocation_is_allowlisted_and_uses_capability(self):
        from brev_provider import workspace_allocation
        def handler(req):
            return httpx.Response(200,json={'id':'machine','organizationId':'org-target','password':'secret',
                'isStoppable':False,'diskStorage':'120Gi','instanceTypeInfo':{'stoppable':True,'provider':'gcp'}})
        allocation=workspace_allocation('org-target','machine',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertIsNone(allocation['stoppable'])
        self.assertNotIn('secret',str(allocation))
        self.assertIsNone(allocation['provider'])

    def test_allocation_reads_actual_instance_and_requested_disk_separately(self):
        from brev_provider import workspace_allocation
        def handler(req):
            return httpx.Response(200,json={'id':'machine','organizationId':'org-target','isStoppable':False,
                'instanceType':'available-a100','environment':{
                    'instance':{'cloud_cred_id':'cloud-ref','is_stoppable':True,'location':'zone-a','disk_size':'248GiB'},
                    'provision':{'Directive':{'CreateInstanceRequest':{'cloud_cred_id':'cloud-ref','instance_type':'available-a100','disk_size':'120GiB'}}}}})
        result=workspace_allocation('org-target','machine',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertEqual(result['cloud_reference'],'cloud-ref')
        self.assertEqual(result['disk_storage'],'120GiB')
        self.assertEqual(result['allocated_disk_storage'],'248GiB')
        self.assertTrue(result['stoppable'])

from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from brev_provider import Brev, ProviderError

class BrevTests(unittest.TestCase):
    def test_unavailable_catalog_type_does_not_dispatch(self):
        provider=self.provider();self.rows=[]
        provider.catalog=lambda org:[]
        with self.assertRaisesRegex(RuntimeError,'unavailable'):
            provider.create('org-fixed','new-name','a100-80gb.1x')
        self.assertTrue(all(c.args[0][1] in ('ls','--version') for c in self.run.call_args_list))

    def provider(self, state='STOPPED'):
        self.rows=[{'id':'fixed-id','name':'mutable-name','status':state}]
        def run(args, timeout=30):
            if args[1]=='--version':return 'Current Version: v0.6.332\n'
            if args[1:3]==['ls','orgs']: return json.dumps([{'id':'org-fixed','name':'org-name','is_active':True}])
            if args[1]=='ls': return json.dumps({'workspaces':self.rows})
            self.rows[0]['status']='RUNNING' if args[1]=='start' else 'STOPPED'
            return ''
        self.run=Mock(side_effect=run)
        def power(org,ident,action):
            self.assertEqual((org,ident),('org-fixed','fixed-id'))
            self.rows[0]['status']='RUNNING' if action=='start' else 'STOPPED'
        self.power=Mock(side_effect=power)
        return Brev(self.run, active_org=lambda:'org-fixed', catalog=lambda org:[{'type':'a100-80gb.1x'}],power_request=self.power)

    def test_start_uses_id_and_explicit_inventory_org(self):
        provider=self.provider()
        self.assertEqual(provider.dispatch('start','org-fixed','fixed-id')['power'],'running')
        self.power.assert_called_once_with('org-fixed','fixed-id','start')
        for call in self.run.call_args_list:
            if call.args[0][1:3]==['ls','--org']: self.assertEqual(call.args[0],['brev','ls','--org','org-name','--json'])

    def test_ambient_org_is_not_used_for_power(self):
        provider=self.provider();provider.active_org=lambda:'other'
        self.assertEqual(provider.dispatch('start','org-fixed','fixed-id')['power'],'running')
        self.power.assert_called_once_with('org-fixed','fixed-id','start')

    def test_deleted_and_unknown_are_not_stopped(self):
        provider=self.provider('STARTING')
        self.assertEqual(provider.observe('org-fixed','fixed-id')['power'],'unknown')
        self.assertEqual(provider.observe('org-fixed','missing')['power'],'deleted')
        with self.assertRaises(ProviderError):provider.dispatch('start','org-fixed','fixed-id')

    def test_name_collision_rejected(self):
        provider=self.provider()
        self.rows.append({'id':'other-id','name':'fixed-id','status':'RUNNING'})
        with self.assertRaises(ProviderError):provider.dispatch('start','org-fixed','fixed-id')
        self.assertTrue(all(c.args[0][1]=='ls' for c in self.run.call_args_list))

    def test_timeout_has_no_automatic_retry(self):
        provider=self.provider()
        self.power.side_effect=TimeoutError('unknown outcome')
        with self.assertRaises(TimeoutError):provider.dispatch('start','org-fixed','fixed-id')
        self.power.assert_called_once()

    def test_creation_uses_scoped_request_and_never_cli_start(self):
        from test_managed_create import SPEC
        provider=self.provider();self.rows=[]
        provider.catalog=lambda org:[SPEC]
        def create(org,name,spec,expected_payload):
            self.assertEqual(org,'org-fixed')
            self.assertEqual(spec,SPEC)
            self.rows.append({'id':'new-id','name':name,'instance_type':spec['type'],'status':'STARTING'})
        provider.create_request=Mock(side_effect=create)
        result=provider.create('org-fixed','rfd4-test',SPEC['type'])
        self.assertEqual(result['instance_id'],'new-id')
        provider.create_request.assert_called_once()
        self.assertTrue(all(c.args[0][1]=='ls' for c in self.run.call_args_list))

    def test_creation_request_timeout_is_not_retried(self):
        from test_managed_create import SPEC
        provider=self.provider();self.rows=[];provider.catalog=lambda org:[SPEC]
        provider.create_request=Mock(side_effect=TimeoutError('lost'))
        with self.assertRaises(TimeoutError):provider.create('org-fixed','rfd4-test',SPEC['type'])
        provider.create_request.assert_called_once()

if __name__ == "__main__": unittest.main()

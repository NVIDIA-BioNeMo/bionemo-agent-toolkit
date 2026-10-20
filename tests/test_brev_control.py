import json
from pathlib import Path
import tempfile
import unittest
import httpx
from test_managed_create import SPEC
from brev_control import create_workspace, creation_spec, creation_payload
from brev_catalog import CatalogError

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
        from brev_control import power_action
        def handler(req):
            self.requests.append(req)
            return httpx.Response(200,json={'id':'machine','organizationId':'org-target'})
        power_action('org-target','machine','stop',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertEqual([r.method for r in self.requests],['GET','PUT'])
        self.assertEqual(self.requests[1].url.path,'/api/workspaces/machine/stop')
        self.assertEqual(self.requests[1].headers['content-type'],'application/json')

    def test_wrong_owner_never_powers_machine(self):
        from brev_control import power_action
        def handler(req):
            self.requests.append(req)
            return httpx.Response(200,json={'id':'machine','organizationId':'other'})
        with self.assertRaises(CatalogError):
            power_action('org-target','machine','start',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertEqual([r.method for r in self.requests],['GET'])

    def test_lost_power_ack_is_not_retried(self):
        from brev_control import power_action
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
        from brev_control import verify_allocation
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
        from brev_control import workspace_allocation
        def handler(req):
            return httpx.Response(200,json={'id':'machine','organizationId':'org-target','password':'secret',
                'isStoppable':False,'diskStorage':'120Gi','instanceTypeInfo':{'stoppable':True,'provider':'gcp'}})
        allocation=workspace_allocation('org-target','machine',credentials_path=self.path,transport=httpx.MockTransport(handler))
        self.assertIsNone(allocation['stoppable'])
        self.assertNotIn('secret',str(allocation))
        self.assertIsNone(allocation['provider'])

    def test_allocation_reads_actual_instance_and_requested_disk_separately(self):
        from brev_control import workspace_allocation
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

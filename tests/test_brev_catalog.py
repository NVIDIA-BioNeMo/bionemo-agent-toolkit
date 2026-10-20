import json
from pathlib import Path
import sys
import tempfile
import unittest
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from brev_catalog import available_types, require_type, CatalogError

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

if __name__=='__main__': unittest.main()

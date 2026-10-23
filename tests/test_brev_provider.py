"""Read-only CLI identity verification; all lifecycle choices belong to chat."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from brev_provider import Brev,ProviderError

class BrevReadTests(unittest.TestCase):
    def test_named_org_and_immutable_id_without_context_switch(self):
        orgs=json.dumps([{'id':'org-id','name':'my-org'}])
        run=Mock(side_effect=[orgs,json.dumps({'workspaces':[{'id':'machine-id','name':'gpu'}]}),orgs])
        result=Brev(run).check_context('org-id','machine-id')
        self.assertEqual(result['name'],'gpu')
        self.assertEqual(run.call_args_list[1].args[0],['brev','ls','--org','my-org','--json'])
        self.assertTrue(all(c.args[0][:2]==['brev','ls'] for c in run.call_args_list))

    def test_absent_cli_expired_login_tls_and_provider_failure_propagate(self):
        for error in (FileNotFoundError('brev'),RuntimeError('login required'),RuntimeError('x509: certificate signed by unknown authority'),RuntimeError('unreachable')):
            run=Mock(side_effect=error)
            with self.assertRaises(ProviderError):Brev(run).check_context('org-id','machine-id')
            self.assertEqual(run.call_count,1)

    def test_wrong_organization_and_ambiguous_instance_rejected(self):
        with self.assertRaises(ProviderError):Brev(Mock(return_value='[]')).check_context('org-id','machine-id')
        orgs=json.dumps([{'id':'org-id','name':'my-org'}])
        run=Mock(side_effect=[orgs,json.dumps({'workspaces':[{'id':'x'},{'id':'x'}]}),orgs])
        with self.assertRaises(ProviderError):Brev(run).check_context('org-id','x')

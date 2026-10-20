import json
from pathlib import Path
import sys
import unittest
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

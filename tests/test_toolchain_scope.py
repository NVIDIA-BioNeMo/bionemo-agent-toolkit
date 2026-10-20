import sys,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from toolchain_scope import observe,verify_worker_membership

class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.unit='rfd4-package-'+'a'*32+'.scope'
        self.group='/system.slice/'+self.unit
        self.events=self.root/self.group.lstrip('/')/'cgroup.events'
        self.events.parent.mkdir(parents=True);self.events.write_text('populated 1\nfrozen 0\n')
        self.membership=self.root/'membership';self.membership.write_text('0::'+self.group+'\n')
        self.fields=dict(LoadState='loaded',ActiveState='active',SubState='running',
                         ControlGroup=self.group,InvocationID='b'*32)
        self.run=Mock(side_effect=lambda *a,**kw:SimpleNamespace(stdout='\n'.join(k+'='+v for k,v in self.fields.items())))
    def check(self,**kwargs):return observe(self.unit,run=self.run,cgroup_root=self.root,**kwargs)
    def test_surviving_child_keeps_scope_pending(self):
        self.assertEqual(self.check()['state'],'pending')
    def test_empty_active_scope_does_not_prove_completion(self):
        self.events.write_text('populated 0\n');self.assertEqual(self.check()['state'],'pending')
    def test_empty_inactive_observation(self):
        self.events.write_text('populated 0\n');self.fields.update(ActiveState='inactive',SubState='dead')
        self.assertEqual(self.check()['state'],'empty')
    def test_gc_is_absence_not_success(self):
        self.fields.update(LoadState='not-found',ActiveState='inactive',SubState='dead',ControlGroup='',InvocationID='')
        self.events.unlink();self.events.parent.rmdir()
        self.assertEqual(self.check(),{'state':'absent','unit':self.unit})
    def test_missing_unit_with_surviving_cgroup_remains_pending(self):
        self.fields.update(LoadState='not-found',ActiveState='inactive',SubState='dead',ControlGroup='',InvocationID='')
        self.assertEqual(self.check()['state'],'pending')
    def test_identity_change_refused(self):
        with self.assertRaisesRegex(ValueError,'invocation changed'):self.check(invocation='c'*32)
    def test_group_change_refused(self):
        self.fields['ControlGroup']='/other'
        with self.assertRaisesRegex(ValueError,'cgroup changed'):self.check()
    def test_permission_or_timeout_not_absence(self):
        for error in (PermissionError(),subprocess.TimeoutExpired('systemctl',15)):
            self.run.side_effect=error
            with self.assertRaises(type(error)):self.check()
    def test_missing_events_not_empty(self):
        self.events.unlink()
        with self.assertRaises(FileNotFoundError):self.check()
    def test_incomplete_response_refused(self):
        del self.fields['InvocationID']
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.check()
    def test_invalid_unit_does_not_run(self):
        with self.assertRaises(ValueError):observe('../other',run=self.run)
        self.run.assert_not_called()
    def test_malformed_invocation_does_not_run(self):
        for invocation in (123,{},'wrong'):
            with self.assertRaises(ValueError):self.check(invocation=invocation)
        self.run.assert_not_called()
    def test_unknown_population_cannot_be_empty(self):
        self.events.write_text('frozen 0\n')
        with self.assertRaisesRegex(ValueError,'population is unknown'):self.check()
    def test_duplicate_fields_refused(self):
        self.run.side_effect=None
        self.run.return_value=SimpleNamespace(stdout='LoadState=loaded\nLoadState=not-found')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):self.check()
    def test_worker_must_already_be_in_exact_scope(self):
        kwargs=dict(run=self.run,cgroup_root=self.root,membership=self.membership)
        self.assertTrue(verify_worker_membership(self.unit,**kwargs)['populated'])
        self.membership.write_text('0::/system.slice/other.scope\n')
        with self.assertRaisesRegex(ValueError,'outside'):verify_worker_membership(self.unit,**kwargs)
    def test_worker_cannot_enter_stopping_or_failed_scope(self):
        for active,sub in [('deactivating','stop-sigterm'),('failed','failed'),('activating','start')]:
            self.fields.update(ActiveState=active,SubState=sub)
            self.assertEqual(self.check()['state'],'pending')
            with self.assertRaisesRegex(ValueError,'not in an active'):
                verify_worker_membership(self.unit,run=self.run,cgroup_root=self.root,membership=self.membership)

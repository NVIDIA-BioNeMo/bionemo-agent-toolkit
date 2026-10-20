"""Actual service gates with isolated ownership observations; no cloud effects.

Unlike unrelated-contract fixtures, these tests do not patch require/local proof.
Only authenticated host identity and the protected remote read are simulated.
"""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service
from core import Backend
from executor_ownership import checksum
from ownership_operation import OwnershipRequired


class OwnershipGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.a=Service(Path(self.temp.name)/'A');self.b=Service(Path(self.temp.name)/'B')
        identity=patch('registry.linux_machine_identity',return_value={'linux_machine_id_sha256':'c'*64});identity.start();self.addCleanup(identity.stop)
        self.ids=[]
        for service in (self.a,self.b):
            service.register_compute('local','gpu','/srv/rfd4','http://127.0.0.1:18769',session_id='s')
            machine=service.config('s')['target_id'];self.ids.append(machine)
            owner=service.ownership_identity(machine)
            with service.managed.transaction() as data:
                data['machines'][machine]['executor_ownership']={'owner':owner,'owner_checksum':checksum(owner),'brev':None,'operation_id':'fixture-prior-claim'}
        self.remote_owner=self.a.ownership_identity(self.ids[0]);self.remote_state='owned'
        self.reads=0
        def observe(service,machine,cfg=None):
            self.reads+=1;expected=service.ownership_identity(machine)
            if self.remote_owner!=expected:raise OwnershipRequired('This machine belongs to a different executor')
            return {'state':self.remote_state,'owner':self.remote_owner,'owner_checksum':checksum(self.remote_owner)}
        for service in (self.a,self.b):
            observer=patch.object(service,'ownership_status',side_effect=lambda machine,cfg=None,s=service:observe(s,machine,cfg));observer.start();self.addCleanup(observer.stop)
            commands=patch.object(service,'target_exec',side_effect=AssertionError('No runtime command permitted in refusal test'));commands.start();self.addCleanup(commands.stop)
            copy=patch.object(service,'target_copy',side_effect=AssertionError('No upload permitted in refusal test'));copy.start();self.addCleanup(copy.stop)

    def plan(self,service):
        export={'revision':1,'cif':'data_example\n_atom_site.id 1\n','issues':[]}
        with patch.object(service,'studio',return_value=export):return service.prepare('s')

    def test_pending_owner_run_excludes_foreign_controller_before_review(self):
        self.a.managed.reserve(self.ids[0],'pending-run-A','run')
        with self.assertRaisesRegex(OwnershipRequired,'different executor'):self.plan(self.b)
        self.assertEqual(self.a.managed.snapshot()['reservations'][self.ids[0]]['owner_id'],'pending-run-A')
        self.assertEqual(self.b.managed.snapshot()['reservations'],{})
        self.b.target_exec.assert_not_called();self.b.target_copy.assert_not_called()

    def test_ownership_change_after_review_blocks_job_acceptance(self):
        self.remote_owner=self.b.ownership_identity(self.ids[1]);plan=self.plan(self.b)
        self.remote_owner=self.a.ownership_identity(self.ids[0])
        with patch.object(self.b,'check_compute',return_value={'state':'ready'}),patch('core.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(OwnershipRequired,'different executor'):self.b.execute(plan['snapshot_id'],plan['plan_checksum'])
            spawn.assert_not_called()
        self.assertFalse((self.b.state/plan['snapshot_id']/'job.json').exists())
        self.assertEqual(self.b.managed.snapshot()['reservations'],{})

    def test_detached_backend_rechecks_before_first_remote_write(self):
        # Backend is precisely the class constructed by worker.py.
        worker=Backend(self.b.root)
        machine=self.ids[1];cfg=self.b.config('s');proof=self.b.local_ownership_proof(cfg)
        directory=worker.state/'queued';directory.mkdir();source=directory/'input.cif';source.write_text('data_example')
        job={'job_id':'queued','status':'queued','target':cfg,'executor_ownership':proof}
        with patch.object(worker,'ownership_status',side_effect=OwnershipRequired('foreign owner')),patch.object(worker,'target_exec') as command,patch.object(worker,'target_copy') as copy:
            worker._submit(cfg,job,source)
            command.assert_not_called();copy.assert_not_called()
        self.assertEqual(worker.read('queued','job.json')['status'],'failed')
        self.assertFalse((directory/'run.sh').exists())

    def test_missing_receipt_or_copied_root_never_uses_remote_commands(self):
        machine=self.ids[1]
        with self.b.managed.transaction() as data:data['machines'][machine]['executor_ownership']=self.a.managed.machine(self.ids[0])['executor_ownership']
        with self.assertRaisesRegex(OwnershipRequired,'another executor'):self.b.require_executor_ownership(self.b.config('s'))
        self.assertEqual(self.reads,0)
        with self.b.managed.transaction() as data:del data['machines'][machine]['executor_ownership']
        self.assertEqual(self.b.compute_status('s')['state'],'ownership_required')
        self.assertEqual(self.b.check_compute('s')['state'],'ownership_required')
        self.assertEqual(self.reads,0)

    def test_pending_publication_cannot_authorize_review(self):
        self.remote_state='pending'
        with self.assertRaisesRegex(OwnershipRequired,'pending'):self.plan(self.a)
        self.a.target_exec.assert_not_called();self.a.target_copy.assert_not_called()

    def test_foreign_controller_cannot_begin_setup_or_recovery(self):
        op=self.b.begin_setup('s')
        with self.assertRaisesRegex(OwnershipRequired,'different executor'):self.b.prepare_runtime_setup(op['id'],self.ids[1])
        self.b.target_copy.assert_not_called();self.b.target_exec.assert_not_called()

    def reviewed_setup(self):
        self.remote_owner=self.b.ownership_identity(self.ids[1])
        op=self.b.begin_setup('s')
        with patch.object(self.b,'review_prerequisites',return_value={'changes':{},'download_bytes':0}):
            review=self.b.prepare_runtime_setup(op['id'],self.ids[1])
        return op,review

    def dispatched_setup(self):
        op,review=self.reviewed_setup();state=self.b.managed
        state.transition(op['id'],'authorized',evidence={'kind':'fixture-approved-review'})
        state.reserve(self.ids[1],op['id'],'setup');state.transition(op['id'],'dispatched')
        return op,review

    def test_foreign_owner_after_setup_review_prevents_staging(self):
        op,review=self.reviewed_setup();self.remote_owner=self.a.ownership_identity(self.ids[0])
        with self.assertRaisesRegex(OwnershipRequired,'different executor'):self.b.execute_runtime_setup(op['id'],review['review_checksum'])
        self.b.target_exec.assert_not_called();self.b.target_copy.assert_not_called()
        self.assertEqual(self.b.managed.operation(op['id'])['state'],'failed')
        self.assertEqual(self.b.managed.snapshot()['reservations'],{})

    def test_foreign_owner_blocks_recovery_fence_then_owning_recovery_can_finish(self):
        op,review=self.dispatched_setup();self.remote_owner=self.a.ownership_identity(self.ids[0])
        with self.assertRaisesRegex(OwnershipRequired,'different executor'):self.b.recover_runtime_setup(op['id'])
        self.b.target_exec.assert_not_called()
        self.assertIn(self.ids[1],self.b.managed.snapshot()['reservations'])
        self.remote_owner=self.b.ownership_identity(self.ids[1])
        outcome={'job_id':op['id'],'state':'failed','reason':'orphaned_dispatch_fenced'}
        with patch.object(self.b,'target_exec',return_value=json.dumps(outcome)) as recovered:
            result=self.b.recover_runtime_setup(op['id'])
        self.assertEqual(result['state'],'failed');self.assertEqual(recovered.call_count,1)
        self.assertIn(' recover ',recovered.call_args.args[1])
        self.assertEqual(self.b.managed.snapshot()['reservations'],{})
        # A fresh explicit request can reach review after the reconciled failure.
        fresh=self.b.begin_setup('s')
        with patch.object(self.b,'review_prerequisites',return_value={'changes':{},'download_bytes':0}):
            self.assertEqual(self.b.prepare_runtime_setup(fresh['id'],self.ids[1])['action'],'setup')

    def test_foreign_owner_prevents_remote_cancel_marker_and_retains_unknown_outcome(self):
        op,review=self.dispatched_setup();self.remote_owner=self.a.ownership_identity(self.ids[0])
        result=self.b.cancel_compute_operation(op['id'])
        self.assertTrue(result['cancel_requested']);self.assertEqual(result['state'],'needs_attention')
        self.assertIn('different executor',result['delivery_error'])
        self.b.target_exec.assert_not_called();self.b.target_copy.assert_not_called()
        self.assertIn(self.ids[1],self.b.managed.snapshot()['reservations'])

    def test_local_proof_survives_disconnect_but_does_not_reconnect(self):
        proof=self.a.local_ownership_proof(self.a.config('s'))
        self.a.disconnect_compute('s',1)
        self.assertEqual(self.a.compute_status('s')['state'],'unregistered')
        cfg=dict(self.a.managed.machine(self.ids[0])['config'],target_id=self.ids[0])
        self.assertEqual(self.a.require_executor_ownership(cfg),proof)
        self.assertIsNone(self.a.managed.selection('s')['machine_id'])

    def brev_fixture(self, *, owned=True, power='running'):
        service=Service(Path(self.temp.name)/'C')
        service.register_compute('brev','brev-gpu','/srv/rfd4','http://127.0.0.1:18769',instance_id='immutable',organization_id='org',session_id='s')
        machine=service.config('s')['target_id'];service.managed.bind_physical_identity(machine,{'linux_machine_id_sha256':'c'*64})
        owner=service.ownership_identity(machine)
        if owned:
            with service.managed.transaction() as data:
                data['machines'][machine]['executor_ownership']={'owner':owner,'owner_checksum':checksum(owner),'brev':{'organization_id':'org','instance_id':'immutable'},'operation_id':'prior-claim'}
        class Provider:
            calls=0
            def __init__(provider):provider.power=power
            def observe(provider,org,instance):return {'power':provider.power,'organization_id':org,'instance_id':instance,'name':'brev-gpu','instance_type':'A100'}
            def check_context(provider,*args):return {}
            def dispatch(provider,action,*args):provider.calls+=1;provider.power='running' if action=='start' else 'stopped'
        provider=Provider()
        patches=[patch('lifecycle.Brev',return_value=provider),patch.object(service,'verify_target'),
                 patch.object(service,'ownership_status',side_effect=lambda *a:self.observe_brev(owner)),
                 patch.object(service,'target_exec',side_effect=AssertionError('No shell command expected')),
                 patch.object(service,'target_copy',side_effect=AssertionError('No upload expected'))]
        for mocked in patches:mocked.start();self.addCleanup(mocked.stop)
        return service,machine,owner,provider

    def observe_brev(self,expected):
        if self.remote_owner!=expected:raise OwnershipRequired('This machine belongs to a different executor')
        return {'state':'owned','owner':expected,'owner_checksum':checksum(expected)}

    def test_new_unowned_stopped_brev_cannot_start_from_provider_visibility(self):
        service,machine,owner,provider=self.brev_fixture(owned=False,power='stopped')
        op=service.begin_setup('s')
        with self.assertRaisesRegex(OwnershipRequired,'ownership claim'):service.prepare_start(op['id'],machine)
        self.assertEqual(provider.calls,0);service.ownership_status.assert_not_called()

    def test_owned_stopped_brev_start_uses_prior_tuple_without_ssh_or_inference(self):
        service,machine,owner,provider=self.brev_fixture(power='stopped')
        op=service.begin_setup('s');review=service.prepare_start(op['id'],machine)
        with patch.object(service,'launch',side_effect=AssertionError('Start must not generate')):
            result=service.execute_start(op['id'],review['review_checksum'])
        self.assertEqual(result['state'],'succeeded');self.assertEqual(provider.calls,1)
        service.ownership_status.assert_not_called();service.target_exec.assert_not_called()
        self.assertEqual(list(service.state.glob('*/job.json')),[])

    def test_foreign_owner_blocks_stop_before_idle_and_provider_dispatch(self):
        service,machine,owner,provider=self.brev_fixture();self.remote_owner=owner
        op=service.begin_setup('s');review=service.prepare_stop(op['id'],machine,True)
        self.a.managed.reserve(self.ids[0],'pending-run-A','run');self.remote_owner=self.a.ownership_identity(self.ids[0])
        with patch('lifecycle.check_idle') as idle:
            with self.assertRaisesRegex(OwnershipRequired,'different executor'):service.execute_stop(op['id'],review['review_checksum'])
            idle.assert_not_called()
        self.assertEqual(provider.calls,0)
        self.assertEqual(self.a.managed.snapshot()['reservations'][self.ids[0]]['owner_id'],'pending-run-A')

    def test_owner_rechecked_after_final_idle_observation(self):
        service,machine,owner,provider=self.brev_fixture();self.remote_owner=owner
        op=service.begin_setup('s');review=service.prepare_stop(op['id'],machine,True)
        calls=[]
        def idle(*args):
            calls.append(1)
            if len(calls)==2:self.remote_owner=self.a.ownership_identity(self.ids[0])
            return {}
        with patch('lifecycle.check_idle',side_effect=idle):
            with self.assertRaisesRegex(OwnershipRequired,'different executor'):service.execute_stop(op['id'],review['review_checksum'])
        self.assertEqual(len(calls),2);self.assertEqual(provider.calls,0)

if __name__=='__main__':unittest.main()

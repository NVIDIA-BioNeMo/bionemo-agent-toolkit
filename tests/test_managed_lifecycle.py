import sys
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service

class Provider:
    def __init__(self):
        self.power='stopped';self.calls=0;self.lose_response=False
    def observe(self, org, instance):
        return {'power':self.power,'organization_id':org,'instance_id':instance,'name':'demo','instance_type':'A100'}
    def check_context(self, *args): return {}
    def dispatch(self, action, org, instance):
        self.calls+=1;self.power='running' if action=='start' else 'stopped'
        if self.lose_response: raise TimeoutError('lost response')
        return self.observe(org,instance)

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=Service(self.temp.name)
        from ownership_test_support import assume_owned
        assume_owned(self,self.service,skip_transport_identity=False)
        verify=patch.object(self.service,'verify_target');verify.start();self.addCleanup(verify.stop)
        self.service.register_compute('brev','demo','/srv/rfd4','http://127.0.0.1',instance_id='fixed',organization_id='org',session_id='demo')
        self.machine=self.service.config('demo')['target_id']
        self.provider=Provider()
        p=patch('lifecycle.Brev',return_value=self.provider);p.start();self.addCleanup(p.stop)
        self.op=self.service.begin_setup('demo')['id']
        self.review=self.service.prepare_start(self.op,self.machine)

    def test_start_once_and_no_inference(self):
        with patch.object(self.service,'launch',side_effect=AssertionError('No inference')):
            a=self.service.execute_start(self.op,self.review['review_checksum'])
            b=self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(a,b);self.assertEqual(a['state'],'succeeded');self.assertEqual(self.provider.calls,1)
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_stop_requires_dedicated_confirmation(self):
        with self.assertRaises(ValueError):self.service.prepare_stop(self.op,self.machine)
        self.assertEqual(self.provider.calls,0)

    def test_disconnected_session_cannot_hide_target_jobs(self):
        self.provider.power='running'
        self.service.disconnect_compute('demo',1)
        op=self.service.begin_setup('demo')['id']
        review=self.service.prepare_stop(op,self.machine,True)
        folder=self.service.state/'queued-job';folder.mkdir(parents=True)
        (folder/'job.json').write_text(json.dumps({'job_id':'queued-job','machine_id':self.machine,'status':'queued'}))
        with patch('lifecycle.check_idle',return_value={}):
            with self.assertRaisesRegex(ValueError,'Active or unresolved'):
                self.service.execute_stop(op,review['review_checksum'])
        self.assertEqual(self.provider.calls,0)

    def test_reprepare_between_read_and_authorization_rejects_old_review(self):
        from managed_state import State
        original=State.transition
        def race(state,operation_id,new_state,**kwargs):
            if new_state=='authorized':
                self.service.prepare_stop(operation_id,self.machine,True)
            return original(state,operation_id,new_state,**kwargs)
        with patch.object(State,'transition',race):
            with self.assertRaisesRegex(ValueError,'Review changed'):
                self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(self.provider.calls,0)

    def test_stop_once_after_activity_check(self):
        self.provider.power='running'
        review=self.service.prepare_stop(self.op,self.machine,True)
        with patch('lifecycle.check_idle',return_value={}) as idle:
            result=self.service.execute_stop(self.op,review['review_checksum'])
            self.service.execute_stop(self.op,review['review_checksum'])
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual(self.provider.calls,1);self.assertEqual(idle.call_count,2)

    def test_work_appearing_on_final_probe_prevents_provider_stop(self):
        self.provider.power='running'
        review=self.service.prepare_stop(self.op,self.machine,True)
        with patch('lifecycle.check_idle',side_effect=[{},ValueError('active work')]) as idle:
            with self.assertRaisesRegex(ValueError,'active work'):
                self.service.execute_stop(self.op,review['review_checksum'])
        self.assertEqual(idle.call_count,2)
        self.assertEqual(self.provider.calls,0)
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_already_stopped_needs_no_ssh_or_stop(self):
        review=self.service.prepare_stop(self.op,self.machine,True)
        with patch('lifecycle.check_idle',side_effect=AssertionError('No SSH to stopped host')):
            result=self.service.execute_stop(self.op,review['review_checksum'])
        self.assertEqual(result['state'],'succeeded')
        self.assertFalse(result['dispatched'])
        self.assertEqual(self.provider.calls,0)
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_already_running_needs_no_start(self):
        self.provider.power='running'
        result=self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(result['state'],'succeeded')
        self.assertFalse(result['dispatched']);self.assertEqual(self.provider.calls,0)

    def test_unknown_activity_blocks_stop_and_releases_undispatched_reservation(self):
        self.provider.power='running'
        review=self.service.prepare_stop(self.op,self.machine,True)
        with patch('lifecycle.check_idle',side_effect=TimeoutError('activity unavailable')):
            with self.assertRaises(TimeoutError):self.service.execute_stop(self.op,review['review_checksum'])
        self.assertEqual(self.provider.calls,0)
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_active_run_reservation_blocks_stop(self):
        review=self.service.prepare_stop(self.op,self.machine,True)
        self.service.managed.reserve(self.machine,'existing-job','run')
        with self.assertRaises(ValueError):self.service.execute_stop(self.op,review['review_checksum'])
        self.assertEqual(self.provider.calls,0)

    def test_cancel_during_preflight_releases_without_dispatch(self):
        def cancel(*args):self.service.managed.cancel(self.op)
        with patch.object(self.provider,'check_context',side_effect=cancel):
            with self.assertRaises(ValueError):
                self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(self.provider.calls,0)
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_cancel_before_reservation_cannot_reacquire_machine(self):
        from managed_state import State
        original=State.reserve
        def race(state,machine,owner,purpose):
            state.cancel(owner)
            return original(state,machine,owner,purpose)
        with patch.object(State,'reserve',race):
            with self.assertRaisesRegex(ValueError,'no longer authorizes'):
                self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(self.service.managed.operation(self.op)['state'],'cancelled')
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])
        self.assertEqual(self.provider.calls,0)

    def test_disconnect_during_preflight_releases_undispatched_reservation(self):
        with patch.object(self.provider,'check_context',side_effect=lambda *args:self.service.disconnect_compute('demo',1)):
            with self.assertRaises(ValueError):
                self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(self.provider.calls,0)
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_terminal_success_and_release_share_one_commit(self):
        # A regression to a second release call would reintroduce the crash window.
        from managed_state import State
        with patch.object(State,'release',side_effect=AssertionError('Must release atomically')):
            result=self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(result['state'],'succeeded')
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_lost_receipt_reconciles_without_second_start(self):
        self.provider.lose_response=True
        with self.assertRaises(TimeoutError):self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertIn(self.machine,self.service.managed.snapshot()['reservations'])
        result=self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(result['state'],'succeeded');self.assertEqual(self.provider.calls,1)

    def test_unknown_outcome_keeps_reservation(self):
        with patch.object(self.provider,'dispatch',side_effect=TimeoutError('unknown')):
            with self.assertRaises(TimeoutError):self.service.execute_start(self.op,self.review['review_checksum'])
        result=self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(result['state'],'needs_attention')
        self.assertIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_tampered_review_never_dispatches(self):
        with self.assertRaises(ValueError):self.service.execute_start(self.op,'bad')
        self.assertEqual(self.provider.calls,0)

    def test_disconnect_invalidates_review(self):
        self.service.disconnect_compute('demo',1)
        result=self.service.execute_start(self.op,self.review['review_checksum'])
        self.assertEqual(result['state'],'cancelled');self.assertEqual(self.provider.calls,0)

    def test_crash_after_authorization_resumes_same_operation(self):
        self.service.managed.transition(self.op,'authorized',evidence={'kind':'reviewed_tool_call','checksum':self.review['review_checksum']})
        self.assertEqual(self.service.execute_start(self.op,self.review['review_checksum'])['state'],'succeeded')
        self.assertEqual(self.provider.calls,1)

    def test_cancel_after_dispatch_reconciles_actual_success(self):
        self.provider.lose_response=True
        with self.assertRaises(TimeoutError):self.service.execute_start(self.op,self.review['review_checksum'])
        self.service.managed.cancel(self.op)
        result=self.service.reconcile_power(self.op)
        self.assertEqual(result['state'],'succeeded');self.assertTrue(result['cancel_requested'])
        self.assertEqual(self.provider.calls,1)

    def test_identity_get_failure_releases_without_power_mutation(self):
        from brev_provider import NotDispatched
        with patch.object(self.provider,'dispatch',side_effect=NotDispatched('identity_unverified','No mutation sent')):
            with self.assertRaises(NotDispatched):self.service.execute_start(self.op,self.review['review_checksum'])
        result=self.service.managed.operation(self.op)
        self.assertEqual(result['state'],'failed')
        self.assertEqual(self.provider.calls,0)
        self.assertNotIn(self.machine,self.service.managed.snapshot()['reservations'])

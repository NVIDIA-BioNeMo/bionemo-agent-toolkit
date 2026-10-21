"""Reviewed claim protocol; simulated transport counts are not live qualification."""
import base64,json,shlex,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service
from executor_ownership import checksum
import ownership_operation as ownership_adapter

class OwnershipOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=Service(self.temp.name)
        self.identity=patch('registry.linux_machine_identity',return_value={'linux_machine_id_sha256':'c'*64});self.identity.start();self.addCleanup(self.identity.stop)
        self.service.register_compute('local','gpu','/srv/rfd4','http://127.0.0.1:18769',session_id='s')
        self.machine=self.service.config('s')['target_id']
        self.owner=None;self.committed=False;self.claims=0;self.confirmations=0;self.failure=None
        self.transport=patch.object(self.service,'target_exec',side_effect=self.remote);self.transport.start();self.addCleanup(self.transport.stop)

    def remote(self,cfg,command,timeout=60):
        args=shlex.split(command)
        if args[:3]==['sudo','-n','--']:args=args[3:];privileged=True
        else:privileged=False
        self.assertEqual(args[:3],['/usr/bin/python3' if privileged else 'python3','-I','-c'])
        self.assertEqual(args[3],ownership_adapter.BOOTSTRAP)
        payload=json.loads(base64.b64decode(args[4],validate=True))
        if payload['action']=='claim':
            self.assertTrue(privileged)
            if self.owner is not None and self.owner!=payload['owner']:raise ValueError('foreign owner')
            if self.owner is None:
                if not payload['allow_initial']:raise ValueError('missing owner')
                self.claims+=1
                if self.failure=='before_publication':raise ConnectionError('unknown transport outcome')
                self.owner=payload['owner']
            else:self.confirmations+=1
            if self.failure=='before_commit':raise ConnectionError('publication fsync failed')
            self.committed=True
            if self.failure=='lost_ack':raise ConnectionError('lost acknowledgment')
            return json.dumps({'state':'owned'})
        self.assertEqual(payload['action'],'inspect');self.assertFalse(privileged)
        if self.owner is None:return json.dumps({'state':'unclaimed'})
        if self.owner!=payload['owner']:raise ValueError('foreign owner')
        return json.dumps({'state':'owned' if self.committed else 'pending','owner':self.owner,'owner_checksum':checksum(self.owner)})

    def prepare(self):
        op=self.service.begin_setup('s')
        return self.service.prepare_executor_claim(op['id'],self.machine)

    def test_review_is_read_only_and_execute_once_survives_disconnect_restart(self):
        review=self.prepare();self.assertEqual(self.claims,0)
        result=self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(result['state'],'succeeded');self.assertEqual(self.claims,1)
        self.service.execute_executor_claim(review['operation_id'],review['review_checksum']);self.assertEqual(self.claims,1)
        receipt=self.service.managed.machine(self.machine)['executor_ownership']
        self.service.disconnect_compute('s',1)
        restarted=Service(self.temp.name)
        self.assertEqual(restarted.managed.machine(self.machine)['executor_ownership'],receipt)
        self.assertIsNone(restarted.managed.selection('s')['machine_id'])
        self.assertEqual(restarted.managed.snapshot()['reservations'],{})

    def test_lost_ack_reconciles_existing_owner_without_second_claim(self):
        review=self.prepare();self.failure='lost_ack'
        with self.assertRaises(ConnectionError):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(self.service.managed.operation(review['operation_id'])['state'],'needs_attention')
        self.assertIn(self.machine,self.service.managed.snapshot()['reservations'])
        self.failure=None
        result=self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(result['state'],'succeeded');self.assertEqual((self.claims,self.confirmations),(1,0))

    def test_unknown_unpublished_claim_retains_reservation_and_never_repeats(self):
        review=self.prepare();self.failure='before_publication'
        with self.assertRaises(ConnectionError):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.failure=None
        result=self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(result['state'],'needs_attention');self.assertEqual(self.claims,1)
        with self.assertRaisesRegex(ValueError,'No matching owner'):self.service.confirm_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(self.claims,1);self.assertIn(self.machine,self.service.managed.snapshot()['reservations'])

    def test_pending_publication_requires_explicit_noncreating_confirmation(self):
        review=self.prepare();self.failure='before_commit'
        with self.assertRaises(ConnectionError):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.failure=None
        self.assertEqual(self.service.reconcile_executor_claim(review['operation_id'])['state'],'needs_attention')
        self.assertEqual(self.confirmations,0)
        result=self.service.confirm_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(result['state'],'succeeded');self.assertEqual((self.claims,self.confirmations),(1,1))

    def test_cancel_after_dispatch_keeps_truthful_external_outcome(self):
        review=self.prepare();self.failure='lost_ack'
        with self.assertRaises(ConnectionError):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.service.managed.cancel(review['operation_id'])
        result=self.service.reconcile_executor_claim(review['operation_id'])
        self.assertEqual(result['state'],'succeeded');self.assertTrue(result['cancel_requested']);self.assertEqual(self.claims,1)

    def test_cancel_before_dispatch_has_no_privileged_effect(self):
        review=self.prepare();self.service.managed.cancel(review['operation_id'])
        self.assertEqual(self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])['state'],'cancelled')
        self.assertEqual(self.claims,0)

    def test_changed_review_or_helpers_refuse_before_claim(self):
        review=self.prepare()
        with self.assertRaisesRegex(ValueError,'review changed'):self.service.execute_executor_claim(review['operation_id'],'wrong')
        with patch.object(ownership_adapter,'sources',return_value={'toolchain_paths':'changed','executor_ownership':'changed'}):
            with self.assertRaisesRegex(ValueError,'helper changed'):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(self.claims,0);self.assertEqual(self.service.managed.snapshot()['reservations'],{})

    def test_changed_privileged_bootstrap_invalidates_review(self):
        review=self.prepare()
        with patch.object(ownership_adapter,'BOOTSTRAP','raise RuntimeError("changed bootstrap")'):
            with self.assertRaisesRegex(ValueError,'helper changed'):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(self.claims,0)

    def pending(self):
        review=self.prepare();self.failure='before_commit'
        with self.assertRaises(ConnectionError):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.failure=None
        return review

    def test_cancelled_pending_confirmation_cannot_issue_sudo(self):
        review=self.pending();self.service.managed.cancel(review['operation_id'])
        with self.assertRaisesRegex(ValueError,'cancelled'):self.service.confirm_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual((self.claims,self.confirmations),(1,0))

    def test_changed_machine_or_reservation_blocks_confirmation_before_sudo(self):
        review=self.pending()
        with self.service.managed.transaction() as data:data['machines'][self.machine]['revision']+=1
        with self.assertRaisesRegex(ValueError,'changed'):self.service.confirm_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(self.confirmations,0)
        with self.service.managed.transaction() as data:
            data['machines'][self.machine]['revision']-=1
            data['reservations'][self.machine]['owner_id']='other-operation'
        with self.assertRaisesRegex(ValueError,'changed'):self.service.confirm_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(self.confirmations,0)

    def test_unknown_confirmation_is_not_dispatched_twice(self):
        review=self.pending();self.failure='before_commit'
        with self.assertRaises(ConnectionError):self.service.confirm_executor_claim(review['operation_id'],review['review_checksum'])
        self.failure=None
        result=self.service.confirm_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(result['state'],'needs_attention');self.assertEqual(self.confirmations,1)
        # Simulate the original administrative helper completing late.
        self.committed=True
        self.assertEqual(self.service.reconcile_executor_claim(review['operation_id'])['state'],'succeeded')
        self.assertEqual(self.confirmations,1)

    def test_old_backend_cannot_mutate_claim_state(self):
        self.prepare()
        with patch('managed_state.BACKEND_PROTOCOL',2):
            with self.assertRaisesRegex(ValueError,'backend protocol'):self.service.managed.snapshot()

    def test_changed_root_cannot_confirm_copied_claim(self):
        review=self.prepare();self.failure='lost_ack'
        with self.assertRaises(ConnectionError):self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        with patch.object(self.service,'ownership_identity',return_value=review['owner']|{'controller_root_sha256':'e'*64}):
            with self.assertRaisesRegex(ValueError,'another controller'):self.service.reconcile_executor_claim(review['operation_id'])
        self.assertEqual(self.claims,1)

    def test_already_existing_matching_owner_is_explicitly_confirmed(self):
        self.owner=self.service.ownership_identity(self.machine);self.committed=True
        review=self.prepare();self.assertFalse(review['allow_initial'])
        result=self.service.execute_executor_claim(review['operation_id'],review['review_checksum'])
        self.assertEqual(result['state'],'succeeded');self.assertEqual((self.claims,self.confirmations),(0,1))

if __name__=='__main__':unittest.main()

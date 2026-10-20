"""Remote protocol fault injection without launching a model."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
import remote_job

class RemoteJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        (self.directory/'package-dispatch.lock').touch()

    def test_lost_receipt_never_spawns_twice(self):
        with patch('remote_job.subprocess.Popen') as spawn:
            remote_job.launch(self.directory, 'job')
            retry = remote_job.launch(self.directory, 'job')
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(retry['state'], 'unknown')

    def test_crash_before_spawn_preserves_unknown_and_blocks_retry(self):
        with patch('remote_job.subprocess.Popen', side_effect=OSError('crash')):
            with self.assertRaises(OSError): remote_job.launch(self.directory, 'job')
        with patch('remote_job.subprocess.Popen') as spawn:
            self.assertEqual(remote_job.launch(self.directory, 'job')['state'], 'unknown')
            spawn.assert_not_called()

    def test_reused_pid_is_unknown(self):
        record = {'job_id':'job','state':'running','process':{'pid':12,'start':'100','boot':'old'}}
        remote_job.write(self.directory/'job-state.json', record)
        with patch('remote_job.identity', return_value={'pid':12,'start':'200','boot':'old','process_state':'S'}):
            self.assertEqual(remote_job.status(self.directory, 'job')['state'], 'unknown')

    def test_terminal_receipt_and_identity_validation(self):
        remote_job.write(self.directory/'job-state.json', {'job_id':'job','state':'completed','exit_code':0})
        self.assertEqual(remote_job.status(self.directory,'job')['state'],'completed')
        with self.assertRaises(ValueError): remote_job.status(self.directory,'different')

    def test_recovery_fences_missing_or_accepted_dispatch_without_relaunch(self):
        for accepted in (False,True):
            with self.subTest(accepted=accepted), tempfile.TemporaryDirectory() as home, patch('remote_job.Path.home',return_value=Path(home)):
                marker=self.directory/'job-state.json'
                if marker.exists():marker.unlink()
                if accepted:remote_job.write(marker,{'job_id':'job','state':'accepted'})
                result=remote_job.recover(self.directory,'job')
                self.assertEqual(result['reason'],'orphaned_dispatch_fenced')
                self.assertEqual(result['execution_outcome'],'unknown')
                with patch('remote_job.subprocess.Popen') as spawn:
                    self.assertEqual(remote_job.launch(self.directory,'job')['state'],'failed')
                    spawn.assert_not_called()
                with patch('remote_job.subprocess.run') as model:
                    with self.assertRaisesRegex(ValueError,'not awaiting'):remote_job.supervise(self.directory,'job')
                    model.assert_not_called()

    def test_recovery_refuses_every_live_lease(self):
        import fcntl
        with tempfile.TemporaryDirectory() as home, patch('remote_job.Path.home',return_value=Path(home)):
            lease=Path(home)/'.local/share/bionemo-rfd4';lease.mkdir(parents=True)
            for path in (self.directory/'dispatch.lock',self.directory/'supervisor.lock',lease/'execution.lock'):
                with self.subTest(lease=path.name),path.open('a') as handle:
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    result=remote_job.recover(self.directory,'job')
                    self.assertEqual(result['recovery'],'busy')
                    self.assertFalse((self.directory/'job-state.json').exists())

    def test_recovery_preserves_completed_outcome(self):
        with tempfile.TemporaryDirectory() as home,patch('remote_job.Path.home',return_value=Path(home)):
            receipt={'job_id':'job','state':'completed','exit_code':0}
            remote_job.write(self.directory/'job-state.json',receipt)
            self.assertEqual(remote_job.recover(self.directory,'job'),receipt)

    def test_delayed_supervisor_preserves_fence_while_new_job_owns_executor(self):
        import fcntl
        with tempfile.TemporaryDirectory() as home,patch('remote_job.Path.home',return_value=Path(home)):
            receipt=remote_job.recover(self.directory,'job')
            lease=Path(home)/'.local/share/bionemo-rfd4/execution.lock'
            with lease.open('a') as active:
                fcntl.flock(active,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError,'not awaiting'):
                    remote_job.supervise(self.directory,'job')
            self.assertEqual(remote_job.status(self.directory,'job'),receipt)

    def package_intent(self):
        import hashlib
        digest=hashlib.sha256(b'{}').hexdigest()
        remote_job.write(self.directory/'package-intent.json',{'job_id':'job','transaction':{},'transaction_sha256':digest})
        return digest

    def test_privileged_install_survives_supervisor_terminal_and_free_leases(self):
        digest=self.package_intent()
        marker=self.directory/'job-state.json'
        original={'job_id':'job','state':'failed','exit_code':1}
        remote_job.write(marker,original)
        for state in ('intent','running'):
            with self.subTest(state=state):
                remote_job.write(self.directory/'package-stage.json',{'job_id':'job','state':state,'transaction_sha256':digest})
                self.assertEqual(remote_job.status(self.directory,'job')['state'],'unknown')
                with patch('remote_job.Path.home',return_value=self.directory/'home'):
                    result=remote_job.recover(self.directory,'job')
                self.assertEqual(result['recovery'],'package_installation_unresolved')
                self.assertEqual(json.loads(marker.read_text()),original)
                with patch('remote_job.subprocess.Popen') as spawn:
                    self.assertEqual(remote_job.launch(self.directory,'job')['state'],'unknown')
                    spawn.assert_not_called()
        remote_job.write(self.directory/'package-stage.json',{'job_id':'job','state':'failed','dispatch_not_started':True,'preparation_error':'No package process started','transaction_sha256':digest})
        self.assertEqual(remote_job.status(self.directory,'job'),original)

    def test_unproved_or_foreign_package_completion_cannot_release(self):
        digest=self.package_intent()
        for receipt in ({'job_id':'other','state':'succeeded','package_manager_waited':True},
                        {'job_id':'job','state':'succeeded'}, {'job_id':'job','state':'unexpected'}):
            with self.subTest(receipt=receipt):
                remote_job.write(self.directory/'package-stage.json',dict(receipt,transaction_sha256=digest))
                with self.assertRaises(ValueError):remote_job.status(self.directory,'job')

    def test_missing_stage_receipt_does_not_erase_durable_intent(self):
        self.package_intent()
        self.assertEqual(remote_job.status(self.directory,'job')['package_stage']['state'],'intent')
        with patch('remote_job.Path.home',return_value=self.directory/'home'):
            self.assertEqual(remote_job.recover(self.directory,'job')['recovery'],'package_installation_unresolved')

    def test_receipt_from_another_review_cannot_release(self):
        self.package_intent()
        remote_job.write(self.directory/'package-stage.json',{'job_id':'job','state':'succeeded','package_manager_waited':True,'transaction_sha256':'different'})
        with self.assertRaisesRegex(ValueError,'identity mismatch'):remote_job.status(self.directory,'job')

    def test_other_job_cannot_start_while_machine_package_owner_unresolved(self):
        home=self.directory/'home';lease=home/'.local/share/bionemo-rfd4';lease.mkdir(parents=True)
        installer=self.directory/'installer';installer.mkdir();(installer/'package-dispatch.lock').touch()
        with (lease/'execution.lock').open('a') as lock:
            digest=remote_job.publish_package_intent(installer,'install',{},lock.fileno(),lease)
        next_job=self.directory/'next';next_job.mkdir()
        remote_job.write(next_job/'job-state.json',{'job_id':'next','state':'accepted'})
        with patch('remote_job.Path.home',return_value=home),patch('remote_job.subprocess.run') as run:
            remote_job.supervise(next_job,'next');run.assert_not_called()
        self.assertEqual(remote_job.status(next_job,'next')['package_owner']['job_id'],'install')
        remote_job.write(installer/'package-stage.json',{'job_id':'install','state':'failed','transaction_sha256':digest,'dispatch_not_started':True,'preparation_error':'fenced before dispatch'})
        self.assertIsNone(remote_job.pending_machine_package(lease))
        recovered=self.directory/'recovered';recovered.mkdir()
        remote_job.write(recovered/'job-state.json',{'job_id':'recovered','state':'accepted'})
        from types import SimpleNamespace
        with patch('remote_job.Path.home',return_value=home),patch('remote_job.identity',return_value={'pid':1,'start':'1','boot':'test'}),patch('remote_job.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
            remote_job.supervise(recovered,'recovered');run.assert_called_once()
        self.assertEqual(remote_job.status(recovered,'recovered')['state'],'completed')

    def test_unrelated_descriptor_cannot_publish_package_owner(self):
        lease=self.directory/'lease';lease.mkdir();(lease/'execution.lock').touch()
        with (self.directory/'wrong.lock').open('a') as lock:
            with self.assertRaisesRegex(ValueError,'executor lease'):
                remote_job.publish_package_intent(self.directory,'job',{},lock.fileno(),lease)
        self.assertFalse((lease/'package-owner.json').exists())

    def test_success_boolean_cannot_replace_process_and_inventory_evidence(self):
        digest=self.package_intent()
        receipt={'job_id':'job','state':'succeeded','transaction_sha256':digest,'package_manager_waited':True,'dispatch_started':True,'exit_code':0,'package_process':{'pid':123,'start':'1','boot':'test'},'installed_packages':{}}
        for changes in ({},{'exit_code':100},{'exit_code':None},{'exit_code':False},{'package_process':{}},{'installed_packages':None},{'dispatch_started':False}):
            with self.subTest(changes=changes):
                remote_job.write(self.directory/'package-stage.json',dict(receipt,**changes))
                with self.assertRaises(ValueError):remote_job.status(self.directory,'job')

    def test_terminal_marker_does_not_override_live_stage_lock(self):
        import fcntl
        digest=self.package_intent()
        receipt={'job_id':'job','state':'failed','dispatch_not_started':True,'preparation_error':'before dispatch','transaction_sha256':digest}
        remote_job.write(self.directory/'package-stage.json',receipt)
        with (self.directory/'package-dispatch.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(remote_job.status(self.directory,'job')['state'],'unknown')
        self.assertIsNone(remote_job.pending_package_stage(self.directory,'job'))

    def test_protected_transaction_survives_local_supervisor_failure(self):
        remote_job.write(self.directory/'job-state.json',{'job_id':'job','state':'failed','exit_code':1})
        pending={'job_id':'job','state':'running','transaction_sha256':'digest'}
        with patch('remote_job.pending_protected_package',return_value=pending),patch('remote_job.Path.home',return_value=self.directory/'home'):
            self.assertEqual(remote_job.status(self.directory,'job')['state'],'unknown')
            self.assertEqual(remote_job.recover(self.directory,'job')['recovery'],'package_installation_unresolved')
        self.assertEqual(json.loads((self.directory/'job-state.json').read_text())['exit_code'],1)

    def test_protected_owner_blocks_a_different_executor_job(self):
        remote_job.write(self.directory/'job-state.json',{'job_id':'job','state':'accepted'})
        with patch('remote_job.pending_protected_package',return_value={'job_id':'other','state':'running'}),patch('remote_job.Path.home',return_value=self.directory/'home'),patch('remote_job.subprocess.run') as run:
            remote_job.supervise(self.directory,'job');run.assert_not_called()
        self.assertEqual(json.loads((self.directory/'job-state.json').read_text())['package_owner']['job_id'],'other')

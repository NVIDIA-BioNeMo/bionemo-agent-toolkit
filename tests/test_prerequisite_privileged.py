import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from prerequisite_privileged import adapter,MODULES,BOOTSTRAP

class PrivilegedAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.scripts=Path(self.tmp.name);self.files={}
        source=Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'
        for name in MODULES:
            data=(source/(name+'.py')).read_bytes();(self.scripts/(name+'.py')).write_bytes(data)
            self.files[name+'.py']=hashlib.sha256(data).hexdigest()
        self.review={'files':self.files,'operation_id':'job','prerequisites':{'changes':{}}}
    def test_checksum_bound_sources_are_sent_to_isolated_root_python(self):
        run=Mock(return_value=SimpleNamespace(stdout='{"state":"pending"}'))
        call=adapter(self.review,scripts=self.scripts,run=run)
        self.assertEqual(call('observe','job',self.review['prerequisites'],{},{}),{'state':'pending'})
        args=run.call_args.args[0]
        self.assertEqual(args[:7],['/usr/bin/sudo','-n','/usr/bin/python3','-I','-S','-B','-c'])
        payload=json.loads(run.call_args.kwargs['input'])
        self.assertEqual(set(payload['sources']),set(MODULES))
        self.assertNotIn(str(self.scripts),args)
        compile(BOOTSTRAP,'root-bootstrap','exec')
    def test_changed_or_symlinked_helper_cannot_reach_sudo(self):
        run=Mock();p=self.scripts/'remote_job.py';p.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'differs'):adapter(self.review,scripts=self.scripts,run=run)
        p.unlink();p.symlink_to(self.scripts/'toolchain_paths.py')
        with self.assertRaisesRegex(ValueError,'symlink'):adapter(self.review,scripts=self.scripts,run=run)
        run.assert_not_called()
    def test_mismatched_request_and_lost_ack_never_retry(self):
        run=Mock(side_effect=TimeoutError('uncertain'))
        call=adapter(self.review,scripts=self.scripts,run=run)
        with self.assertRaisesRegex(ValueError,'authorized'):call('launch','different',{}, {},{})
        run.assert_not_called()
        with self.assertRaises(TimeoutError):call('launch','job',self.review['prerequisites'],{}, {})
        self.assertEqual(run.call_count,1)

    def test_recovery_cannot_fence_a_live_executor(self):
        import fcntl
        from unittest.mock import patch
        from prerequisite_privileged import reconcile_reviewed_setup
        lease=self.scripts/'execution.lock';lease.touch();call=Mock()
        with lease.open('a') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch('runtime_setup.validate_setup_review',return_value=self.review),patch('prerequisite_privileged.Path.read_text',return_value='{}'),patch('prerequisite_privileged.adapter',return_value=call):
                result=reconcile_reviewed_setup('recover','/root','job','review','checksum',lease_path=lease)
        self.assertEqual(result['state'],'pending');call.assert_not_called()

    def test_recovery_retains_execution_lease_during_root_call(self):
        import fcntl
        from unittest.mock import patch
        from prerequisite_privileged import reconcile_reviewed_setup
        lease=self.scripts/'execution.lock';lease.touch()
        def root_call(*args):
            with lease.open('a') as other:
                with self.assertRaises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return {'job_id':'job','state':'failed'}
        with patch('runtime_setup.validate_setup_review',return_value=self.review),patch('prerequisite_privileged.Path.read_text',return_value='{}'),patch('prerequisite_privileged.adapter',return_value=root_call),patch('prerequisite_privileged.record_terminal_receipt'):
            result=reconcile_reviewed_setup('recover','/root','job','review','checksum',lease_path=lease)
        self.assertEqual(result['state'],'failed')

    def test_terminal_receipt_resolves_matching_local_intent_only(self):
        from prerequisite_privileged import record_terminal_receipt
        from remote_job import pending_package_stage
        directory=self.scripts/'operation';directory.mkdir()
        tx={'changes':{}};digest=hashlib.sha256(json.dumps(tx,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (directory/'package-intent.json').write_text(json.dumps({'job_id':'job','transaction':tx,'transaction_sha256':digest}))
        receipt={'job_id':'job','transaction_sha256':digest,'state':'failed','dispatch_not_started':True,'preparation_error':'fenced'}
        with self.assertRaisesRegex(ValueError,'does not match'):
            record_terminal_receipt(directory,'job',tx,dict(receipt,job_id='other'))
        self.assertFalse((directory/'package-stage.json').exists())
        record_terminal_receipt(directory,'job',tx,receipt)
        self.assertIsNone(pending_package_stage(directory,'job'))
        with self.assertRaisesRegex(ValueError,'different terminal'):
            record_terminal_receipt(directory,'job',tx,dict(receipt,preparation_error='different fence'))
        self.assertEqual(json.loads((directory/'package-stage.json').read_text()),receipt)
        record_terminal_receipt(directory,'job',tx,receipt)
        self.assertIsNone(pending_package_stage(directory,'job'))

    def test_malformed_terminal_evidence_preserves_existing_receipt(self):
        from prerequisite_privileged import record_terminal_receipt
        directory=self.scripts/'operation';directory.mkdir()
        tx={'changes':{}};digest=hashlib.sha256(json.dumps(tx,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (directory/'package-intent.json').write_text(json.dumps({'job_id':'job','transaction':tx,'transaction_sha256':digest}))
        existing={'job_id':'job','transaction_sha256':digest,'state':'running'}
        path=directory/'package-stage.json';path.write_text(json.dumps(existing));before=path.read_bytes()
        with self.assertRaises(ValueError):
            record_terminal_receipt(directory,'job',tx,dict(existing,state='succeeded'))
        self.assertEqual(path.read_bytes(),before)

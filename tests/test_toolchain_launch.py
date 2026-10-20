import hashlib,json,os,sys,tempfile,unittest,fcntl
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_launch as launch
import toolchain_paths as paths

class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job=self.root/'job';self.job.mkdir()
        self.boot=self.root/'boot';self.boot.write_text('11111111-1111-4111-8111-111111111111')
        self.profile={'packages':{}}
        tx={'profile_sha256':hashlib.sha256(json.dumps(self.profile,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'helper_hashes':{}}
        self.digest=hashlib.sha256(json.dumps(tx,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (self.job/'package-intent.json').write_text(json.dumps({'protocol':1,'job_id':'job','transaction':tx,'transaction_sha256':self.digest}))
        (self.root/'package-owner.json').write_text(json.dumps({'job_id':'job','directory':str(self.job),'transaction_sha256':self.digest}))
        self.process=Mock(return_value=Mock(pid=123))
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        @contextmanager
        def fixture(path):
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
            try:yield fd
            finally:os.close(fd)
        for name,value in [('os.geteuid',lambda:0),('protected_directory',fixture),
             ('read_record',lambda fd,name:paths.read_record(fd,name,owner_uid=os.getuid())),
             ('write_record',lambda fd,name,value:paths.write_record(fd,name,value,owner_uid=os.getuid())),
             ('BOOT_ID',self.boot),('verify_bundle',Mock())]:
            self.stack.enter_context(patch('toolchain_launch.'+name,value))
    def go(self):return launch.launch(self.root,'job',self.root,{},self.profile,{},process=self.process)
    def test_launch_is_detached_and_repeat_does_not_dispatch(self):
        self.assertEqual(self.go()['state'],'dispatch_uncertain')
        self.assertEqual(self.go()['state'],'dispatch_uncertain')
        self.process.assert_called_once()
        args,kwargs=self.process.call_args
        self.assertIn('--scope',args[0]);self.assertTrue(kwargs['start_new_session'])
        self.assertEqual(kwargs['env']['PATH'],'/usr/sbin:/usr/bin:/sbin:/bin')
        self.assertTrue((self.job/'package-launch.json').exists())
    def test_lost_dispatch_ack_is_never_retried(self):
        self.process.side_effect=OSError('unknown boundary')
        with self.assertRaises(OSError):self.go()
        self.assertEqual(self.go()['state'],'dispatch_uncertain')
        self.process.assert_called_once()
    def test_recovery_fence_prevents_launch(self):
        (self.job/'package-stage.json').write_text(json.dumps({'job_id':'job','transaction_sha256':self.digest,'state':'failed','dispatch_not_started':True,'preparation_error':'fenced'}))
        self.assertEqual(self.go()['state'],'already_dispatched');self.process.assert_not_called()
    def test_active_worker_blocks_launch(self):
        with (self.job/'package-dispatch.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'worker is active'):self.go()
        self.process.assert_not_called()
    def test_review_change_cannot_dispatch(self):
        self.profile['changed']=True
        with self.assertRaisesRegex(ValueError,'profile differs'):self.go()
        self.process.assert_not_called()
    def test_unreviewed_helper_hashes_cannot_launch(self):
        with self.assertRaisesRegex(ValueError,'not bound'):
            launch.launch(self.root,'job',self.root,{'unexpected':'hash'},self.profile,{},process=self.process)
        self.process.assert_not_called()
        self.assertFalse((self.job/'package-launch.json').exists())
    def test_bundle_failure_precedes_launch_intent(self):
        launch.verify_bundle.side_effect=ValueError('changed helper')
        with self.assertRaisesRegex(ValueError,'changed helper'):self.go()
        self.assertFalse((self.job/'package-launch.json').exists());self.process.assert_not_called()

class BundleTests(unittest.TestCase):
    def test_unreviewed_modules_or_bytecode_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in launch.BUNDLE_FILES:(root/name).write_bytes(b'')
            (root/'subprocess.py').write_text('unreviewed')
            @contextmanager
            def fixture(path):
                fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
                try:yield fd
                finally:os.close(fd)
            with patch('toolchain_launch.protected_directory',fixture):
                with self.assertRaisesRegex(ValueError,'unreviewed'):
                    launch.verify_bundle(root,{name:hashlib.sha256(b'').hexdigest() for name in launch.BUNDLE_FILES})

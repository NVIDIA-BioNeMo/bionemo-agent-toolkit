import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from contextlib import contextmanager
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_stage as stage
import remote_job
import toolchain_paths

class PrivilegedStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job=self.root/'job';self.job.mkdir()
        self.lease=self.root/'lease';self.lease.mkdir()
        self.archive=self.root/'gcc.deb';self.archive.write_bytes(b'fixture')
        digest=hashlib.sha256(b'fixture').hexdigest()
        self.profile={'packages':{'gcc':{'Version':'11','Size':'7','SHA256':digest}}}
        self.tx={'profile_sha256':hashlib.sha256(json.dumps(self.profile,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'changes':{'gcc':{'version':'11','actions':['Inst','Conf'],'sha256':digest}},'requires_absent_root_dpkg_config':True,'package_configuration':{'fixture':'configuration'}}
        config_patch=patch('toolchain_stage.package_configuration',return_value={'fixture':'configuration'})
        self.configuration=config_patch.start();self.addCleanup(config_patch.stop)
        with (self.lease/'execution.lock').open('a') as lock:
            remote_job.publish_package_intent(self.job,'job',self.tx,lock.fileno(),self.lease)
        self.run=Mock(return_value=SimpleNamespace(stdout='Inst gcc (11 local [amd64])\nConf gcc (11 local [amd64])'))
        self.child=Mock(pid=123);self.child.wait.return_value=0
        self.process=Mock(return_value=self.child)
        scope_patch=patch('toolchain_stage.verify_worker_membership',return_value={
            'state':'pending','populated':True,'active_state':'active','sub_state':'running',
            'unit':'fixture.scope','invocation':'b'*32,'control_group':'/fixture.scope'})
        self.membership=scope_patch.start();self.addCleanup(scope_patch.stop)
        # Capture the real function before patching the shared tempfile module.
        real_mkdtemp=tempfile.mkdtemp
        private_factory=patch('toolchain_stage.tempfile.mkdtemp',side_effect=lambda **kwargs: real_mkdtemp(dir=self.root))
        private_factory.start();self.addCleanup(private_factory.stop)
        self.inspect=Mock(return_value=self.tx)
        self.audit='';self.installed='gcc\tinstall ok installed\t11\n'
        original=self.run.return_value
        def execute_command(args,**kwargs):
            if args[:2]==['dpkg','--audit']:return SimpleNamespace(stdout=self.audit)
            if args[0]=='dpkg-query':return SimpleNamespace(stdout=self.installed)
            return original
        self.run.side_effect=execute_command
    def execute(self):
        @contextmanager
        def fixture_directory(path):
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
            try:yield fd
            finally:os.close(fd)
        with patch('toolchain_stage.protected_directory',side_effect=fixture_directory),patch('toolchain_stage.read_record',side_effect=lambda fd,name:toolchain_paths.read_record(fd,name,owner_uid=os.getuid())),patch('toolchain_stage.write_record',side_effect=lambda fd,name,value:toolchain_paths.write_record(fd,name,value,owner_uid=os.getuid())),patch('toolchain_stage.os.geteuid',return_value=0),patch('toolchain_stage.identity',side_effect=lambda pid:{'pid':pid,'start':'1','boot':'test'}):
            return stage.execute(self.job,'job',self.profile,{'gcc':self.archive},self.lease,run=self.run,inspect=self.inspect,process=self.process)
    def test_verified_local_only_install_waits_before_terminal_receipt(self):
        receipt=self.execute()
        inspected=self.inspect.call_args.kwargs['archives']
        self.assertNotEqual(Path(inspected['gcc']),self.archive)
        self.assertTrue(Path(inspected['gcc']).is_relative_to(Path(receipt['archive_directory'])))
        self.child.wait.assert_called_once()
        self.assertEqual(receipt['state'],'running');self.assertTrue(receipt['package_manager_waited'])
        self.assertTrue(receipt['needs_reconciliation'])
        args=self.process.call_args.args[0]
        self.assertNotIn('--no-download',args);self.assertIn('--no-remove',args)
        for setting in ('Dir::Etc::sourcelist=','Dir::Etc::sourceparts=','Dir::State::lists=','Dir::Cache::archives='):
            path=Path(next(arg.removeprefix(setting) for arg in args if arg.startswith(setting)))
            self.assertTrue(path.is_relative_to(Path(receipt['archive_directory'])))
            self.assertEqual(path.read_text() if path.is_file() else list(path.iterdir()),'' if path.is_file() else [])
        self.assertEqual(receipt['package_process']['pid'],123)
        self.assertIsNotNone(remote_job.pending_machine_package(self.lease))
    def test_worker_outside_scope_cannot_dispatch_packages(self):
        self.membership.side_effect=ValueError('outside authorized scope')
        with self.assertRaisesRegex(ValueError,'outside authorized scope'):self.execute()
        self.process.assert_not_called()
        self.assertFalse((self.job/'package-stage.json').exists())
    def test_changed_review_has_no_dispatch(self):
        self.inspect.return_value={}
        with self.assertRaisesRegex(ValueError,'new review'):self.execute()
        self.process.assert_not_called()
        receipt=json.loads((self.job/'package-stage.json').read_text())
        self.assertEqual(receipt['state'],'failed')
        self.assertTrue(receipt['dispatch_not_started'])
    def test_caller_environment_cannot_redirect_package_commands(self):
        with patch.dict(os.environ,{'PATH':'/tmp/untrusted','APT_CONFIG':'/tmp/apt.conf',
                                   'LD_PRELOAD':'/tmp/loader.so','PYTHONPATH':'/tmp/modules'}):
            self.execute()
        environments=[call.kwargs['env'] for call in self.run.call_args_list]
        environments.append(self.process.call_args.kwargs['env'])
        for environment in environments:
            self.assertEqual(environment['PATH'],'/usr/sbin:/usr/bin:/sbin:/bin')
            self.assertNotEqual(environment.get('APT_CONFIG'),'/tmp/apt.conf')
            for key in ('LD_PRELOAD','PYTHONPATH'):
                self.assertNotIn(key,environment)
    def test_simulation_and_install_share_protected_empty_configuration(self):
        self.execute()
        simulation=next(call for call in self.run.call_args_list if '--simulate' in call.args[0])
        env=simulation.kwargs['env']
        self.assertEqual(env,self.process.call_args.kwargs['env'])
        config=Path(env['APT_CONFIG'])
        self.assertTrue(config.is_relative_to(self.root))
        self.assertEqual(config.stat().st_mode & 0o777,0o600)
        self.assertEqual(config.parent.stat().st_mode & 0o777,0o700)
        self.assertEqual(list((config.parent/'config-parts').iterdir()),[])
        self.assertEqual((config.parent/'empty.conf').read_text(),'')
        self.assertIn('Dir::Etc::parts '+json.dumps(str(config.parent/'config-parts')),config.read_text())
        self.assertIn('Dir::Etc::main '+json.dumps(str(config.parent/'empty.conf')),config.read_text())
        self.assertNotIn('DPkg::Options',config.read_text())
        self.assertNotIn('Debug::NoLocking',config.read_text())
    def test_corrupt_archive_cannot_reach_package_manager(self):
        self.archive.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'checksum'):self.execute()
        self.process.assert_not_called();self.assertIsNone(remote_job.pending_machine_package(self.lease))
        receipt=json.loads((self.job/'package-stage.json').read_text())
        self.assertTrue(receipt['dispatch_not_started'])
    def test_solver_surprise_cannot_dispatch(self):
        self.run.return_value.stdout='Inst driver (1 local)'
        with self.assertRaisesRegex(ValueError,'Unreviewed'):self.execute()
        self.process.assert_not_called()
    def test_configuration_drift_during_preparation_refuses_dispatch(self):
        self.configuration.side_effect=[{'fixture':'configuration'},{'fixture':'changed logger'}]
        with self.assertRaisesRegex(ValueError,'changed before dispatch'):self.execute()
        self.process.assert_not_called()
        receipt=json.loads((self.job/'package-stage.json').read_text())
        self.assertTrue(receipt['dispatch_not_started'])
        self.assertNotIn('dispatch_started',receipt)
    def test_bad_configuration_prevents_privileged_review(self):
        self.configuration.return_value={'fixture':'unsupported'}
        with self.assertRaisesRegex(ValueError,'changed before dispatch'):self.execute()
        self.inspect.assert_not_called()
        self.run.assert_not_called()
        self.process.assert_not_called()
    def test_root_configuration_presence_and_permission_errors_refuse(self):
        root_config=Mock()
        with self.assertRaisesRegex(ValueError,'unsupported'):
            stage.verify_dispatch_configuration(self.tx,root_config)
        root_config.lstat.side_effect=PermissionError('denied')
        with self.assertRaises(PermissionError):
            stage.verify_dispatch_configuration(self.tx,root_config)
        root_config.lstat.side_effect=FileNotFoundError()
        stage.verify_dispatch_configuration(self.tx,root_config)
    def test_lost_process_dispatch_leaves_unknown_and_cannot_retry(self):
        self.process.side_effect=OSError('unknown dispatch boundary')
        with self.assertRaises(OSError):self.execute()
        self.assertEqual(remote_job.status(self.job,'job')['state'],'unknown')
        with self.assertRaisesRegex(ValueError,'already dispatched'):self.execute()
        self.assertEqual(self.process.call_count,1)
    def test_package_failure_is_not_reported_as_success(self):
        self.child.wait.return_value=100
        receipt=self.execute();self.assertEqual(receipt['state'],'running');self.assertTrue(receipt['needs_attention']);self.assertEqual(receipt['exit_code'],100)

    def test_concurrent_dispatch_cannot_pass_review_or_start_apt(self):
        import fcntl
        with (self.job/'package-dispatch.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'still active'):self.execute()
        self.inspect.assert_not_called();self.process.assert_not_called()
        # Once the original lock is free and no dispatch happened, the same
        # reviewed transaction can proceed exactly once.
        self.assertEqual(self.execute()['state'],'running')
        self.process.assert_called_once()

    def test_dispatch_lock_symlink_refused(self):
        target=self.root/'unrelated';target.write_text('preserve')
        (self.job/'package-dispatch.lock').symlink_to(target)
        with self.assertRaises(OSError):self.execute()
        self.assertEqual(target.read_text(),'preserve');self.process.assert_not_called()

    def test_zero_exit_with_wrong_installed_version_is_failed(self):
        self.installed='gcc\tinstall ok installed\t12\n'
        receipt=self.execute()
        self.assertEqual(receipt['exit_code'],0);self.assertEqual(receipt['state'],'running');self.assertTrue(receipt['needs_attention'])
        self.assertIn('versions differ',receipt['verification_error'])

    def test_zero_exit_with_dirty_dpkg_is_failed_without_repair(self):
        self.audit='unconfigured gcc'
        receipt=self.execute();self.assertEqual(receipt['state'],'running');self.assertTrue(receipt['needs_attention'])
        self.assertIn('needs repair',receipt['verification_error'])
        self.assertFalse(any('--configure' in call.args[0] for call in self.run.call_args_list))

    def test_post_dispatch_exception_preserves_archives_for_surviving_child(self):
        self.child.wait.side_effect=OSError('lost wait observation')
        with self.assertRaises(OSError):self.execute()
        receipt=json.loads((self.job/'package-stage.json').read_text())
        self.assertEqual(receipt['state'],'running')
        self.assertEqual((Path(receipt['archive_directory'])/'0.deb').read_bytes(),b'fixture')
        self.assertIsNotNone(remote_job.pending_machine_package(self.lease))

    def test_known_preparation_failure_allows_new_review_without_reinstall(self):
        self.archive.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.execute()
        self.assertIsNone(remote_job.pending_machine_package(self.lease))
        new_job=self.root/'new-review';new_job.mkdir()
        with (self.lease/'execution.lock').open('a') as lock:
            remote_job.publish_package_intent(new_job,'new-review',self.tx,lock.fileno(),self.lease)
        self.assertEqual(remote_job.pending_machine_package(self.lease)['job_id'],'new-review')
        self.process.assert_not_called()

    def test_signalled_package_parent_does_not_release_surviving_child(self):
        import os,signal,subprocess
        child_file=self.root/'surviving-child.pid'
        program=('import subprocess,sys,os,signal; '
                 'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],close_fds=True); '
                 'open(sys.argv[1],"w").write(str(child.pid)); '
                 'os.kill(os.getpid(),signal.SIGTERM)')
        def stand_in(args,**kwargs):
            return subprocess.Popen([sys.executable,'-c',program,str(child_file)],**kwargs)
        self.process=stand_in
        try:
            receipt=self.execute()
            self.assertEqual(receipt['exit_code'],-signal.SIGTERM)
            child_pid=int(child_file.read_text());os.kill(child_pid,0)
            self.assertTrue(receipt['needs_attention'])
            self.assertIsNotNone(remote_job.pending_machine_package(self.lease))
            self.assertTrue((Path(receipt['archive_directory'])/'0.deb').exists())
        finally:
            if child_file.exists():
                try:os.kill(int(child_file.read_text()),signal.SIGTERM)
                except ProcessLookupError:pass

    def test_unprotected_transaction_refused_before_commands(self):
        with patch('toolchain_stage.os.geteuid',return_value=0):
            with self.assertRaises((ValueError,OSError)):
                stage.execute(self.job,'job',self.profile,{'gcc':self.archive},self.lease,run=self.run,inspect=self.inspect,process=self.process)
        self.run.assert_not_called();self.process.assert_not_called()

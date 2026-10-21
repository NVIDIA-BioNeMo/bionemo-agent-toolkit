import sys,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from toolchain_process import observe, verify_worker_membership

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

import hashlib,json,os,sys,tempfile,unittest
from contextlib import contextmanager
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_process as owner
import toolchain_paths as paths

class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.tx={'changes':{}}
        self.digest=hashlib.sha256(json.dumps(self.tx,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def publish(self,job='job',digest=None):
        @contextmanager
        def fixture(path):
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
            try:yield fd
            finally:os.close(fd)
        with patch('toolchain_process.os.geteuid',return_value=0),patch('toolchain_process.protected_directory',side_effect=fixture),patch('toolchain_process.transaction_directory',side_effect=lambda fd,name:paths.transaction_directory(fd,name,owner_uid=os.getuid())),patch('toolchain_process.read_record',side_effect=lambda fd,name:paths.read_record(fd,name,owner_uid=os.getuid())),patch('toolchain_process.write_record',side_effect=lambda fd,name,value:paths.write_record(fd,name,value,owner_uid=os.getuid())):
            return owner.publish(self.root,job,self.tx,digest or self.digest)
    def test_exact_retry_reuses_original_owner(self):
        self.assertFalse(self.publish()['reused'])
        self.assertTrue(self.publish()['reused'])
    def test_other_operation_cannot_replace_pending_owner(self):
        self.publish();before=(self.root/'package-owner.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'reconciled'):self.publish('other')
        self.assertEqual((self.root/'package-owner.json').read_bytes(),before)
    def test_changed_review_cannot_publish(self):
        with self.assertRaisesRegex(ValueError,'checksum'):self.publish(digest='wrong')
        self.assertFalse((self.root/'package-owner.json').exists())
    def test_crash_after_intent_can_finish_owner_publication(self):
        directory=self.root/'job';directory.mkdir()
        (directory/'package-intent.json').write_text(json.dumps({'protocol':1,'job_id':'job','transaction':self.tx,'transaction_sha256':self.digest}))
        self.assertTrue(self.publish()['reused'])
        self.assertEqual(json.loads((self.root/'package-owner.json').read_text())['job_id'],'job')

    def test_old_unpublished_intent_cannot_replace_later_terminal_owner(self):
        directory=self.root/'old';directory.mkdir()
        (directory/'package-intent.json').write_text(json.dumps({'protocol':1,'job_id':'old','transaction':self.tx,'transaction_sha256':self.digest}))
        self.publish('new')
        (self.root/'new'/'package-dispatch.lock').touch()
        (self.root/'new'/'package-stage.json').write_text(json.dumps({'job_id':'new','transaction_sha256':self.digest,'state':'failed','dispatch_not_started':True,'preparation_error':'no dispatch'}))
        with self.assertRaisesRegex(ValueError,'superseded'):self.publish('old')
        self.assertEqual(json.loads((self.root/'package-owner.json').read_text())['job_id'],'new')

import hashlib,json,sys,tempfile,unittest
from unittest.mock import Mock,patch
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_process as stage
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
        config_patch=patch('toolchain_process.package_configuration',return_value={'fixture':'configuration'})
        self.configuration=config_patch.start();self.addCleanup(config_patch.stop)
        with (self.lease/'execution.lock').open('a') as lock:
            remote_job.publish_package_intent(self.job,'job',self.tx,lock.fileno(),self.lease)
        self.run=Mock(return_value=SimpleNamespace(stdout='Inst gcc (11 local [amd64])\nConf gcc (11 local [amd64])'))
        self.child=Mock(pid=123);self.child.wait.return_value=0
        self.process=Mock(return_value=self.child)
        scope_patch=patch('toolchain_process.verify_worker_membership',return_value={
            'state':'pending','populated':True,'active_state':'active','sub_state':'running',
            'unit':'fixture.scope','invocation':'b'*32,'control_group':'/fixture.scope'})
        self.membership=scope_patch.start();self.addCleanup(scope_patch.stop)
        # Capture the real function before patching the shared tempfile module.
        real_mkdtemp=tempfile.mkdtemp
        private_factory=patch('toolchain_process.tempfile.mkdtemp',side_effect=lambda **kwargs: real_mkdtemp(dir=self.root))
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
        with patch('toolchain_process.protected_directory',side_effect=fixture_directory),patch('toolchain_process.read_record',side_effect=lambda fd,name:toolchain_paths.read_record(fd,name,owner_uid=os.getuid())),patch('toolchain_process.write_record',side_effect=lambda fd,name,value:toolchain_paths.write_record(fd,name,value,owner_uid=os.getuid())),patch('toolchain_process.os.geteuid',return_value=0),patch('toolchain_process.identity',side_effect=lambda pid:{'pid':pid,'start':'1','boot':'test'}):
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
        with patch('toolchain_process.os.geteuid',return_value=0):
            with self.assertRaises((ValueError,OSError)):
                stage.execute(self.job,'job',self.profile,{'gcc':self.archive},self.lease,run=self.run,inspect=self.inspect,process=self.process)
        self.run.assert_not_called();self.process.assert_not_called()

import hashlib,json,os,sys,tempfile,unittest,fcntl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_process as recovery

class PreparationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job=self.root/'job';self.job.mkdir()
        self.digest=hashlib.sha256(b'{}').hexdigest()
        (self.job/'package-intent.json').write_text(json.dumps({'protocol':1,'job_id':'job','transaction':{},'transaction_sha256':self.digest}))
        (self.root/'package-owner.json').write_text(json.dumps({'job_id':'job','directory':str(self.job),'transaction_sha256':self.digest}))
    def recover(self, **kwargs):
        @contextmanager
        def fixture(path):
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
            try:yield fd
            finally:os.close(fd)
        with patch('toolchain_process.os.geteuid',return_value=0),patch('toolchain_process.protected_directory',side_effect=fixture),patch('toolchain_process.read_record',side_effect=lambda fd,name:paths.read_record(fd,name,owner_uid=os.getuid())),patch('toolchain_process.write_record',side_effect=lambda fd,name,value:paths.write_record(fd,name,value,owner_uid=os.getuid())):
            return recovery.recover_preparation(self.root,'job',**kwargs)
    def test_missing_receipt_is_fenced_and_recovery_is_repeatable(self):
        result=self.recover();self.assertTrue(result['dispatch_not_started'])
        self.assertIsNone(remote_job.pending_machine_package(self.root))
        self.assertEqual(self.recover(),result)
    def test_live_stage_cannot_be_fenced(self):
        with (self.job/'package-dispatch.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'still active'):self.recover()
        self.assertFalse((self.job/'package-stage.json').exists())
        self.assertTrue(self.recover()['dispatch_not_started'])
    def test_ambiguous_dispatch_retains_owner_and_receipt(self):
        receipt={'job_id':'job','state':'running','transaction_sha256':self.digest,'dispatch_started':True}
        path=self.job/'package-stage.json';path.write_text(json.dumps(receipt));before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'may have started'):self.recover()
        self.assertEqual(path.read_bytes(),before);self.assertIsNotNone(remote_job.pending_machine_package(self.root))
    def test_unknown_old_protocol_is_not_reinterpreted(self):
        path=self.job/'package-intent.json';record=json.loads(path.read_text());record.pop('protocol');path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'older preparation'):self.recover()
        self.assertFalse((self.job/'package-stage.json').exists())

    def test_reboot_recovery_retains_unknown_outcome_but_allows_new_review(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        old='11111111-1111-4111-8111-111111111111';new='22222222-2222-4222-8222-222222222222'
        receipt={'job_id':'job','state':'running','transaction_sha256':self.digest,'dispatch_started':True,'supervisor':{'boot':old}}
        path=self.job/'package-stage.json';path.write_text(json.dumps(receipt))
        boot=self.root/'boot';boot.write_text(old)
        locks=[self.root/'frontend',self.root/'dpkg']
        for lock in locks:lock.touch()
        run=Mock(return_value=SimpleNamespace(stdout=''))
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.PACKAGE_LOCKS',locks):
            with self.assertRaisesRegex(ValueError,'Same-boot'):self.recover(reconcile_reboot=True,run=run)
            run.assert_not_called()
            boot.write_text(new);run.return_value.stdout='unfinished package'
            with self.assertRaisesRegex(ValueError,'requires repair'):self.recover(reconcile_reboot=True,run=run)
            self.assertEqual(json.loads(path.read_text()),receipt)
            run.return_value.stdout=''
            result=self.recover(reconcile_reboot=True,run=run)
        self.assertEqual(result['execution_outcome'],'unknown')
        self.assertEqual(result['state'],'failed')
        self.assertIsNone(remote_job.pending_machine_package(self.root))

    def scoped_fixture(self):
        from toolchain_process import scope_name
        profile={'packages':{'gcc':{'Version':'11'}}}
        tx={'profile_sha256':hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'changes':{'gcc':{'version':'11'}}}
        self.digest=hashlib.sha256(json.dumps(tx,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (self.job/'package-intent.json').write_text(json.dumps({'protocol':1,'job_id':'job','transaction':tx,'transaction_sha256':self.digest}))
        (self.root/'package-owner.json').write_text(json.dumps({'job_id':'job','directory':str(self.job),'transaction_sha256':self.digest}))
        boot=self.root/'boot';boot.write_text('11111111-1111-4111-8111-111111111111')
        unit=scope_name('job',self.digest)
        receipt={'job_id':'job','state':'running','transaction_sha256':self.digest,'dispatch_started':True,
                 'supervisor':{'boot':boot.read_text()},'scope':{'unit':unit,'control_group':'/system.slice/'+unit,
                 'populated':True,'active_state':'active','sub_state':'running','invocation':'a'*32}}
        (self.job/'package-stage.json').write_text(json.dumps(receipt))
        locks=[self.root/'frontend',self.root/'dpkg']
        for lock in locks:lock.touch()
        self.observed={'state':'absent','unit':unit}
        return profile,boot,locks,receipt

    def test_same_boot_absent_scope_reconciles_without_claiming_success(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t11\n')])
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.PACKAGE_LOCKS',locks),patch('toolchain_process.observe',return_value=self.observed):
            result=self.recover(profile=profile,run=run)
        self.assertEqual(result['state'],'failed');self.assertEqual(result['execution_outcome'],'unknown')
        self.assertEqual(result['installed_packages'],{'gcc':'11'})
        self.assertIsNone(remote_job.pending_machine_package(self.root))
        self.assertEqual([call.args[0][0] for call in run.call_args_list],['dpkg','dpkg-query'])

    def test_live_or_unreadable_scope_retains_owner_without_package_checks(self):
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture();run=Mock()
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.observe') as observe:
            observe.return_value=dict(self.observed,state='pending')
            with self.assertRaisesRegex(ValueError,'still has activity'):self.recover(profile=profile,run=run)
            observe.side_effect=PermissionError('denied')
            with self.assertRaises(PermissionError):self.recover(profile=profile,run=run)
        run.assert_not_called()
        self.assertEqual(json.loads((self.job/'package-stage.json').read_text()),receipt)
        self.assertIsNotNone(remote_job.pending_machine_package(self.root))

    def test_dirty_or_mismatched_packages_do_not_release_scope_owner(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.PACKAGE_LOCKS',locks),patch('toolchain_process.observe',return_value=self.observed):
            with self.assertRaisesRegex(ValueError,'needs repair'):
                self.recover(profile=profile,run=Mock(return_value=SimpleNamespace(stdout='unfinished')))
            with self.assertRaisesRegex(ValueError,'versions differ'):
                self.recover(profile=profile,run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t12\n')]))
        self.assertEqual(json.loads((self.job/'package-stage.json').read_text()),receipt)

    def test_changed_profile_cannot_reconcile(self):
        profile,boot,locks,receipt=self.scoped_fixture()
        profile['packages']['gcc']['Version']='12'
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.observe') as observe:
            with self.assertRaisesRegex(ValueError,'profile differs'):self.recover(profile=profile)
        observe.assert_not_called()

    def test_normal_completion_requires_waited_zero_exit_and_is_repeatable(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        receipt.update(package_manager_waited=True,exit_code=0,needs_attention=True,verification_error='old verification error',package_process={'pid':123,'start':'456','boot':boot.read_text()})
        (self.job/'package-stage.json').write_text(json.dumps(receipt))
        run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t11\n')])
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.PACKAGE_LOCKS',locks),patch('toolchain_process.observe',return_value=self.observed):
            result=self.recover(profile=profile,finalize_success=True,run=run)
            self.assertEqual(self.recover(profile=profile,finalize_success=True,run=run),result)
        self.assertEqual(result['state'],'succeeded')
        self.assertNotIn('needs_attention',result)
        self.assertNotIn('verification_error',result)
        self.assertIsNone(remote_job.pending_machine_package(self.root))
        self.assertEqual(run.call_count,2)

    def test_matching_packages_without_exit_evidence_cannot_claim_success(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.PACKAGE_LOCKS',locks),patch('toolchain_process.observe',return_value=self.observed):
            for extra in ({},{'package_manager_waited':True,'exit_code':1},{'package_manager_waited':True,'exit_code':False}):
                candidate=dict(receipt,**extra);(self.job/'package-stage.json').write_text(json.dumps(candidate))
                run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t11\n')])
                with self.assertRaisesRegex(ValueError,'successful process receipt'):
                    self.recover(profile=profile,finalize_success=True,run=run)
                self.assertEqual(json.loads((self.job/'package-stage.json').read_text()),candidate)

    def test_interrupted_recovery_is_never_later_promoted_to_success(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        receipt.update(package_manager_waited=True,exit_code=0,package_process={'pid':123,'start':'456','boot':boot.read_text()})
        (self.job/'package-stage.json').write_text(json.dumps(receipt))
        run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t11\n')])
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.PACKAGE_LOCKS',locks),patch('toolchain_process.observe',return_value=self.observed):
            result=self.recover(profile=profile,run=run)
            self.assertEqual(result['state'],'failed')
            self.assertEqual(self.recover(profile=profile,finalize_success=True,run=run),result)

    def test_normal_completion_rejects_other_boot_and_surviving_descendants(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        receipt.update(package_manager_waited=True,exit_code=0,package_process={'pid':123,'start':'456','boot':'22222222-2222-4222-8222-222222222222'})
        path=self.job/'package-stage.json';path.write_text(json.dumps(receipt))
        with patch('toolchain_process.BOOT_ID_PATH',boot),patch('toolchain_process.PACKAGE_LOCKS',locks),patch('toolchain_process.observe',return_value=self.observed) as observe:
            run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t11\n')])
            with self.assertRaisesRegex(ValueError,'successful process receipt'):
                self.recover(profile=profile,finalize_success=True,run=run)
            self.assertEqual(json.loads(path.read_text()),receipt)
            receipt['package_process']['boot']=boot.read_text();path.write_text(json.dumps(receipt))
            observe.return_value=dict(self.observed,state='pending')
            run=Mock()
            with self.assertRaisesRegex(ValueError,'still has activity'):
                self.recover(profile=profile,finalize_success=True,run=run)
            run.assert_not_called()
            self.assertEqual(json.loads(path.read_text()),receipt)

from contextlib import contextmanager,ExitStack
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_process as launch

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
            self.stack.enter_context(patch('toolchain_process.'+name,value))
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
            with patch('toolchain_process.protected_directory',fixture):
                with self.assertRaisesRegex(ValueError,'unreviewed'):
                    launch.verify_bundle(root,{name:hashlib.sha256(b'').hexdigest() for name in launch.BUNDLE_FILES})

if __name__ == "__main__": unittest.main()

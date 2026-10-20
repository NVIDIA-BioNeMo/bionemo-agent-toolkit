import hashlib,json,os,sys,tempfile,unittest,fcntl
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import toolchain_recovery as recovery
import toolchain_paths as paths
import remote_job

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
        with patch('toolchain_recovery.os.geteuid',return_value=0),patch('toolchain_recovery.protected_directory',side_effect=fixture),patch('toolchain_recovery.read_record',side_effect=lambda fd,name:paths.read_record(fd,name,owner_uid=os.getuid())),patch('toolchain_recovery.write_record',side_effect=lambda fd,name,value:paths.write_record(fd,name,value,owner_uid=os.getuid())):
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
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.PACKAGE_LOCKS',locks):
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
        from toolchain_scope import scope_name
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
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.PACKAGE_LOCKS',locks),patch('toolchain_recovery.observe',return_value=self.observed):
            result=self.recover(profile=profile,run=run)
        self.assertEqual(result['state'],'failed');self.assertEqual(result['execution_outcome'],'unknown')
        self.assertEqual(result['installed_packages'],{'gcc':'11'})
        self.assertIsNone(remote_job.pending_machine_package(self.root))
        self.assertEqual([call.args[0][0] for call in run.call_args_list],['dpkg','dpkg-query'])

    def test_live_or_unreadable_scope_retains_owner_without_package_checks(self):
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture();run=Mock()
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.observe') as observe:
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
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.PACKAGE_LOCKS',locks),patch('toolchain_recovery.observe',return_value=self.observed):
            with self.assertRaisesRegex(ValueError,'needs repair'):
                self.recover(profile=profile,run=Mock(return_value=SimpleNamespace(stdout='unfinished')))
            with self.assertRaisesRegex(ValueError,'versions differ'):
                self.recover(profile=profile,run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t12\n')]))
        self.assertEqual(json.loads((self.job/'package-stage.json').read_text()),receipt)

    def test_changed_profile_cannot_reconcile(self):
        profile,boot,locks,receipt=self.scoped_fixture()
        profile['packages']['gcc']['Version']='12'
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.observe') as observe:
            with self.assertRaisesRegex(ValueError,'profile differs'):self.recover(profile=profile)
        observe.assert_not_called()

    def test_normal_completion_requires_waited_zero_exit_and_is_repeatable(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        receipt.update(package_manager_waited=True,exit_code=0,needs_attention=True,verification_error='old verification error',package_process={'pid':123,'start':'456','boot':boot.read_text()})
        (self.job/'package-stage.json').write_text(json.dumps(receipt))
        run=Mock(side_effect=[SimpleNamespace(stdout=''),SimpleNamespace(stdout='gcc\tinstall ok installed\t11\n')])
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.PACKAGE_LOCKS',locks),patch('toolchain_recovery.observe',return_value=self.observed):
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
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.PACKAGE_LOCKS',locks),patch('toolchain_recovery.observe',return_value=self.observed):
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
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.PACKAGE_LOCKS',locks),patch('toolchain_recovery.observe',return_value=self.observed):
            result=self.recover(profile=profile,run=run)
            self.assertEqual(result['state'],'failed')
            self.assertEqual(self.recover(profile=profile,finalize_success=True,run=run),result)

    def test_normal_completion_rejects_other_boot_and_surviving_descendants(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        profile,boot,locks,receipt=self.scoped_fixture()
        receipt.update(package_manager_waited=True,exit_code=0,package_process={'pid':123,'start':'456','boot':'22222222-2222-4222-8222-222222222222'})
        path=self.job/'package-stage.json';path.write_text(json.dumps(receipt))
        with patch('toolchain_recovery.BOOT_ID_PATH',boot),patch('toolchain_recovery.PACKAGE_LOCKS',locks),patch('toolchain_recovery.observe',return_value=self.observed) as observe:
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

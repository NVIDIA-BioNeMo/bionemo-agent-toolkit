import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from runtime_setup import setup, SetupCancelled

class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'model').mkdir()
        (self.root/'model/setup.sh').write_bytes(b'pinned installer')
        self.lock=self.root/'execution.lock';self.calls=[];self.fail=False;self.smoke_fail=False
        self.recipe={'id':'test','model_revision':'fixed','source_hashes':{'setup.sh':hashlib.sha256(b'pinned installer').hexdigest()},'weights':[],'weights_base_url':'https://example'}
    def runner(self,args,**kwargs):
        self.calls.append(args)
        if args[0]=='git':return SimpleNamespace(stdout='fixed\n')
        if args[0]=='locked-installer':
            self.assertTrue(kwargs['pass_fds'])
            self.assertEqual(kwargs['env']['PYTHONDONTWRITEBYTECODE'],'1')
            if self.fail:raise RuntimeError('installer interrupted')
            return SimpleNamespace(stdout='')
        if args[0].endswith('rfd4-generate'):
            if self.smoke_fail:raise RuntimeError('GPU smoke failed')
            return SimpleNamespace(stdout='')
        if '-c' in args and 'setup-smoke' in args[-1]:
            return SimpleNamespace(stdout=json.dumps({'structures':[{'path':'result.cif','atoms':10,'size':100,'sha256':'a'*64}]}))
        return SimpleNamespace(stdout=json.dumps({'recipe_id':'test','checks':{k:True for k in ['platform','python','revision','source','dependencies','entrypoint','weights','cuda','gpu']}}))
    def invoke(self, **options):
        with patch('runtime_setup.verify_source',return_value=True), patch('runtime_setup.install',side_effect=lambda root,**kw: (kw['run'](['locked-installer'],pass_fds=kw['pass_fds'],env={'PYTHONDONTWRITEBYTECODE':'1'}), {'lock_sha256':'verified'})[1]):
            return setup(self.root,recipe=self.recipe,run=self.runner,lock_path=self.lock,operation_id="setup-test",**options)
    def test_locked_installer_and_smoke_acceptance(self):
        result=self.invoke()
        self.assertEqual(self.calls[1],['locked-installer'])
        self.assertEqual(result['stage'],'accepted');self.assertTrue(result['ready'])
        self.assertEqual(result['installation']['lock_sha256'],'verified')
        command=next(c for c in self.calls if c[0].endswith('rfd4-generate'))
        self.assertTrue(any(a.startswith('hydra.run.dir='+str(self.root.resolve()/'setup-smoke')) for a in command))
    def test_interrupted_install_can_resume(self):
        self.fail=True
        with self.assertRaises(RuntimeError):self.invoke()
        self.assertEqual(json.loads((self.root/'runtime-setup.json').read_text())['stage'],'needs_attention')
        self.fail=False
        self.assertEqual(self.invoke()['stage'],'accepted')
    def test_modified_installer_never_executes(self):
        (self.root/'model/setup.sh').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Modified installer'):self.invoke()
        self.assertEqual(len(self.calls),1)
    def test_active_remote_job_blocks_all_setup_steps(self):
        with self.lock.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'Runtime is in use'):self.invoke()
        self.assertEqual(self.calls,[])

    def test_setup_can_use_its_supervisors_inherited_lock(self):
        with self.lock.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch.dict(os.environ,{'RFD4_EXECUTION_LOCK_FD':str(lock.fileno())}):
                self.assertEqual(self.invoke()['stage'],'accepted')
            # Closing the setup helper's duplicate must not release supervisor ownership.
            with self.lock.open('a') as other:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_unrelated_inherited_descriptor_is_rejected(self):
        self.lock.touch()
        with (self.root/'unrelated').open('a') as unrelated:
            with patch.dict(os.environ,{'RFD4_EXECUTION_LOCK_FD':str(unrelated.fileno())}):
                with self.assertRaisesRegex(ValueError,'does not match'):
                    self.invoke()
        self.assertEqual(self.calls,[])

    def test_failed_smoke_never_accepts_runtime(self):
        self.smoke_fail=True
        with self.assertRaisesRegex(RuntimeError,'GPU smoke failed'):self.invoke()
        state=json.loads((self.root/'runtime-setup.json').read_text())
        self.assertFalse(state['ready']);self.assertEqual(state['stage'],'needs_attention')

    def test_cancel_before_install_starts_no_installer(self):
        marker=self.root/'setup-operations/setup-test/cancel-requested'
        marker.parent.mkdir(parents=True);marker.touch()
        with self.assertRaises(SetupCancelled):self.invoke()
        self.assertFalse(any(call[0]=='locked-installer' for call in self.calls))
        state=json.loads((self.root/'runtime-setup.json').read_text())
        self.assertEqual(state['stage'],'cancelled');self.assertFalse(state['ready'])

    def test_cancel_during_installer_prevents_smoke_and_downloads(self):
        original=self.runner
        def cancel_after_install(args,**kwargs):
            result=original(args,**kwargs)
            if args[0]=='locked-installer':
                marker=self.root/'setup-operations/setup-test/cancel-requested'
                marker.parent.mkdir(parents=True);marker.touch()
            return result
        with patch.object(self,'runner',side_effect=cancel_after_install):
            with self.assertRaises(SetupCancelled):self.invoke()
        self.assertEqual(len(self.calls),2)
        self.assertFalse((self.root/'setup-smoke').exists())

    def test_cancel_at_smoke_stage_boundary_allows_current_stage_to_finish(self):
        import runtime_setup
        original=runtime_setup.write_journal
        def journal(path,value):
            original(path,value)
            if value['stage']=='smoke_running':
                marker=self.root/'setup-operations/setup-test/cancel-requested'
                marker.parent.mkdir(parents=True);marker.touch()
        with patch('runtime_setup.write_journal',side_effect=journal):
            result=self.invoke()
        self.assertEqual(result['stage'],'accepted')
        self.assertEqual(sum(call[0].endswith('rfd4-generate') for call in self.calls),1)

    def test_cancel_during_smoke_records_actual_success(self):
        original=self.runner
        def cancel_in_smoke(args,**kwargs):
            if args[0].endswith('rfd4-generate'):
                marker=self.root/'setup-operations/setup-test/cancel-requested'
                marker.parent.mkdir(parents=True);marker.touch()
            return original(args,**kwargs)
        with patch.object(self,'runner',side_effect=cancel_in_smoke):
            result=self.invoke()
        self.assertTrue(result['ready'])
        self.assertEqual(result['stage'],'accepted')

    def test_cancel_before_staging_writes_terminal_journal(self):
        (self.root/'model/setup.sh').unlink();(self.root/'model').rmdir()
        marker=self.root/'setup-operations/setup-test/cancel-requested'
        marker.parent.mkdir(parents=True);marker.touch()
        with patch('runtime_setup.stage') as staging:
            with self.assertRaises(SetupCancelled):self.invoke()
            staging.assert_not_called()
        journal=json.loads((self.root/'runtime-setup.json').read_text())
        self.assertEqual(journal['operation_id'],'setup-test')
        self.assertEqual(journal['stage'],'cancelled')

    def test_failed_staging_with_cancel_retains_actual_failure_journal(self):
        (self.root/'model/setup.sh').unlink();(self.root/'model').rmdir()
        def failure(*args,**kwargs):
            marker=self.root/'setup-operations/setup-test/cancel-requested'
            marker.parent.mkdir(parents=True);marker.touch()
            raise ValueError('Repository access unavailable')
        with patch('runtime_setup.stage',side_effect=failure):
            with self.assertRaisesRegex(ValueError,'Repository access'):self.invoke()
        journal=json.loads((self.root/'runtime-setup.json').read_text())
        self.assertEqual(journal['operation_id'],'setup-test')
        self.assertEqual(journal['stage'],'needs_attention')
        self.assertFalse(journal['ready'])
        self.assertFalse(any(call[0]=='locked-installer' for call in self.calls))

    def test_post_smoke_runtime_change_never_becomes_ready(self):
        original=self.runner
        ran_smoke=False
        def mutated(args,**kwargs):
            nonlocal ran_smoke
            if args[0].endswith('rfd4-generate'):ran_smoke=True
            result=original(args,**kwargs)
            if ran_smoke and '-c' in args and 'setup-smoke' not in args[-1]:
                value=json.loads(result.stdout)
                value['checks']['source']=False
                result.stdout=json.dumps(value)
            return result
        with patch.object(self,'runner',side_effect=mutated):
            with self.assertRaisesRegex(ValueError,'after smoke'):self.invoke()
        state=json.loads((self.root/'runtime-setup.json').read_text())
        self.assertFalse(state['ready']);self.assertEqual(state['stage'],'needs_attention')

    def test_reviewed_prerequisites_run_under_existing_lease_before_install(self):
        def prerequisite(root,operation,reviewed,**kwargs):
            self.assertEqual(operation,'setup-test')
            with self.lock.open('a') as other:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertFalse(any(call[0]=='locked-installer' for call in self.calls))
            kwargs['journal']('prerequisites_reconciling')
            return {'state':'not_needed'}
        with patch('prerequisite_setup.install_prerequisites',side_effect=prerequisite):
            self.assertEqual(self.invoke(reviewed={'test':True})['prerequisites'],{'state':'not_needed'})
        self.calls=[]
        with patch('prerequisite_setup.install_prerequisites',side_effect=RuntimeError('package pending')):
            with self.assertRaisesRegex(RuntimeError,'package pending'):self.invoke(reviewed={'test':True})
        self.assertFalse(any(call[0]=='locked-installer' for call in self.calls))
        self.assertFalse(json.loads((self.root/'runtime-setup.json').read_text())['ready'])


    def prerequisite_seam(self, lost_ack=False):
        from functools import partial
        from prerequisite_setup import install_prerequisites
        from remote_job import pending_machine_package
        profile=json.loads(Path(sys.modules['runtime_setup'].__file__).with_name('toolchain_profile.json').read_text())
        digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        tx={'profile_sha256':digest(profile),'helper_hashes':{},'changes':{'gcc':{'version':'11'}}}
        directory=self.root/'setup-operations/setup-test';directory.mkdir(parents=True)
        unit='rfd4-package-'+hashlib.sha256(('setup-test\0'+digest(tx)).encode()).hexdigest()[:32]+'.scope'
        boot='22222222-2222-4222-8222-222222222222'
        receipt={'job_id':'setup-test','transaction_sha256':digest(tx),'state':'succeeded',
            'package_manager_waited':True,'dispatch_started':True,'exit_code':0,
            'package_process':{'pid':123,'start':'456','boot':boot},
            'supervisor':{'boot':boot},'recovery_boot':boot,'scope_quiescent':True,
            'package_database_clean':True,'package_locks_verified':True,
            'installed_packages':{'gcc':'11'},
            'scope':{'unit':unit,'control_group':'/system.slice/'+unit,'populated':True,
                     'active_state':'active','sub_state':'running','invocation':'a'*32},
            'scope_observation':{'unit':unit,'state':'absent'}}
        actions=[]
        def privileged(action,*args):
            actions.append(action)
            intent=json.loads((directory/'package-intent.json').read_text())
            self.assertEqual(intent['transaction'],tx)
            with self.lock.open('a') as other:
                with self.assertRaises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertFalse(any(call[0]=='locked-installer' for call in self.calls))
            if action=='launch' and lost_ack:raise TimeoutError('package acknowledgment lost')
            return receipt
        original_runner=self.runner
        def runner(args,**kwargs):
            if args[0]=='locked-installer':
                self.assertEqual(json.loads((directory/'package-stage.json').read_text()),receipt)
                self.assertIsNone(pending_machine_package(self.root))
            return original_runner(args,**kwargs)
        coordinator=partial(install_prerequisites,review=lambda profile:dict(tx),download=lambda *a,**kw:{})
        with patch('prerequisite_setup.install_prerequisites',coordinator),patch.object(self,'runner',side_effect=runner):
            if lost_ack:
                with self.assertRaisesRegex(TimeoutError,'acknowledgment lost'):
                    self.invoke(reviewed={'prerequisites':tx},privileged=privileged)
            else:self.assertTrue(self.invoke(reviewed={'prerequisites':tx},privileged=privileged)['ready'])
        if lost_ack:
            self.assertEqual(actions,['publish','launch'])
            self.assertFalse(any(call[0]=='locked-installer' or call[0].endswith('rfd4-generate') for call in self.calls))
            self.assertFalse(json.loads((self.root/'runtime-setup.json').read_text())['ready'])
            self.assertEqual(pending_machine_package(self.root)['job_id'],'setup-test')
        else:self.assertEqual(actions,['publish','launch','observe'])

    def test_real_prerequisite_coordinator_records_terminal_before_native_install(self):
        self.prerequisite_seam()

    def test_real_prerequisite_coordinator_lost_ack_preserves_pending_ownership(self):
        self.prerequisite_seam(lost_ack=True)


class SetupReviewBindingTests(unittest.TestCase):
    def setUp(self):
        from runtime_recipe import RECIPE
        from toolchain_process import BUNDLE_FILES
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.scripts=self.root/'scripts';self.scripts.mkdir()
        source=Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'
        self.files={}
        for name in BUNDLE_FILES|{'runtime_setup.py','toolchain_profile.json'}:
            content=(source/name).read_bytes();(self.scripts/name).write_bytes(content)
            self.files[name]=hashlib.sha256(content).hexdigest()
        self.recipe={k:v for k,v in RECIPE.items() if k!='install_mode'}
        self.review={'operation_id':'setup-test','action':'setup','remote_root':'/srv/rfd4',
          'recipe_id':self.recipe['id'],'recipe':self.recipe,'recipe_checksum':self.digest(self.recipe),
          'files':self.files,'prerequisites':{'profile_sha256':self.digest(json.loads((self.scripts/'toolchain_profile.json').read_text())),
          'helper_hashes':{name:self.files[name] for name in BUNDLE_FILES}}}
        self.path=self.root/'review.json'
    def digest(self,value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def validate(self,**kwargs):
        from runtime_setup import validate_setup_review
        self.path.write_text(json.dumps(self.review))
        return validate_setup_review(self.path,kwargs.pop('checksum',self.digest(self.review)),kwargs.pop('root','/srv/rfd4'),kwargs.pop('operation','setup-test'),scripts=self.scripts,recipe=self.recipe)
    def test_review_binds_operation_recipe_profile_and_source(self):
        self.assertEqual(self.validate(),self.review)
        with self.assertRaisesRegex(ValueError,'checksum'):self.validate(checksum='0'*64)
        with self.assertRaisesRegex(ValueError,'identity'):self.validate(operation='different')
        with self.assertRaisesRegex(ValueError,'identity'):self.validate(root='/srv/other')
        self.review['recipe_checksum']='0'*64
        with self.assertRaisesRegex(ValueError,'recipe'):self.validate()
    def test_changed_source_or_symlink_is_rejected(self):
        path=self.scripts/'runtime_setup.py';path.write_text('changed')
        with self.assertRaisesRegex(ValueError,'source changed'):self.validate()
        path.unlink();path.symlink_to(self.scripts/'toolchain_process.py')
        with self.assertRaisesRegex(ValueError,'source changed'):self.validate()
    def test_profile_helper_drift_and_path_escape_are_rejected(self):
        self.review['prerequisites']['profile_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'profile changed'):self.validate()
        self.review['prerequisites']['profile_sha256']=self.digest(json.loads((self.scripts/'toolchain_profile.json').read_text()))
        self.review['prerequisites']['helper_hashes']['remote_job.py']='0'*64
        with self.assertRaisesRegex(ValueError,'helper manifest'):self.validate()
        self.review['files']['../outside']='0'*64
        with self.assertRaisesRegex(ValueError,'filename'):self.validate()

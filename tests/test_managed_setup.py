import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service
from runtime_recipe import RECIPE
from publication_test_support import publication_reply

class ManagedSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Service(self.temp.name)
        from ownership_test_support import assume_owned
        assume_owned(self,self.s,skip_transport_identity=False)
        verify=patch.object(self.s,'verify_target');verify.start();self.addCleanup(verify.stop)
        self.s.register_compute('brev','demo','/srv/rfd4','http://127.0.0.1',instance_id='fixed',organization_id='org',session_id='demo')
        self.machine=self.s.config('demo')['target_id'];self.op=self.s.begin_setup('demo')['id']
        prerequisite=patch.object(self.s,'review_prerequisites',return_value={'changes':{},'download_bytes':0})
        self.prerequisite=prerequisite.start();self.addCleanup(prerequisite.stop)
        self.review=self.s.prepare_runtime_setup(self.op,self.machine);self.launches=0;self.lost=False
    def remote(self,cfg,command,**kwargs):
        publication=publication_reply(command)
        if publication is not None:return publication
        if ' launch-published ' in command:
            self.launches+=1
            if self.lost:raise TimeoutError('receipt lost')
            return json.dumps({'job_id':self.op,'state':'accepted'})
        if ' status ' in command:return json.dumps({'job_id':self.op,'state':'completed'})
        if command.startswith('cat '):return json.dumps(self.receipt())
        return ''
    def bundle_paths(self):
        return [str(Path(self.review['remote_root'])/'model-bundle'/item['name'])
                for item in self.review['recipe']['model_bundle']['files']]
    def receipt(self):
        from setup_operation import REQUIRED
        return {'operation_id':self.op,'recipe_id':self.review['recipe_id'],'recipe_checksum':self.review['recipe_checksum'],
                'stage':'accepted','ready':True,
                'weight_paths':self.bundle_paths(),
                'evidence':{'recipe_id':self.review['recipe_id'],'checks':{key:True for key in REQUIRED}},
                'post_smoke_evidence':{'recipe_id':self.review['recipe_id'],'checks':{key:True for key in REQUIRED}},
                'smoke':{'operation_id':self.op,'recipe_checksum':self.review['recipe_checksum'],'example':'monomer-short',
                         'output_dir':'/srv/rfd4/setup-smoke/monomer-short-test',
                         'structures':[{'path':'result.cif','atoms':20,'size':500,'sha256':'a'*64}]}}
    def execute(self):
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_copy'),patch.object(self.s,'target_exec',side_effect=self.remote):
            return self.s.execute_runtime_setup(self.op,self.review['review_checksum'])
    def test_repeated_setup_does_not_repeat_remote_launch(self):
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,1)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
    def test_preparation_completion_is_not_runtime_readiness(self):
        self.prerequisite.return_value={'status':'preparation_required','packages':['gcc'],'download_bytes':10}
        self.review=self.s.prepare_runtime_setup(self.op,self.machine)
        self.assertEqual(self.review['phase'],'prepare_archives')
        self.assertFalse(self.review['prerequisite_requires_sudo'])
        original=self.remote
        def prepared(cfg,command,**kwargs):
            if command.startswith('cat '):
                return json.dumps({'operation_id':self.op,'stage':'archives_prepared','ready':False,
                    'review_checksum':self.review['review_checksum'],'prepared_packages':['gcc']})
            return original(cfg,command,**kwargs)
        before=self.s.managed.machine(self.machine)['config']
        with patch.object(self.s,'target_copy'),patch.object(self.s,'target_exec',side_effect=prepared):
            self.assertEqual(self.s.execute_runtime_setup(self.op,self.review['review_checksum'])['state'],'succeeded')
            self.assertEqual(self.s.execute_runtime_setup(self.op,self.review['review_checksum'])['state'],'succeeded')
        self.assertEqual(self.launches,1)
        self.assertEqual(self.s.managed.machine(self.machine)['config'],before)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
    def test_preparation_cannot_accept_model_smoke_as_completion(self):
        self.prerequisite.return_value={'status':'preparation_required','packages':['gcc'],'download_bytes':10}
        self.review=self.s.prepare_runtime_setup(self.op,self.machine)
        with self.assertRaisesRegex(ValueError,'archive evidence'):self.execute()
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
    def test_failed_setup_then_preparation_cannot_clear_runtime_gate(self):
        original=self.remote
        def failed(cfg,command,**kwargs):
            if ' status ' in command:return json.dumps({'job_id':self.op,'state':'failed'})
            return original(cfg,command,**kwargs)
        with patch.object(self.s,'target_copy'),patch.object(self.s,'target_exec',side_effect=failed):
            self.assertEqual(self.s.execute_runtime_setup(self.op,self.review['review_checksum'])['state'],'failed')
        failed_operation=self.op
        self.assertTrue(self.s.runtime_setup_incomplete(self.machine))
        self.op=self.s.begin_setup('demo')['id']
        self.prerequisite.return_value={'status':'preparation_required','packages':['gcc'],'download_bytes':10}
        self.review=self.s.prepare_runtime_setup(self.op,self.machine)
        def prepared(cfg,command,**kwargs):
            if command.startswith('cat '):
                return json.dumps({'operation_id':self.op,'stage':'archives_prepared','ready':False,
                    'review_checksum':self.review['review_checksum'],'prepared_packages':['gcc']})
            return original(cfg,command,**kwargs)
        with patch.object(self.s,'target_copy'),patch.object(self.s,'target_exec',side_effect=prepared):
            self.assertEqual(self.s.execute_runtime_setup(self.op,self.review['review_checksum'])['state'],'succeeded')
        self.assertEqual(self.s.managed.machine(self.machine)['runtime_setup_operation'],failed_operation)
        self.assertTrue(self.s.runtime_setup_incomplete(self.machine))
        self.assertEqual(self.s.compute_status('demo')['state'],'needs_setup')
    def test_lost_acknowledgment_reconciles_original_setup(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        self.lost=False
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,1)
    def test_active_job_blocks_runtime_mutation(self):
        self.s.managed.reserve(self.machine,'other-job','run')
        with self.assertRaises(ValueError):self.execute()
        self.assertEqual(self.launches,0)
    def test_tampered_review_cannot_install(self):
        with self.assertRaises(ValueError):self.s.execute_runtime_setup(self.op,'bad')
        self.assertEqual(self.launches,0)
    def test_changed_prerequisites_prevent_runtime_mutation(self):
        self.prerequisite.return_value={'changes':{'gcc':{'version':'11'}},'download_bytes':10}
        with self.assertRaisesRegex(ValueError,'prerequisites changed'):self.execute()
        self.assertEqual(self.launches,0)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_unqualified_prerequisite_install_cannot_start(self):
        self.prerequisite.return_value={'changes':{'gcc':{'version':'11'}},'download_bytes':10}
        profile=Path(sys.modules['setup_operation'].__file__).with_name('toolchain_profile.json')
        original=Path.read_bytes
        def unqualified(path):
            content=original(path)
            if path==profile:
                value=json.loads(content);value['status']='candidate_not_qualified'
                return json.dumps(value,sort_keys=True).encode()
            return content
        with patch.object(Path,'read_bytes',unqualified):
            self.review=self.s.prepare_runtime_setup(self.op,self.machine)
        with self.assertRaisesRegex(ValueError,'not completed qualification'):self.execute()
        self.assertEqual(self.launches,0)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_qualified_prerequisite_install_dispatches_once(self):
        self.prerequisite.return_value={'changes':{'gcc':{'version':'11'}},'download_bytes':10}
        self.review=self.s.prepare_runtime_setup(self.op,self.machine)
        self.assertTrue(self.review['prerequisite_requires_sudo'])
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,1)

    def test_qualified_prerequisite_lost_ack_retains_reservation(self):
        self.prerequisite.return_value={'changes':{'gcc':{'version':'11'}},'download_bytes':10}
        self.review=self.s.prepare_runtime_setup(self.op,self.machine)
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
        self.lost=False
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,1)

    def test_original_source_change_after_review_keeps_frozen_package(self):
        profile=Path(sys.modules['setup_operation'].__file__).with_name('toolchain_profile.json')
        original=Path.read_bytes
        def changed(path):
            data=original(path)
            return data+b'\n' if path==profile else data
        with patch.object(Path,'read_bytes',changed):
            self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,1)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_frozen_profile_change_after_review_prevents_dispatch(self):
        profile=self.s.state/self.op/'setup-payloads'/self.review['review_checksum']/'toolchain_profile.json'
        profile.write_bytes(profile.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Frozen setup package changed'):self.execute()
        self.assertEqual(self.launches,0)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_old_setup_journal_cannot_satisfy_current_operation(self):
        original=self.remote
        def stale(cfg,command,**kwargs):
            if command.startswith('cat '):
                return json.dumps({'operation_id':'another-operation','recipe_id':self.review['recipe_id'],'stage':'accepted','ready':True,'weight_paths':self.bundle_paths(),'smoke':{'structures':[{'path':'result.cif'}]}})
            return original(cfg,command,**kwargs)
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_copy'),patch.object(self.s,'target_exec',side_effect=stale):
            with self.assertRaisesRegex(ValueError,'matching smoke'):
                self.s.execute_runtime_setup(self.op,self.review['review_checksum'])
        self.assertEqual(self.launches,1)
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
        # Reconciliation with matching evidence completes without a second launch.
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,1)

    def test_completed_setup_updates_paths_without_reconnecting(self):
        before=self.s.managed.selection('demo')
        revision=self.s.managed.machine(self.machine)['revision']
        self.execute()
        machine=self.s.managed.machine(self.machine)
        self.assertEqual(machine['revision'],revision+1)
        self.assertEqual(machine['config']['runtime_recipe'],RECIPE['id'])
        self.assertEqual(len(machine['config']['weight_paths']),2)
        self.assertEqual(self.s.managed.selection('demo'),before)

    def test_failed_runtime_mutation_invalidates_old_ready_cache(self):
        from datetime import datetime,timezone
        cfg=self.s.config('demo');fingerprint=self.s.target_fingerprint(cfg)
        (self.s.root/('compute-check-'+fingerprint+'.json')).write_text(json.dumps({'state':'ready','fingerprint':fingerprint,'checked_at':datetime.now(timezone.utc).isoformat(),'executor_ownership':self.s.local_ownership_proof(cfg)}))
        self.assertEqual(self.s.compute_status('demo')['state'],'ready')
        original=self.remote
        def failed(cfg,command,**kwargs):
            if ' status ' in command:return json.dumps({'job_id':self.op,'state':'failed','exit_code':1})
            return original(cfg,command,**kwargs)
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_copy'),patch.object(self.s,'target_exec',side_effect=failed):
            self.assertEqual(self.s.execute_runtime_setup(self.op,self.review['review_checksum'])['state'],'failed')
        self.assertEqual(self.s.compute_status('demo')['state'],'needs_setup')
        with patch.object(self.s,'target_exec',side_effect=AssertionError('Incomplete setup cannot revalidate old runtime')):
            self.assertEqual(self.s.check_compute('demo')['state'],'needs_setup')

    def test_package_upgrade_reconciles_with_reviewed_recipe(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch('setup_operation.RECIPE',{'id':'new-recipe','model_bundle':{'files':[]}}):
            self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(len(self.s.managed.machine(self.machine)['config']['weight_paths']),2)

    def test_public_bundle_paths_are_accepted_only_for_the_reviewed_bundle(self):
        from setup_operation import validate
        expected=self.bundle_paths()
        self.assertEqual(validate(self.review,self.receipt()),expected)
        self.assertEqual(expected,['/srv/rfd4/model-bundle/config.json',
                                   '/srv/rfd4/model-bundle/model.safetensors'])
        invalid=[expected[:1],list(reversed(expected)),
                 ['/srv/rfd4/model/data_path/weights/model.ckpt'],
                 ['/srv/rfd4/model-bundle/config.json','/srv/other/model.safetensors']]
        for paths in invalid:
            with self.subTest(paths=paths):
                receipt=self.receipt();receipt['weight_paths']=paths
                with self.assertRaisesRegex(ValueError,'checkpoint paths'):
                    validate(self.review,receipt)

    def test_incomplete_smoke_evidence_cannot_commit_readiness(self):
        from setup_operation import validate
        changes=[lambda x:x.pop('recipe_checksum'),
                 lambda x:x.pop('post_smoke_evidence'),
                 lambda x:x['post_smoke_evidence']['checks'].update(source=False),
                 lambda x:x['evidence']['checks'].update(weights=False),
                 lambda x:x['smoke']['structures'][0].update(sha256='invalid'),
                 lambda x:x['smoke']['structures'][0].update(path='../elsewhere.cif'),
                 lambda x:x['smoke'].update(operation_id='old-operation')]
        for change in changes:
            receipt=self.receipt();change(receipt)
            with self.assertRaises(ValueError):validate(self.review,receipt)

    def test_cancel_delivery_failure_retains_unknown_operation(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch.object(self.s,'target_exec',side_effect=TimeoutError('unreachable')):
            result=self.s.cancel_compute_operation(self.op)
        self.assertEqual(result['state'],'needs_attention')
        self.assertIn('unconfirmed',result['detail'])
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_remote_cancelled_receipt_releases_reservation(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch.object(self.s,'target_exec',return_value=''):
            self.s.cancel_compute_operation(self.op)
        def remote(cfg,command,**kwargs):
            return json.dumps({'job_id':self.op,'state':'failed'} if ' status ' in command else {'operation_id':self.op,'stage':'cancelled'})
        with patch.object(self.s,'target_exec',side_effect=remote):
            result=self.s.reconcile_runtime_setup(self.op)
        self.assertEqual(result['state'],'cancelled')
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
        self.assertEqual(self.s.compute_status('demo')['state'],'needs_setup')

    def test_terminal_failure_before_journal_does_not_claim_cancellation(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch.object(self.s,'target_exec',return_value=''):
            self.s.cancel_compute_operation(self.op)
        def remote(cfg,command,**kwargs):
            if ' status ' in command:return json.dumps({'job_id':self.op,'state':'failed','exit_code':1})
            raise FileNotFoundError('Setup journal was never written')
        with patch.object(self.s,'target_exec',side_effect=remote):
            result=self.s.reconcile_runtime_setup(self.op)
        self.assertEqual(result['state'],'failed')
        self.assertTrue(result['cancel_requested'])
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
        self.assertEqual(self.s.compute_status('demo')['state'],'needs_setup')

    def test_unknown_setup_offers_recovery_without_relaunch(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch.object(self.s,'target_exec',return_value=json.dumps({'job_id':self.op,'state':'unknown'})):
            result=self.s.reconcile_runtime_setup(self.op)
        self.assertEqual(result['recovery_action'],'recover_runtime_setup')
        self.assertEqual(result['state'],'needs_attention')
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_exec',return_value=json.dumps({'job_id':self.op,'state':'failed','reason':'orphaned_dispatch_fenced','execution_outcome':'unknown'})):
            result=self.s.recover_runtime_setup(self.op)
        self.assertEqual(result['state'],'failed')
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
        self.assertEqual(self.s.compute_status('demo')['state'],'needs_setup')
        self.assertEqual(self.launches,1)

    def test_cancel_during_completed_smoke_preserves_success(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch.object(self.s,'target_exec',return_value=''):
            self.s.cancel_compute_operation(self.op)
        result=self.execute()
        self.assertEqual(result['state'],'succeeded')
        self.assertTrue(result['cancel_requested'])
        self.assertEqual(self.launches,1)

    def test_recovery_lost_receipt_retains_lease_until_same_fence_is_observed(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        fence={'job_id':self.op,'state':'failed','reason':'orphaned_dispatch_fenced','execution_outcome':'unknown'}
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_exec',side_effect=TimeoutError('fence written but receipt lost')):
            with self.assertRaises(TimeoutError):self.s.recover_runtime_setup(self.op)
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_exec',return_value=json.dumps(fence)):
            self.assertEqual(self.s.recover_runtime_setup(self.op)['state'],'failed')
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
        self.assertEqual(self.launches,1)
        # Recovery resolves the old attempt; a new, separately reviewed setup
        # must be possible without erasing history or replaying the old launch.
        previous_operation=self.op
        previous_record=self.s.managed.operation(previous_operation)
        self.assertTrue(self.s.runtime_setup_incomplete(self.machine))
        self.op=self.s.begin_setup('demo',target_id=self.machine)['id']
        self.assertNotEqual(self.op,previous_operation)
        self.review=self.s.prepare_runtime_setup(self.op,self.machine)
        self.lost=False
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,2)
        self.assertFalse(self.s.runtime_setup_incomplete(self.machine))
        self.assertEqual(self.s.managed.operation(previous_operation),previous_record)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.launches,2)

    def test_cancel_arriving_during_recovery_preserves_unknown_external_outcome(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        def recover(cfg,command,**kwargs):
            self.s.managed.cancel(self.op)
            return json.dumps({'job_id':self.op,'state':'failed','reason':'orphaned_dispatch_fenced','execution_outcome':'unknown'})
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_exec',side_effect=recover):
            result=self.s.recover_runtime_setup(self.op)
        self.assertEqual(result['state'],'failed')
        self.assertTrue(result['cancel_requested'])
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_reconciliation_refuses_changed_host_before_reading_receipt(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch.object(self.s,'verify_target',side_effect=ValueError('Physical machine identity changed')),patch.object(self.s,'target_exec') as remote:
            with self.assertRaisesRegex(ValueError,'identity changed'):self.s.reconcile_runtime_setup(self.op)
            remote.assert_not_called()
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_cancel_refuses_marker_write_on_changed_host(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with patch.object(self.s,'verify_target',side_effect=ValueError('Physical machine identity changed')),patch.object(self.s,'target_exec') as remote:
            result=self.s.cancel_compute_operation(self.op)
            remote.assert_not_called()
        self.assertIn('unconfirmed',result['detail'])
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_late_identity_discovery_blocks_alias_job_without_reservation(self):
        other=self.s.managed.register({'linux_machine_id_sha256':'same-host'},{'kind':'ssh'})['id']
        directory=self.s.state/'legacy-active';directory.mkdir()
        (directory/'job.json').write_text(json.dumps({'job_id':'legacy-active','machine_id':other,'status':'running'}))
        def bind(cfg):self.s.managed.bind_physical_identity(self.machine,{'linux_machine_id_sha256':'same-host'})
        with patch.object(self.s,'verify_target',side_effect=bind),patch.object(self.s,'target_copy') as copy,patch.object(self.s,'target_exec') as remote:
            with self.assertRaisesRegex(ValueError,'verified host'):
                self.s.execute_runtime_setup(self.op,self.review['review_checksum'])
            remote.assert_not_called();copy.assert_not_called()
        self.assertFalse(self.s.managed.operation(self.op)['dispatched'])

    def test_remote_launch_carries_exact_authorized_review(self):
        import shlex
        copied={}
        def capture(cfg,source,destination,**kwargs):
            self.assertEqual(Path(source).name,self.review['review_checksum'])
            self.assertRegex(destination,'^/srv/rfd4/setup-operations/'+self.op+'/uploads/[0-9a-f]{32}$')
            self.assertEqual({p.name for p in Path(source).iterdir()},
                             set(self.review['files'])|{'setup-review.json','run.sh'})
            for name in ('setup-review.json','run.sh'):
                copied[name]=(Path(source)/name).read_text()
        with patch.object(self.s,'verify_target'),patch.object(self.s,'target_copy',side_effect=capture) as transfer,patch.object(self.s,'target_exec',side_effect=self.remote):
            self.s.execute_runtime_setup(self.op,self.review['review_checksum'])
        self.assertEqual(transfer.call_count,1)
        self.assertEqual(json.loads(copied['setup-review.json']),self.s.managed.operation(self.op)['review'])
        args=shlex.split(copied['run.sh'].split('exec ',1)[1])
        self.assertEqual(args[-1],self.review['review_checksum'])
        self.assertEqual(args[-2],'/srv/rfd4/setup-operations/'+self.op+'/payload/setup-review.json')
        self.assertEqual(args[-3],self.op)

    def test_prerequisite_reconciliation_uses_payload_code_and_original_mutable_root(self):
        import shlex
        operation=self.s.managed.operation(self.op)
        for legacy in (False,True):
            with self.subTest(legacy=legacy):
                candidate=json.loads(json.dumps(operation))
                if legacy:candidate['review'].pop('execution_script_template')
                with patch.object(self.s,'target_exec',return_value=json.dumps({'job_id':self.op,'state':'pending'})) as remote:
                    self.s.reconcile_setup_prerequisites(candidate,'observe')
                args=shlex.split(remote.call_args.args[1])
                base='/srv/rfd4/setup-operations/'+self.op+('' if legacy else '/payload')
                self.assertEqual(args[2],base+'/prerequisite_privileged.py')
                self.assertEqual(args[4:6],['/srv/rfd4',self.op])
                self.assertEqual(args[6],base+'/setup-review.json')

    def test_failed_directory_transfer_never_dispatches(self):
        with patch.object(self.s,'target_copy',side_effect=TimeoutError('copy outcome unknown')) as transfer,patch.object(self.s,'target_exec',side_effect=self.remote):
            with self.assertRaises(TimeoutError):
                self.s.execute_runtime_setup(self.op,self.review['review_checksum'])
            self.assertEqual(self.s.execute_runtime_setup(self.op,self.review['review_checksum'])['state'],'failed')
            self.assertEqual(transfer.call_count,1)
        operation=self.s.managed.operation(self.op)
        self.assertEqual(operation['state'],'failed')
        self.assertFalse(operation['dispatched'])
        self.assertEqual(self.launches,0)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_cancellation_during_directory_transfer_prevents_launch(self):
        def copied(*args,**kwargs):
            self.s.managed.cancel(self.op)
        with patch.object(self.s,'target_copy',side_effect=copied),patch.object(self.s,'target_exec',side_effect=self.remote):
            with self.assertRaises(ValueError):
                self.s.execute_runtime_setup(self.op,self.review['review_checksum'])
        self.assertEqual(self.s.managed.operation(self.op)['state'],'cancelled')
        self.assertFalse(self.s.managed.operation(self.op)['dispatched'])
        self.assertEqual(self.launches,0)
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_privileged_recovery_precedes_supervisor_recovery(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        self.lost=False
        with self.s.managed.transaction() as data:
            data['operations'][self.op]['review']['prerequisites']['changes']={'gcc':{'version':'11'}}
        with patch.object(self.s,'verify_target'),patch.object(self.s,'reconcile_setup_prerequisites',return_value={'job_id':self.op,'state':'pending'}) as packages,patch.object(self.s,'target_exec',return_value=json.dumps({'job_id':self.op,'state':'unknown','package_stage':{'job_id':self.op}})) as remote:
            result=self.s.recover_runtime_setup(self.op)
            self.assertEqual(result['prerequisite_status']['state'],'pending')
            self.assertEqual(remote.call_count,1);self.assertIn(' status ',remote.call_args.args[1]);packages.assert_called_once()
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
        with patch.object(self.s,'verify_target'),patch.object(self.s,'reconcile_setup_prerequisites',return_value={'job_id':self.op,'state':'failed'}),patch.object(self.s,'target_exec',side_effect=[json.dumps({'job_id':self.op,'state':'unknown','package_stage':{'job_id':self.op}}),json.dumps({'job_id':self.op,'state':'failed','reason':'orphaned_dispatch_fenced'})]) as remote:
            self.assertEqual(self.s.recover_runtime_setup(self.op)['state'],'failed')
            self.assertIn(' recover ',remote.call_args.args[1])
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_recovery_before_package_publication_uses_supervisor_fence(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.execute()
        with self.s.managed.transaction() as data:
            data['operations'][self.op]['review']['prerequisites']['changes']={'gcc':{'version':'11'}}
        responses=[json.dumps({'job_id':self.op,'state':'unknown'}),json.dumps({'job_id':self.op,'state':'failed','reason':'orphaned_dispatch_fenced'})]
        with patch.object(self.s,'verify_target'),patch.object(self.s,'reconcile_setup_prerequisites') as packages,patch.object(self.s,'target_exec',side_effect=responses):
            self.assertEqual(self.s.recover_runtime_setup(self.op)['state'],'failed')
        packages.assert_not_called()
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])

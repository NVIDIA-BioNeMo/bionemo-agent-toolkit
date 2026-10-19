"""Standalone registry, isolated selection, durable drafts and safe recovery."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service
import registry

TARGET = {'target_id':'gpu.example','title':'Shared GPU','provider':'ngs-compute',
          'controller_transport':'ssh','executor':'local_process','workspace_access':'remote_filesystem',
          'description':'Existing machine','config_hash':'sha256:'+'a'*64,'host_access':{'alias':'gpu'},
          'workspace_root':'/srv','executor_configuration':{}}

class RegistryContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Service(self.tmp.name)
        identity=patch('registry.effective_access',side_effect=lambda alias,run: {'alias':alias,'host':alias})
        identity.start();self.addCleanup(identity.stop)
    def register(self, session=None, name='gpu'):
        return self.s.register_compute('ssh',name,'/srv/rfd4','http://127.0.0.1:18765',ssh_host=name,weight_paths=['/weights/model.ckpt'],session_id=session)
    def test_owns_registry_and_selection_without_external_plugin(self):
        self.register()
        self.assertTrue(self.s.available_compute()['available'])
        self.assertEqual(self.s.available_compute()['targets'][0]['target_id'],'gpu')
        with patch.object(self.s,'target_exec',side_effect=AssertionError('no remote execution')):
            self.s.register_registry_compute('gpu',session_id='one')
        self.assertEqual(self.s.compute_status('one')['source'],'BioNeMo')
        self.assertEqual(self.s.config('one')['ssh_host'],'gpu')
    def test_changed_catalog_record_requires_reselection(self):
        self.register();cfg=self.s.config('one')
        self.s.register_compute('ssh','gpu','/other','http://127.0.0.1',ssh_host='gpu')
        with self.assertRaisesRegex(ValueError,'configuration changed'): registry.Catalog(self.s.root).verify(cfg)
    def test_changed_ssh_alias_rejected_for_old_job(self):
        with patch('registry.effective_access',return_value={'alias':'gpu','host':'different'}):
            with self.assertRaisesRegex(ValueError,'SSH identity changed'):
                self.s.verify_target({'kind':'ssh','registry_target':{'host_access':{'alias':'gpu','host':'original'}}})
    def test_empty_catalog_needs_no_external_environment(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.s.available_compute(),{'available':True,'targets':[]})
    def test_migrates_only_owned_config_and_preserves_immutable_job(self):
        cfg={'kind':'ssh','instance':'gpu','remote_root':'/srv/rfd4','studio_url':'http://127.0.0.1',
             'ssh_host':'gpu','registry_target':dict(TARGET,host_access={'alias':'gpu','host':'gpu'})}
        path=self.s.root/'config.json';path.write_text(json.dumps(cfg))
        jobdir=self.s.state/'old';jobdir.mkdir();job=jobdir/'job.json';job.write_text(json.dumps({'target':cfg}))
        before=job.read_bytes()
        migrated=self.s.config()
        self.assertNotIn('registry_target',migrated)
        self.assertEqual(migrated['ssh_access'],cfg['registry_target']['host_access'])
        self.assertEqual(job.read_bytes(),before)
        self.assertTrue(path.with_suffix('.json.before-standalone').exists())
        self.assertEqual(self.s.config(),migrated)
        self.assertEqual(self.s.compute_status()['state'],'registered')
    def test_legacy_scheduler_target_cannot_migrate(self):
        cfg={'instance':'gpu','registry_target':dict(TARGET,executor='slurm')}
        (self.s.root/'config.json').write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError,'scheduler'): self.s.config()
    def test_migration_preserves_distinct_session_targets_with_same_name(self):
        for name,host in [('a','host-a'),('b','host-b')]:
            cfg={'kind':'ssh','instance':'gpu','remote_root':'/srv','studio_url':'http://127.0.0.1','ssh_host':host}
            self.s.compute_config_path(name).write_text(json.dumps(cfg))
        self.s.available_compute()
        self.assertNotEqual(self.s.config('a')['target_id'],self.s.config('b')['target_id'])
    def test_missing_editor_has_actionable_error(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'CPU editor is not configured'): self.s.studio_url()
    def test_inspection_is_connection_only(self):
        self.register()
        with patch.object(self.s,'target_exec',return_value='') as execute:
            self.assertTrue(self.s.inspect_compute_target('gpu')['connected'])
            self.assertEqual(execute.call_args.args[1],'true')
        with patch.object(self.s,'target_exec',side_effect=RuntimeError('offline')):
            self.assertFalse(self.s.inspect_compute_target('gpu')['connected'])
    def test_session_selection_isolated_from_global_default(self):
        self.register()
        first=self.s.config('one')
        self.register(name='different')
        self.assertEqual(self.s.config('one'),first)
        self.assertEqual(self.s.config('two')['instance'],'different')
    def test_failed_connection_not_model_setup(self):
        self.register()
        with patch.object(self.s,'target_exec',side_effect=RuntimeError('Connection refused')):
            self.assertEqual(self.s.check_compute()['state'],'disconnected')
        with patch.object(self.s,'target_exec',side_effect=['','A100',RuntimeError('Runtime missing')]):
            self.assertEqual(self.s.check_compute()['state'],'needs_setup')
    def test_gpu_readiness_independent_of_editor(self):
        self.register()
        with patch.object(self.s,'target_exec',return_value='A100'),patch.object(self.s,'studio',side_effect=AssertionError('editor must be separate')):
            self.assertEqual(self.s.check_compute()['state'],'ready')
    def test_old_check_cannot_show_ready_forever(self):
        self.register()
        with patch.object(self.s,'target_exec',return_value='A100'): self.s.check_compute()
        p=next(self.s.root.glob('compute-check-*.json'))
        value=json.loads(p.read_text());value['checked_at']='2000-01-01T00:00:00+00:00';p.write_text(json.dumps(value))
        self.assertEqual(self.s.compute_status()['state'],'registered')
    def test_cpu_editor_and_incomplete_draft_work_without_compute(self):
        with patch.dict(os.environ,{'RFD4_EDITOR_URL':'http://127.0.0.1:18765'}):
            self.assertEqual(self.s.studio_url(),'http://127.0.0.1:18765')
        export={'cif':'data_draft\n_atom_site.id 1','revision':3,'issues':[{'severity':'error'}]}
        with patch.object(self.s,'studio',return_value=export):
            draft=self.s.save_draft('draft','Keep these hotspots',settings={'seed':42})
        # Recreate backend as after process restart.
        other=Service(self.tmp.name)
        self.assertEqual(other.list_drafts()['drafts'][0]['revision'],3)
        with patch.object(other,'import_cif',return_value={'session_id':'restored'}) as imp:
            result=other.restore_draft(draft['draft_id'])
        imp.assert_called_once_with(export['cif'])
        self.assertEqual(result['note'],'Keep these hotspots')
        self.assertEqual(result['settings']['seed'],42)
    def test_poll_original_job_after_target_switch(self):
        self.register();cfg=self.s.config()
        directory=self.s.state/'job';directory.mkdir()
        self.s.save_job({'job_id':'job','instance':'gpu','target':cfg,'status':'submitted','remote_dir':'/srv/runs/job'})
        self.register(name='different')
        with patch.object(self.s,'target_exec',return_value='RUNNING') as execute:
            self.assertEqual(self.s.status('job')['status'],'running')
        self.assertEqual(execute.call_args.args[0],cfg)
    def test_setup_requests_are_idempotent_and_cannot_claim_readiness(self):
        first=self.s.begin_setup('one')
        self.assertEqual(first,self.s.begin_setup('one'))
        self.s.update_setup(first['request_id'],'downloading','Downloading weights','one')
        self.assertEqual(self.s.compute_status('one')['state'],'setting_up')
        with self.assertRaisesRegex(ValueError,'request changed'):
            self.s.update_setup('different','complete','Done','one')
        self.s.update_setup(first['request_id'],'complete','Done','one')
        self.assertEqual(self.s.compute_status('one')['state'],'unregistered')
    def test_submission_rechecks_readiness_and_retries_existing_job(self):
        self.register()
        exported={'cif':'data_draft\n_atom_site.id 1','revision':3,'issues':[]}
        with patch.object(self.s,'studio',return_value=exported): plan=self.s.prepare('one')
        with patch.object(self.s,'check_compute',return_value={'state':'disconnected','detail':'offline'}),patch('core.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'not ready'): self.s.execute(plan['snapshot_id'],plan['plan_checksum'])
            spawn.assert_not_called()
        with patch.object(self.s,'check_compute',return_value={'state':'ready'}),patch('core.subprocess.Popen') as spawn:
            job=self.s.execute(plan['snapshot_id'],plan['plan_checksum'])
        self.register('one',name='different')
        with patch.object(self.s,'check_compute',side_effect=AssertionError('Do not recheck or resubmit an existing job')):
            self.assertEqual(self.s.execute(plan['snapshot_id'],plan['plan_checksum']),job)

class SSHIdentityContract(unittest.TestCase):
    def test_resolution_is_local_and_tracks_transport_changes(self):
        from unittest.mock import Mock
        output='hostname gpu.example\nuser ubuntu\nport 22\nstricthostkeychecking true\nidentityfile /keys/one\n'
        run=Mock(return_value=output)
        first=registry.effective_access('gpu',run)
        self.assertEqual(run.call_args.args[0],['ssh','-G','-o','BatchMode=yes','--','gpu'])
        run.return_value=output.replace('/keys/one','/keys/two')
        with self.assertRaisesRegex(ValueError,'SSH identity changed'): registry.verify_access(first,run)

"""Offline checks for immutable plans and duplicate submission prevention."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service

class Plans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = Service(self.tmp.name)
        self.cfg = {'instance':'demo', 'instance_id':'id-demo', 'remote_root':'/home/ubuntu/rfd4', 'studio_url':'http://127.0.0.1:18764'}
        (Path(self.tmp.name)/'config.json').write_text(json.dumps(self.cfg))
        self.export = {'cif':'data_demo\n_atom_site.id 1\n', 'revision':1, 'issues':[]}
    def plan(self):
        with patch.object(self.service, 'studio', return_value=self.export):
            return self.service.prepare('session')
    def test_plan_launch_and_retry_dispatch_once(self):
        plan = self.plan()
        with patch('core.subprocess.Popen') as spawn:
            first = self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
            second = self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
        self.assertEqual(first,second)
        self.assertEqual(spawn.call_count,1)
    def test_tampered_plan_rejected(self):
        plan=self.plan()
        path=self.service.state/plan['snapshot_id']/'plan.json'
        raw=json.loads(path.read_text()); raw['samples']=16; path.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'Plan changed'):
            self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
    def test_input_changes_rejected(self):
        plan=self.plan()
        (self.service.state/plan['snapshot_id']/'input.cif').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Snapshot was modified'):
            self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
    def test_input_and_snapshot_metadata_changes_rejected(self):
        import hashlib
        plan=self.plan()
        directory=self.service.state/plan['snapshot_id']
        data=b'changed'
        (directory/'input.cif').write_bytes(data)
        snapshot=json.loads((directory/'snapshot.json').read_text())
        snapshot['sha256']=hashlib.sha256(data).hexdigest()
        (directory/'snapshot.json').write_text(json.dumps(snapshot))
        with self.assertRaisesRegex(ValueError,'Snapshot was modified'):
            self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
    def test_image_note_preserved_without_model_conditions(self):
        import base64
        image=b'\x89PNG\r\n\x1a\nexample'
        with patch.object(self.service,'studio',return_value=self.export):
            plan=self.service.prepare('session',image_base64=base64.b64encode(image).decode())
        self.assertEqual((self.service.state/plan['snapshot_id']/'annotation.png').read_bytes(),image)
        self.assertNotIn('image_base64',json.dumps(plan))
    def test_target_changes_rejected(self):
        plan=self.plan()
        self.cfg['instance_id']='different'
        (Path(self.tmp.name)/'config.json').write_text(json.dumps(self.cfg))
        with self.assertRaisesRegex(ValueError,'configuration changed'):
            self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
    def test_validation_blocks_errors(self):
        self.export['issues']=[{'check':'other','severity':'error'}]
        with self.assertRaisesRegex(ValueError,'validation failed'):
            self.plan()
    def test_upstream_missing_atoms_warning(self):
        self.export['issues']=[{'check':'missing_atoms','severity':'error'}]
        self.assertEqual(self.plan()['issues'][0]['severity'],'warning')
    def test_collect_rejects_changed_target(self):
        plan=self.plan()
        with patch('core.subprocess.Popen'):
            job=self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
        job['status']='completed'; self.service.save_job(job)
        self.cfg['instance_id']='different'
        (Path(self.tmp.name)/'config.json').write_text(json.dumps(self.cfg))
        with self.assertRaisesRegex(ValueError,'original target'):
            self.service.collect(job['job_id'])

if __name__ == '__main__':
    unittest.main()

class GenerationContract(unittest.TestCase):
    setUp = Plans.setUp
    plan = Plans.plan
    def test_nondefault_settings_survive_review_and_submission(self):
        from generation import overrides
        chosen = {'thinking':'high','backbone_noise':0.25,'latent_noise':0.45}
        with patch.object(self.service,'studio',return_value=self.export):
            plan = self.service.prepare('session',generation=chosen)
        with patch('core.subprocess.Popen'):
            job = self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
        self.assertEqual(job['generation'], chosen)
        with patch.object(self.service,'verify_target'), patch.object(self.service,'target_exec'), patch.object(self.service,'target_copy'):
            self.service._submit(job['target'],job,self.service.state/job['job_id']/'input.cif')
        command = (self.service.state/job['job_id']/'run.sh').read_text()
        for arg in overrides(chosen): self.assertIn(arg,command)

    def test_invalid_options_never_create_plan(self):
        for value in ({'thinking':'extreme'}, {'backbone_noise':float('nan')}, {'latent_noise':0}, {'latent_noise':True}, {'command':'evil'}):
            with self.subTest(value=value), patch.object(self.service,'snapshot') as snapshot:
                with self.assertRaises(ValueError): self.service.prepare('session',generation=value)
                snapshot.assert_not_called()

    def test_sampling_tamper_rejected(self):
        plan = self.plan()
        path = self.service.state/plan['snapshot_id']/'plan.json'
        raw = json.loads(path.read_text()); raw['generation']['thinking']='high'; path.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'Plan changed'):
            self.service.execute(plan['snapshot_id'],plan['plan_checksum'])

    def test_results_archive_and_input_switch_use_saved_artifacts(self):
        import base64, io, zipfile
        plan = self.plan()
        with patch('core.subprocess.Popen'):
            job = self.service.execute(plan['snapshot_id'],plan['plan_checksum'])
        job['status']='completed'; self.service.save_job(job)
        directory = self.service.state/job['job_id']/'results'; directory.mkdir()
        (directory/'design1.cif').write_text('data_first')
        (directory/'design2.cif').write_text('data_second')
        self.assertEqual(len(self.service.results(job['job_id'])['designs']),2)
        with patch.object(self.service,'import_cif',return_value={'session_id':'loaded'}) as imp, patch.object(self.service,'viewer_payload',side_effect=lambda x:x):
            self.service.open_run_structure(job['job_id'])
            imp.assert_called_with(self.export['cif'])
            self.service.open_run_structure(job['job_id'],1)
            imp.assert_called_with('data_second')
        result=self.service.download_results(job['job_id'])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result['base64']))) as z:
            self.assertEqual(z.read('input.cif').decode(),self.export['cif'])
            self.assertEqual(z.read('design-2/design2.cif'),b'data_second')

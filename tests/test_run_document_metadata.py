"""Run navigation restores only metadata bound to the accepted frozen input."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service

class RunDocumentMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=Service(self.tmp.name,runner=lambda *a,**k:self.fail('external command'))
        self.image=base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
        with patch.object(self.service,'studio',return_value={'cif':'data_fixture\n_atom_site.id 1\n','revision':1,'issues':[]}):
            public=self.service.prepare_design_request('demo',note='The saved run note',samples=2,seed=123,
                image_base64=self.image,generation={'thinking':'low','backbone_noise':0.2,'latent_noise':0.4})
        self.id=public['snapshot_id'];self.folder=self.service.state/self.id
        self.plan=dict(public,target={'kind':'brev','instance':'fixture','instance_id':'fixed','organization_id':'org','remote_root':'/srv/rfd4','studio_url':'http://127.0.0.1'})
        self.plan['plan_checksum']=self.service.checksum(self.plan)
        (self.folder/'plan.json').write_text(json.dumps(self.plan))
        self.job={key:self.plan[key] for key in ('snapshot_id','samples','seed','generation','target')}
        self.job.update(job_id=self.id,status='completed');self.service.save_job(self.job)

    def write_plan(self,**changes):
        plan=dict(self.plan,**changes);plan['plan_checksum']=self.service.checksum(plan)
        (self.folder/'plan.json').write_text(json.dumps(plan));return plan

    def test_saved_run_note_image_and_settings_match_accepted_plan(self):
        value=self.service.saved_run_metadata(self.job)
        self.assertEqual(value['source'],'saved_run')
        self.assertEqual(value['note'],'The saved run note')
        self.assertEqual(value['image_base64'],self.image)
        self.assertEqual(value['settings'],{'samples':2,'seed':123,'generation':self.plan['generation']})

    def test_corrupted_plan_refuses_before_structure_import(self):
        damaged=dict(self.plan,note='tampered');(self.folder/'plan.json').write_text(json.dumps(damaged))
        with patch.object(self.service,'import_cif') as imported:
            with self.assertRaisesRegex(ValueError,'plan or input changed'):
                self.service.open_run_structure(self.id)
        imported.assert_not_called()

    def test_modified_input_refuses_before_structure_import(self):
        (self.folder/'input.cif').write_text('data_changed\n_atom_site.id 2\n')
        with patch.object(self.service,'import_cif') as imported:
            with self.assertRaisesRegex(ValueError,'plan or input changed'):
                self.service.open_run_structure(self.id,0)
        imported.assert_not_called()

    def test_settings_or_target_mismatch_with_accepted_job_refuses(self):
        for key,value in [('seed',321),('samples',1),('target',{'instance':'replacement'}),('generation',{'thinking':'high'})]:
            with self.subTest(field=key):
                with self.assertRaisesRegex(ValueError,'do not match the accepted run'):
                    self.service.saved_run_metadata(dict(self.job,**{key:value}))

    def test_legacy_missing_plan_explicitly_has_no_metadata(self):
        value=self.service.saved_run_metadata({'job_id':'legacy'})
        self.assertEqual(value,{'source':'unavailable','note':'','image_base64':None,'settings':None})

    def test_changed_image_refuses(self):
        (self.folder/'annotation.png').write_bytes(b'\x89PNG\r\n\x1a\nchanged')
        with self.assertRaisesRegex(ValueError,'image note changed'):self.service.saved_run_metadata(self.job)

    def test_old_unbound_image_is_not_presented_as_verified(self):
        plan=dict(self.plan);plan.pop('image_sha256');plan['plan_checksum']=self.service.checksum(plan)
        (self.folder/'plan.json').write_text(json.dumps(plan))
        value=self.service.saved_run_metadata(self.job)
        self.assertIsNone(value['image_base64']);self.assertTrue(value['image_note_unavailable'])

    def test_input_and_result_payloads_both_include_bound_metadata(self):
        with patch.object(self.service,'import_cif',return_value={'session_id':'input'}), \
             patch.object(self.service,'open_result',return_value={'session_id':'result'}), \
             patch.object(self.service,'viewer_payload',side_effect=lambda value:value), \
             patch.object(self.service,'result_files',return_value=[]):
            for index,session in [(None,'input'),(0,'result')]:
                value=self.service.open_run_structure(self.id,index)
                self.assertEqual(value['session_id'],session)
                self.assertEqual(value['document_metadata']['note'],self.plan['note'])
                self.assertFalse((self.service.root/'state.json').exists())

if __name__=='__main__':unittest.main()

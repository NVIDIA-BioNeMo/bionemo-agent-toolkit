"""Verified results and exports survive loss of access to the original host."""
import base64,hashlib,io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service

class OfflineResults(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Service(self.tmp.name)
        with patch.object(self.s,'studio',return_value={'cif':'data_input','revision':1,'issues':[]}):
            self.request=self.s.prepare_design_request('editor',note='original note',samples=2,seed=99)
        self.id=self.request['request_id'];self.folder=self.s.state/self.id
        self.s.save_job(dict(job_id=self.id,snapshot_id=self.id,runtime_protocol=4,status='completed',
            request_checksum=self.request['request_checksum'],remote_dispatch_started=True,remote_dir='/srv/runs/'+self.id,
            target={'ssh_alias':'gpu','runtime_root':'/srv/rfd4','output_root':'/srv/runs'},
            **{k:self.request[k] for k in ('samples','seed','generation')}))
        results=self.folder/'results';results.mkdir()
        for name,value in [('one.cif',b'data_one'),('two.cif',b'data_two')]: (results/name).write_bytes(value)
        self.manifest={'version':1,'files':[{'path':p.name,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(results.iterdir())]}
        (results/'.manifest.json').write_text(json.dumps(self.manifest))
        logs=self.folder/'logs';logs.mkdir();(logs/'receipt.json').write_bytes(b'terminal receipt')
        (self.folder/'collection.json').write_text(json.dumps({'state':'complete','manifest':self.manifest,'log_hashes':{'receipt.json':hashlib.sha256(b'terminal receipt').hexdigest()}}))
        no_remote=patch.object(self.s,'named_exec',side_effect=AssertionError('host is stopped'))
        no_remote.start();self.addCleanup(no_remote.stop)

    def test_verified_results_and_zip_work_offline(self):
        self.assertEqual(len(self.s.results(self.id)['designs']),2)
        archive=self.s.download_results(self.id)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive['base64']))) as z:
            self.assertEqual(z.read('input.cif'),b'data_input')
            self.assertEqual(z.read('design-2/two.cif'),b'data_two')

    def test_input_and_result_restore_immutable_metadata_offline(self):
        with patch.object(self.s,'import_cif',return_value={'session_id':'opened'}) as imported,patch.object(self.s,'viewer_payload',side_effect=lambda v:v):
            first=self.s.open_run_structure(self.id)
            imported.assert_called_with('data_input')
            second=self.s.open_run_structure(self.id,1)
            imported.assert_called_with('data_two')
        self.assertEqual(first['document_metadata'],second['document_metadata'])
        self.assertEqual(first['document_metadata']['note'],'original note')
        self.assertEqual(first['document_metadata']['settings']['seed'],99)

    def test_tampered_cache_is_not_exported_when_original_host_unavailable(self):
        (self.folder/'results/two.cif').write_bytes(b'bad')
        with self.assertRaisesRegex(AssertionError,'stopped'):self.s.download_results(self.id)

    def test_changed_reviewed_input_is_not_exported(self):
        (self.folder/'input.cif').write_bytes(b'data_changed_after_review')
        with self.assertRaisesRegex(ValueError, 'Saved design input changed'):
            self.s.download_results(self.id)

    def test_changed_reviewed_request_is_not_exported(self):
        request = dict(self.request, seed=100)
        (self.folder/'request.json').write_text(json.dumps(request))
        with self.assertRaisesRegex(ValueError, 'Saved design request changed'):
            self.s.download_results(self.id)

    def test_request_must_match_the_accepted_job(self):
        job = self.s.read(self.id, 'job.json')
        job['request_checksum'] = '0' * 64
        self.s.save_job(job)
        with self.assertRaisesRegex(ValueError, 'Run provenance changed'):
            self.s.download_results(self.id)

    def test_another_valid_snapshot_cannot_replace_the_jobs_input(self):
        with patch.object(self.s, 'studio', return_value={'cif':'data_other', 'revision':2, 'issues':[]}):
            other = self.s.prepare_design_request('other-editor')
        job = self.s.read(self.id, 'job.json')
        job['snapshot_id'] = other['request_id']
        self.s.save_job(job)
        with self.assertRaisesRegex(ValueError, 'Run provenance changed'):
            self.s.download_results(self.id)

    def test_zip_keeps_verified_bytes_if_input_changes_during_archive_creation(self):
        enter = zipfile.ZipFile.__enter__
        def change_input(archive):
            (self.folder/'input.cif').write_bytes(b'data_changed_during_export')
            return enter(archive)
        with patch.object(zipfile.ZipFile, '__enter__', new=change_input):
            exported = self.s.download_results(self.id)
        self.assertEqual((self.folder/'input.cif').read_bytes(), b'data_changed_during_export')
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['base64']))) as archive:
            self.assertEqual(archive.read('input.cif'), b'data_input')

    def legacy_reviewed_job(self):
        job = self.s.read(self.id, 'job.json')
        job['runtime_protocol'] = 3
        self.s.save_job(job)
        plan = dict(self.request, target=job['target'])
        plan['plan_checksum'] = self.s.checksum(plan)
        (self.folder/'plan.json').write_text(json.dumps(plan))

    def test_verified_legacy_input_can_still_be_exported_offline(self):
        self.legacy_reviewed_job()
        exported = self.s.download_results(self.id)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['base64']))) as archive:
            self.assertEqual(archive.read('input.cif'), b'data_input')
            self.assertEqual(archive.read('design-2/two.cif'), b'data_two')

    def test_changed_legacy_reviewed_input_is_not_exported(self):
        self.legacy_reviewed_job()
        (self.folder/'input.cif').write_bytes(b'data_changed_after_review')
        with self.assertRaisesRegex(ValueError, 'plan or input changed'):
            self.s.download_results(self.id)

    def test_legacy_input_without_review_provenance_is_not_exported(self):
        self.legacy_reviewed_job()
        (self.folder/'plan.json').unlink()
        with self.assertRaisesRegex(ValueError, 'provenance unavailable'):
            self.s.download_results(self.id)

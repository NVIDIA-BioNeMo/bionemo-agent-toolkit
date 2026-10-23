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

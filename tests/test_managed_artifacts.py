import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service
from artifacts import validate_manifest

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = Service(self.tmp.name)
        self.jobdir = self.service.state / 'job'
        self.jobdir.mkdir()
        self.job = {'job_id': 'job', 'status': 'completed', 'remote_dir': '/srv/runs/job',
                    'target': {'kind': 'local', 'instance': 'test', 'remote_root': '/srv', 'studio_url': 'http://127.0.0.1'}}
        self.service.save_job(self.job)
        self.content = {'one.cif': b'data_one', 'two.cif': b'data_two'}
        self.manifest = {'version': 1, 'files': [{'path': k, 'size': len(v), 'sha256': hashlib.sha256(v).hexdigest()} for k,v in self.content.items()]}
        self.copies = 0
        self.mode = 'good'
        def copy(cfg, source, destination, **kwargs):
            self.copies += 1
            out = destination / 'inference_samples'
            out.mkdir(exist_ok=True)
            for k,v in self.content.items():
                (out/k).write_bytes(v)
            if self.mode == 'corrupt': (out/'two.cif').write_bytes(b'bad')
            if self.mode == 'interrupted': raise ConnectionError('transfer interrupted')
            if self.mode == 'disk_full': raise OSError('No space left on device')
        for method,value in [('verify_target', lambda *a: None), ('target_exec', lambda *a, **kw: json.dumps(self.manifest)), ('target_copy', copy)]:
            mocked = patch.object(self.service, method, side_effect=value)
            mocked.start(); self.addCleanup(mocked.stop)
        no_launch = patch.object(self.service, 'launch', side_effect=AssertionError('Must never rerun inference'))
        no_launch.start(); self.addCleanup(no_launch.stop)

    def test_complete_manifest_reused_without_download(self):
        first = self.service.collect('job')
        self.assertEqual(len(first['files']), 2)
        self.assertEqual(self.service.collect('job'), first)
        self.assertEqual(self.copies, 1)

    def test_brev_directory_copy_retries_without_rerunning_inference(self):
        self.job['target'].update(kind='brev',instance_id='dedicated')
        self.service.save_job(self.job)
        self.mode='interrupted'
        with self.assertRaises(ConnectionError):self.service.collect('job')
        self.assertEqual(self.service.read('job','job.json')['status'],'completed')
        self.assertFalse((self.jobdir/'results').exists())
        self.mode='good'
        result=self.service.collect('job')
        self.assertEqual(result['collection'],'complete')
        self.assertEqual(self.copies,2)
        self.assertEqual(self.service.collect('job'),result)
        self.assertEqual(self.copies,2)
        self.assertEqual((self.jobdir/'results/two.cif').read_bytes(),self.content['two.cif'])

    def test_failed_transfers_retry_without_changing_run(self):
        for failure in ('corrupt', 'interrupted', 'disk_full'):
            with self.subTest(failure=failure):
                self.mode = failure
                with self.assertRaises((ValueError, ConnectionError, OSError)):
                    self.service.collect('job')
                self.assertEqual(self.service.read('job', 'job.json')['status'], 'completed')
                self.assertFalse((self.jobdir/'results/.manifest.json').exists())
        self.mode = 'good'
        self.assertEqual(self.service.collect('job')['collection'], 'complete')

    def test_legacy_partial_directory_is_not_complete(self):
        (self.jobdir/'results').mkdir()
        (self.jobdir/'results/one.cif').write_bytes(self.content['one.cif'])
        self.assertEqual(len(self.service.result_files('job')), 2)
        self.assertEqual(self.copies, 1)

    def test_cached_corruption_is_repaired(self):
        self.service.collect('job')
        (self.jobdir/'results/one.cif').write_bytes(b'corrupt')
        self.service.collect('job')
        self.assertEqual(self.copies, 2)
        self.assertEqual((self.jobdir/'results/one.cif').read_bytes(), self.content['one.cif'])

    def test_manifest_rejects_traversal_duplicate_and_empty(self):
        for name in ('../secret.cif', '/etc/secret.cif', 'a/../b.cif'):
            with self.assertRaises(ValueError):
                validate_manifest({'version':1,'files':[dict(self.manifest['files'][0],path=name)]})
        with self.assertRaises(ValueError): validate_manifest({'version':1,'files':[]})
        with self.assertRaises(ValueError): validate_manifest({'version':1,'files':[self.manifest['files'][0]]*2})

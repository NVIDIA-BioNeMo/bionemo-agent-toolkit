"""Protocol-4 result caches can be repaired without rerunning inference."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service


class ChatCollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.service = Service(self.root / 'client')
        self.directory = self.service.state / 'job'
        self.directory.mkdir()
        self.remote = self.root / 'remote'
        self.outputs = self.remote / 'output/inference_samples'
        self.outputs.mkdir(parents=True)
        self.content = {'one.cif': b'data_one\n', 'two.cif': b'data_two\n'}
        for name, content in self.content.items():
            (self.outputs / name).write_bytes(content)
        self.machine = 'a' * 32
        self.job = dict(job_id='job', snapshot_id='job', runtime_protocol=4,
            status='completed', remote_dispatch_started=True, remote_dir='/srv/runs/job',
            target=dict(ssh_alias='gpu-test', runtime_root='/srv/rfd4', output_root='/srv/runs'),
            launch_checksum='b' * 64,
            machine_identity=hashlib.sha256(self.machine.encode()).hexdigest())
        self.service.save_job(self.job)
        (self.remote / 'receipt.json').write_text(json.dumps(
            dict(state='completed', launch_checksum=self.job['launch_checksum'])))
        (self.remote / 'run.log').write_text('completed\n')
        self.copies = 0
        self.copy_lock = threading.Lock()
        self.transfer_barrier = None
        self.transfer_mode = 'good'
        for method, effect in (
                ('named_exec', self.execute),
                ('run', self.download),
                ('submit_design_request', AssertionError('Must never rerun inference'))):
            mocked = patch.object(self.service, method, side_effect=effect)
            mocked.start()
            self.addCleanup(mocked.stop)

    def execute(self, destination, command, timeout=60):
        self.assertEqual(destination, self.job['target'])
        if command == 'cat /etc/machine-id':
            return self.machine
        args = shlex.split(command)
        self.assertEqual(args[:2], ['python3', '-c'])
        self.assertEqual(len(args), 4)
        relative = Path(args[3]).relative_to(self.job['remote_dir'])
        # Run the actual remote log/manifest readers against a local host fixture.
        result = subprocess.run([sys.executable, '-c', args[2], str(self.remote / relative)],
            capture_output=True, text=True, check=True, timeout=timeout)
        return result.stdout

    def download(self, args, timeout=60):
        self.assertEqual(args[:2], ['scp', '-r'])
        self.assertEqual(args[-2], 'gpu-test:/srv/runs/job/output/inference_samples')
        with self.copy_lock:
            self.copies += 1
        destination = Path(args[-1]) / 'inference_samples'
        shutil.copytree(self.outputs, destination)
        if self.transfer_mode == 'corrupt':
            (destination / 'two.cif').write_bytes(b'x' * len(self.content['two.cif']))
        elif self.transfer_mode == 'interrupted':
            raise ConnectionError('transfer interrupted')
        elif self.transfer_mode == 'disk_full':
            raise OSError('No space left on device')
        if self.transfer_barrier is not None:
            self.transfer_barrier.wait(timeout=10)
        return ''

    def assert_complete(self, result):
        self.assertEqual(result['collection'], 'complete')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['files']), len(self.content))
        for name, content in self.content.items():
            self.assertEqual((self.directory / 'results' / name).read_bytes(), content)
        self.assertEqual(self.service.read('job', 'job.json'), self.job)
        with patch.object(self.service, 'named_exec', side_effect=AssertionError('host stopped')), \
                patch.object(self.service, 'run', side_effect=AssertionError('must reuse cache')):
            self.assertEqual(self.service.collect('job'), result)

    def corrupt_cache(self):
        self.service.collect('job')
        damaged = b'x' * len(self.content['one.cif'])
        (self.directory / 'results/one.cif').write_bytes(damaged)
        return damaged

    def test_verified_cache_is_reused_offline(self):
        self.assert_complete(self.service.collect('job'))
        self.assertEqual(self.copies, 1)
        self.assertEqual(list(self.directory.glob('.previous-results-*')), [])

    def test_corrupted_cache_is_repaired_and_preserved(self):
        damaged = self.corrupt_cache()
        self.assert_complete(self.service.collect('job'))
        self.assertEqual(self.copies, 2)
        previous = list(self.directory.glob('.previous-results-*'))
        self.assertEqual(len(previous), 1)
        self.assertEqual((previous[0] / 'one.cif').read_bytes(), damaged)

    def test_missing_cached_file_is_repaired(self):
        self.service.collect('job')
        (self.directory / 'results/two.cif').unlink()
        self.assert_complete(self.service.collect('job'))
        self.assertEqual(self.copies, 2)

    def test_partial_cache_without_collection_receipt_is_repaired(self):
        results = self.directory / 'results'
        results.mkdir()
        (results / 'one.cif').write_bytes(self.content['one.cif'])
        self.assert_complete(self.service.collect('job'))
        self.assertEqual(self.copies, 1)

    def test_failed_download_preserves_cache_and_receipt_for_retry(self):
        damaged = self.corrupt_cache()
        receipt = (self.directory / 'collection.json').read_bytes()
        for mode in ('corrupt', 'interrupted', 'disk_full'):
            with self.subTest(mode=mode):
                self.transfer_mode = mode
                with self.assertRaises((ValueError, ConnectionError, OSError)):
                    self.service.collect('job')
                self.assertEqual((self.directory / 'results/one.cif').read_bytes(), damaged)
                self.assertEqual((self.directory / 'collection.json').read_bytes(), receipt)
                self.assertEqual(self.service.read('job', 'job.json'), self.job)
                self.assertEqual(list(self.directory.glob('.previous-results-*')), [])
                self.assertEqual(list(self.directory.glob('.collection-*')), [])
        self.transfer_mode = 'good'
        self.assert_complete(self.service.collect('job'))

    def test_concurrent_repairs_reuse_verified_replacement(self):
        damaged = self.corrupt_cache()
        self.transfer_barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: self.service.collect('job'), range(2)))
        for result in results:
            self.assert_complete(result)
        self.assertEqual(self.copies, 3)
        previous = list(self.directory.glob('.previous-results-*'))
        self.assertEqual(len(previous), 1)
        self.assertEqual((previous[0] / 'one.cif').read_bytes(), damaged)

    def test_dangling_results_symlink_is_repaired_without_following_it(self):
        missing = self.root / 'missing-results'
        (self.directory / 'results').symlink_to(missing, target_is_directory=True)
        self.assert_complete(self.service.collect('job'))
        self.assertFalse((self.directory / 'results').is_symlink())
        self.assertFalse(missing.exists())
        previous = list(self.directory.glob('.previous-results-*'))
        self.assertEqual(len(previous), 1)
        self.assertTrue(previous[0].is_symlink())

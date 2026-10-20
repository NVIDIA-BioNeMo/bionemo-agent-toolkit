"""Published execution protocol with real harmless shell counter, simulated owner."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
import execution_payload
import remote_job
from executor_ownership import checksum


class PublishedRemoteJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.directory = self.root / 'job'; self.directory.mkdir()
        self.id = 'a' * 32
        upload = self.root / 'upload'; upload.mkdir()
        script = '#!/bin/bash\nprintf x >> ' + shlex.quote(str(self.directory / 'counter')) + '\n'
        (upload / 'run.sh').write_text(script)
        owner = {'protocol': 1, 'executor_id': 'b' * 32, 'controller_root_sha256': 'c' * 64,
                 'linux_machine_id_sha256': 'd' * 64, 'brev': None}
        self.proof = {'owner': owner, 'owner_checksum': checksum(owner), 'brev': None}
        binding = {'kind': 'run', 'id': self.id, 'review_checksum': 'e' * 64, 'executor_ownership': self.proof}
        manifest = {'run.sh': hashlib.sha256(script.encode()).hexdigest()}
        self.expected = execution_payload.validate_manifest(manifest, binding)
        execution_payload.publish_payload(upload, self.directory / 'payload', manifest, binding)
        for target, kwargs in (
            ('executor_ownership.inspect', {'return_value': {'state': 'owned'}}),
            ('remote_job.pending_protected_package', {'return_value': None}),
            ('remote_job.pending_machine_package', {'return_value': None}),
            ('remote_job.identity', {'return_value': {'pid': 123, 'start': '1', 'boot': 'fixture', 'process_state': 'S'}}),
            ('remote_job.Path.home', {'return_value': self.root / 'home'}),
        ):
            mock = patch(target, **kwargs); mock.start(); self.addCleanup(mock.stop)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for folder, directories, files in os.walk(self.root): os.chmod(folder, 0o700)
        self.temp.cleanup()

    def launch(self):
        return remote_job.launch(self.directory, self.id, expected_payload=self.expected)

    def test_verified_payload_runs_once_and_keeps_mutable_files_outside(self):
        with patch('remote_job.subprocess.Popen') as spawn:
            self.assertEqual(self.launch()['state'], 'accepted')
            self.assertEqual(spawn.call_args.args[0][3], 'supervise-published')
            self.assertEqual(self.launch()['state'], 'unknown')
            self.assertEqual(spawn.call_count, 1)
        remote_job.supervise(self.directory, self.id, expected_payload=self.expected)
        self.assertEqual((self.directory / 'counter').read_text(), 'x')
        self.assertEqual(remote_job.status(self.directory, self.id)['state'], 'completed')
        self.assertEqual(set(p.name for p in (self.directory / 'payload').iterdir()), {'run.sh', 'payload-manifest.json'})
        with patch('remote_job.subprocess.Popen') as spawn:
            self.assertEqual(self.launch()['state'], 'completed'); spawn.assert_not_called()

    def test_wrong_review_identity_refuses_before_marker_or_spawn(self):
        # Even correctly published bytes cannot authorize a different job ID.
        with patch('remote_job.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'review identity'):
                remote_job.launch(self.directory, 'different', expected_payload=self.expected)
            spawn.assert_not_called()
        self.assertFalse((self.directory / 'job-state.json').exists())

    def test_legacy_dispatch_refuses_published_directory_but_reads_terminal_history(self):
        with patch('remote_job.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'legacy dispatch refused'):
                remote_job.launch(self.directory, self.id)
            spawn.assert_not_called()
        self.assertFalse((self.directory / 'job-state.json').exists())
        remote_job.write(self.directory / 'job-state.json', {'job_id': self.id, 'state': 'completed', 'exit_code': 0})
        with patch('remote_job.subprocess.Popen') as spawn:
            self.assertEqual(remote_job.launch(self.directory, self.id)['state'], 'completed')
            self.assertEqual(remote_job.status(self.directory, self.id)['state'], 'completed')
            spawn.assert_not_called()

    def test_foreign_owner_refuses_before_marker_or_spawn(self):
        with patch('executor_ownership.inspect', return_value={'state': 'foreign'}), patch('remote_job.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'ownership'): self.launch()
            spawn.assert_not_called()
        self.assertFalse((self.directory / 'job-state.json').exists())

    def test_cancel_before_launch_and_existing_fence_never_spawn(self):
        (self.directory / 'cancel-requested').touch()
        with patch('remote_job.subprocess.Popen') as spawn:
            self.assertEqual(self.launch()['reason'], 'cancelled_before_launch')
            (self.directory / 'cancel-requested').unlink()
            self.assertEqual(self.launch()['state'], 'failed'); spawn.assert_not_called()
        self.assertFalse((self.directory / 'counter').exists())

    def test_cancel_after_acceptance_stops_before_script(self):
        with patch('remote_job.subprocess.Popen'): self.launch()
        (self.directory / 'cancel-requested').touch()
        remote_job.supervise(self.directory, self.id, expected_payload=self.expected)
        self.assertEqual(remote_job.status(self.directory, self.id)['reason'], 'cancelled_before_execution')
        self.assertFalse((self.directory / 'counter').exists())

    def test_changed_payload_at_actual_path_refuses_supervision(self):
        with patch('remote_job.subprocess.Popen'): self.launch()
        os.chmod(self.directory / 'payload' / 'run.sh', 0o644)
        (self.directory / 'payload' / 'run.sh').write_text('exit 0\n')
        with self.assertRaisesRegex(ValueError, 'checksum differs'):
            remote_job.supervise(self.directory, self.id, expected_payload=self.expected)
        self.assertFalse((self.directory / 'counter').exists())
        self.assertEqual(remote_job.status(self.directory, self.id)['state'], 'unknown')


if __name__ == '__main__': unittest.main()

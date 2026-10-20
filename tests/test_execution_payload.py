"""Real filesystem/process publication tests; not live SSH or GPU acceptance."""
import hashlib
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
import execution_payload as payload


def contender(upload, destination, manifest, binding, ready, results):
    ready.wait(10)
    try:
        result = payload.publish_payload(upload, destination, manifest, binding)
        results.put(('ok', result['reused']))
    except Exception as error:
        import traceback
        results.put(('error', traceback.format_exc()))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.upload = self.root / 'upload'; self.upload.mkdir()
        self.content = {'input.cif': b'data_reviewed\n', 'run.sh': b'#!/bin/bash\nexit 0\n'}
        for name, content in self.content.items(): (self.upload / name).write_bytes(content)
        self.manifest = {name: hashlib.sha256(content).hexdigest() for name, content in self.content.items()}
        self.binding = {'job_id': 'a' * 32, 'plan_checksum': 'b' * 64, 'owner_checksum': 'c' * 64}
        self.destination = self.root / 'job' / 'payload'
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for folder, directories, files in os.walk(self.root):
            os.chmod(folder, 0o700)
        self.temp.cleanup()

    def publish(self, **kwargs):
        return payload.publish_payload(kwargs.get('upload', self.upload), self.destination,
                                       kwargs.get('manifest', self.manifest), kwargs.get('binding', self.binding))

    def test_new_inodes_survive_old_open_writer_and_retry_ignores_mutated_upload(self):
        with (self.upload / 'input.cif').open('r+b') as orphan:
            first = self.publish()
            self.assertFalse(first['reused'])
            self.assertNotEqual(os.stat(self.upload / 'input.cif').st_ino, os.stat(self.destination / 'input.cif').st_ino)
            orphan.seek(0); orphan.truncate(); orphan.write(b'late surviving SCP'); orphan.flush(); os.fsync(orphan.fileno())
        self.assertEqual((self.destination / 'input.cif').read_bytes(), self.content['input.cif'])
        self.assertTrue(self.publish()['reused'])
        self.assertEqual(set(p.name for p in self.destination.parent.iterdir()), {'.payload-publish.lock', 'payload'})

    def test_mismatch_never_replaces_or_repairs_publication(self):
        self.publish(); original = (self.destination / 'input.cif').read_bytes()
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            self.publish(binding=dict(self.binding, job_id='d' * 32))
        self.assertEqual((self.destination / 'input.cif').read_bytes(), original)
        os.chmod(self.destination / 'input.cif', 0o644)
        (self.destination / 'input.cif').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'checksum differs'): self.publish()
        self.assertEqual((self.destination / 'input.cif').read_bytes(), b'corrupted')

    def test_interrupted_copy_publishes_nothing_and_new_attempt_recovers(self):
        original = payload.read_file
        def interrupted(fd, name, **kwargs):
            if name == 'run.sh': raise OSError('injected read interruption')
            return original(fd, name, **kwargs)
        with patch.object(payload, 'read_file', interrupted):
            with self.assertRaisesRegex(OSError, 'interruption'): self.publish()
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.destination.parent.glob('.payload-*')), [self.destination.parent / '.payload-publish.lock'])
        self.assertFalse(self.publish()['reused'])

    def test_lost_publication_ack_reuses_exact_bytes(self):
        original = payload.publish
        def lost(source, destination, **kwargs):
            original(source, destination, **kwargs)
            raise ConnectionError('acknowledgment lost')
        with patch.object(payload, 'publish', lost):
            with self.assertRaisesRegex(ConnectionError, 'lost'): self.publish()
        self.assertTrue(self.destination.exists())
        self.assertTrue(self.publish()['reused'])

    def test_manifest_mode_change_refuses_without_repair(self):
        self.publish()
        os.chmod(self.destination / payload.RECEIPT, 0o644)
        with self.assertRaisesRegex(ValueError, 'receipt mode differs'): self.publish()
        self.assertEqual((self.destination / payload.RECEIPT).stat().st_mode & 0o777, 0o644)

    def test_parent_rename_cannot_redirect_publication_or_cleanup(self):
        original = payload.publish
        held_parent = self.destination.parent
        moved = self.root / 'moved-job'
        def replaced(source, destination, **kwargs):
            held_parent.rename(moved)
            held_parent.mkdir()
            (held_parent / 'sentinel').write_text('preserve')
            return original(source, destination, **kwargs)
        with patch.object(payload, 'publish', replaced): self.publish()
        self.assertFalse(self.destination.exists())
        self.assertEqual((moved / 'payload' / 'input.cif').read_bytes(), self.content['input.cif'])
        self.assertEqual((held_parent / 'sentinel').read_text(), 'preserve')

    def test_failed_directory_sync_can_be_retried_without_launch(self):
        original = payload.os.fsync
        calls = []
        def failed(fd):
            calls.append(fd)
            if len(calls) == 2: raise OSError('injected directory fsync failure')
            return original(fd)
        with patch.object(payload.os, 'fsync', failed):
            with self.assertRaisesRegex(OSError, 'fsync failure'): self.publish()
        self.assertFalse(self.destination.exists())
        self.publish()

    def test_invalid_uploads_refuse_without_publication(self):
        for kind in ('extra', 'missing', 'symlink', 'fifo', 'changed'):
            with self.subTest(kind=kind):
                attempt = self.root / kind; attempt.mkdir()
                for name, content in self.content.items(): (attempt / name).write_bytes(content)
                if kind == 'extra': (attempt / 'unexpected').write_text('extra')
                if kind in ('missing', 'symlink', 'fifo'): (attempt / 'input.cif').unlink()
                if kind == 'symlink': (attempt / 'input.cif').symlink_to(self.upload / 'input.cif')
                if kind == 'fifo': os.mkfifo(attempt / 'input.cif')
                if kind == 'changed': (attempt / 'input.cif').write_text('changed')
                with self.assertRaises((ValueError, OSError)): self.publish(upload=attempt)
                self.assertFalse(self.destination.exists())
        self.publish()

    def test_symlink_destination_and_ancestor_refuse(self):
        self.destination.parent.mkdir()
        self.destination.symlink_to(self.upload, target_is_directory=True)
        with self.assertRaises(OSError): self.publish()
        self.destination.unlink(); (self.destination.parent / '.payload-publish.lock').unlink(); self.destination.parent.rmdir()
        self.destination.parent.symlink_to(self.upload, target_is_directory=True)
        with self.assertRaises(OSError): self.publish()

    def test_competing_matching_and_conflicting_attempts(self):
        context = multiprocessing.get_context('fork')
        for matching in (True, False):
            with self.subTest(matching=matching):
                self.destination = self.root / str(matching) / 'payload'
                ready = context.Event(); results = context.Queue()
                bindings = [self.binding, self.binding if matching else dict(self.binding, job_id='d' * 32)]
                processes = [context.Process(target=contender, args=(self.upload, self.destination, self.manifest, binding, ready, results)) for binding in bindings]
                for process in processes: process.start()
                ready.set()
                outcomes = [results.get(timeout=10) for process in processes]
                for process in processes:
                    process.join(10); self.assertEqual(process.exitcode, 0)
                self.assertEqual(sum(item[0] == 'ok' for item in outcomes), 2 if matching else 1, outcomes)
                if matching: self.assertEqual(sorted(item[1] for item in outcomes), [False, True])
                self.assertEqual((self.destination / 'input.cif').read_bytes(), self.content['input.cif'])


if __name__ == '__main__': unittest.main()

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] /
                      'integrations/atomworks-studio/scripts'))
from idle_observation import file_identity, process_identity, observe_process, config_identity


class IdleObservationTests(unittest.TestCase):
    def test_top_level_configuration_fifo_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fifo'
            os.mkfifo(path)
            with self.assertRaisesRegex(ValueError,'regular file'):
                config_identity(path,{})

    def test_config_directory_additions_and_content_changes_are_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cache={}
            empty=config_identity(root,cache)
            (root/'extra.conf').write_text('workload')
            added=config_identity(root,cache)
            self.assertNotEqual(empty,added)
            (root/'extra.conf').write_text('modified')
            self.assertNotEqual(added,config_identity(root,cache))
            (root/'linked.conf').symlink_to(root/'extra.conf')
            with self.assertRaisesRegex(ValueError,'symlink'):config_identity(root,cache)

    def test_changed_content_and_permissions_invalidate_cached_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'agent'
            path.write_bytes(b'first')
            cache = {}
            first = file_identity(path, cache)
            path.write_bytes(b'other')
            second = file_identity(path, cache)
            self.assertNotEqual(first['sha256'], second['sha256'])
            self.assertEqual(second['sha256'], hashlib.sha256(b'other').hexdigest())
            path.chmod(0o600)
            third = file_identity(path, cache)
            self.assertEqual(third['mode'], '0o600')

    def test_missing_file_is_not_observed_as_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                file_identity(Path(directory) / 'missing', {})

    def test_proc_command_parentheses_do_not_shift_start_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            fields = ['S', '42'] + ['0'] * 17 + ['987654']
            (path / 'stat').write_text('123 (name (with) spaces) ' + ' '.join(fields))
            self.assertEqual(process_identity(path), {'start': '987654', 'ppid': 42})

    def test_live_identity_changes_are_not_stable(self):
        for changed_file, changed_value in (
            ('cmdline', 'agent\x00changed'),
            ('cgroup', '0::/system.slice/other.service\n'),
            ('status', 'Uid:\t1\t1\t1\t1\nName:\tagent\n'),
        ):
            with self.subTest(changed_file=changed_file), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                proc = root / '123'
                proc.mkdir()
                binary = root / 'agent'
                binary.write_bytes(b'fake executable')
                (proc / 'exe').symlink_to(binary)
                (proc / 'cmdline').write_bytes(b'agent\x00')
                (proc / 'cgroup').write_text('0::/system.slice/agent.service\n')
                (proc / 'status').write_text('Uid:\t0\t0\t0\t0\nName:\tagent\n')
                reads = []

                def identity(path):
                    reads.append(path)
                    if len(reads) == 2:
                        (proc / changed_file).write_text(changed_value)
                    return {'start':'999', 'ppid':1}

                def paths(value):
                    return root if value == '/proc' else Path(value)

                result = Mock(stdout='MainPID=123\nControlGroup=/system.slice/agent.service\n')
                with patch('idle_observation.Path', side_effect=paths), \
                     patch('idle_observation.process_identity', side_effect=identity), \
                     patch('idle_observation.subprocess.run', return_value=result):
                    self.assertFalse(observe_process(123, {}, {})['identity_stable'])

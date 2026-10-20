import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
import ssh_transport


class SSHTransportTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'kind': 'brev', 'instance': 'saved-machine',
                    'ssh_access': {'alias': 'saved-machine', 'host': 'verified-endpoint'}}
        self.run = Mock(return_value='ok')
        self.verify = patch('registry.verify_access')
        self.verifier = self.verify.start()
        self.addCleanup(self.verify.stop)

    def assert_secure(self, args):
        for option in ('StrictHostKeyChecking=yes', 'ForwardAgent=no', 'ControlMaster=no', 'ControlPath=none'):
            self.assertIn(option, args)
        self.assertIn('UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'), args)
        self.assertNotIn('brev', args)

    def test_execution_is_direct_and_cannot_start_via_cli_fallback(self):
        self.assertEqual(ssh_transport.execute(self.cfg, 'true', self.run, 15), 'ok')
        self.verifier.assert_called_once_with(self.cfg['ssh_access'], self.run)
        args, timeout = self.run.call_args.args
        self.assertEqual(timeout, 15)
        self.assertEqual(args[0], 'ssh')
        self.assertEqual(args[-3:], ['--', 'saved-machine', 'true'])
        self.assert_secure(args)

    def test_upload_and_download_use_same_safe_transport(self):
        for download, expected in ((False, ['/tmp/payload', 'saved-machine:/srv/parent']),
                                   (True, ['saved-machine:/tmp/payload', '/srv/parent'])):
            with self.subTest(download=download):
                self.run.reset_mock()
                ssh_transport.copy(self.cfg, '/tmp/payload', '/srv/parent', download, self.run, 60)
                args = self.run.call_args.args[0]
                self.assertEqual(args[:2], ['scp', '-r'])
                self.assertEqual(args[-2:], expected)
                self.assert_secure(args)
                self.assertEqual(self.run.call_count, 1)

    def test_unverified_legacy_brev_access_requires_explicit_refresh(self):
        for access in (None,):
            cfg = dict(self.cfg, ssh_access=access)
            with self.assertRaisesRegex(ValueError, 'Refresh and verify'):
                ssh_transport.execute(cfg, 'true', self.run, 15)
            self.run.assert_not_called()

    def test_alias_mismatch_blocks_both_transports_before_execution_or_copy(self):
        for kind in ('ssh', 'brev'):
            cfg = dict(self.cfg, kind=kind, ssh_host='saved-machine', ssh_access={'alias': 'other'})
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, 'different alias'):
                    ssh_transport.execute(cfg, 'true', self.run, 15)
                with self.assertRaisesRegex(ValueError, 'different alias'):
                    ssh_transport.copy(cfg, '/tmp/a', '/srv', False, self.run, 15)
                self.run.assert_not_called()
                self.verifier.assert_not_called()

    def test_identity_drift_prevents_any_remote_command(self):
        self.verifier.side_effect = ValueError('SSH identity changed')
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            ssh_transport.copy(self.cfg, '/tmp/x', '/srv', False, self.run, 60)
        self.run.assert_not_called()

    def test_connection_failure_has_no_refresh_start_or_retry(self):
        for error in (TimeoutError('unreachable'), RuntimeError('Host key verification failed')):
            with self.subTest(error=error):
                self.run.reset_mock()
                self.run.side_effect = error
                with self.assertRaises(type(error)):
                    ssh_transport.execute(self.cfg, 'true', self.run, 15)
                self.assertEqual(self.run.call_count, 1)
                self.assertEqual(self.run.call_args.args[0][0], 'ssh')

    def test_existing_ssh_also_requires_host_verification_without_mux_reuse(self):
        ssh_transport.execute({'kind': 'ssh', 'ssh_host': 'my-host'}, 'true', self.run, 15)
        args = self.run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('ControlPath=none', args)

    def test_only_explicit_brev_refresh_can_remember_a_first_use_key(self):
        ssh_transport.execute(self.cfg,'true',self.run,15,trust_on_first_use=True)
        args=self.run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=accept-new',args)
        self.assertIn('UserKnownHostsFile='+str(Path.home()/'.ssh/known_hosts'),args)
        self.assertNotIn('StrictHostKeyChecking=no',args)
        self.run.reset_mock()
        with self.assertRaisesRegex(ValueError,'only during Brev'):
            ssh_transport.execute({'kind':'ssh','ssh_host':'my-host'},'true',self.run,15,trust_on_first_use=True)
        self.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

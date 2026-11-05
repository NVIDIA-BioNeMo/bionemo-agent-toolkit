"""Setup orchestration tests; GPU/installer doubles do not qualify inference."""
from contextlib import ExitStack
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
import runtime_setup as setup
from runtime_recipe import PROBE, RECIPE


class RuntimeSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'runtime'
        self.outputs = Path(self.temp.name) / 'outputs'

    def host(self, output):
        runner = Mock(return_value=Mock(stdout=output))
        with patch('platform.system', return_value='Linux'), patch('platform.machine', return_value='x86_64'), \
                patch('platform.libc_ver', return_value=('glibc', '2.35')):
            setup.host_preflight(runner)

    def test_host_preflight_accepts_compatible_driver_and_memory(self):
        self.host('580.196.07, 81920\n')

    def test_old_driver_and_two_small_gpus_fail(self):
        for output, reason in [('565.57.01, 81920\n', 'driver 580'),
                               ('580.178.04, 49140\n580.178.04, 49140\n', '75 GiB'),
                               ('', 'driver 580')]:
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, reason):
                self.host(output)

    def test_incompatible_host_does_not_stage_or_download(self):
        with patch.object(setup, 'host_preflight', side_effect=ValueError('host incompatible')), \
                patch.object(setup, 'stage') as stage, patch.object(setup, 'install') as install:
            with self.assertRaisesRegex(ValueError, 'host incompatible'):
                setup.setup(self.root, self.outputs)
            stage.assert_not_called()
            install.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_readiness_executes_the_shared_studio_probe_and_local_bundle_paths(self):
        checks = {name: True for name in ('platform', 'python', 'revision', 'source',
                                          'dependencies', 'entrypoint', 'weights', 'cuda', 'gpu')}
        runner = Mock(return_value=Mock(stdout=json.dumps({'recipe_id': RECIPE['id'], 'checks': checks})))
        setup.readiness(self.root, runner)
        argv = runner.call_args.args[0]
        self.assertEqual(argv[:4], [str(self.root / 'model/.venv/bin/python'), '-B', '-c', PROBE])
        cfg = json.loads(argv[4])
        self.assertEqual(cfg['weight_paths'], [str(self.root / 'model-bundle' / item['name'])
                                              for item in RECIPE['model_bundle']['files']])
        for name in checks:
            with self.subTest(check=name):
                runner.return_value.stdout = json.dumps({'recipe_id': RECIPE['id'], 'checks': checks | {name: False}})
                with self.assertRaisesRegex(ValueError, name):
                    setup.readiness(self.root, runner)

    def test_active_execution_or_setup_prevents_runtime_mutation(self):
        self.root.mkdir()
        self.outputs.mkdir()
        for path in (self.root / '.rfd4-setup.lock', self.outputs / '.rfd4-execution.lock'):
            with self.subTest(lock=path), path.open('a') as lock, \
                    patch.object(setup, 'host_preflight'), patch.object(setup, 'stage') as stage:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError, 'active'):
                    setup.setup(self.root, self.outputs)
                stage.assert_not_called()

    def test_failed_stage_never_reports_ready_or_runs_smoke(self):
        for failed in ('install', 'download_bundle', 'readiness'):
            with self.subTest(stage=failed), ExitStack() as stack:
                helpers = {name: stack.enter_context(patch.object(setup, name))
                           for name in ('host_preflight', 'stage', 'install', 'download_bundle',
                                        'verify_source', 'readiness', 'smoke')}
                helpers[failed].side_effect = ValueError('broken stage')
                with self.assertRaisesRegex(ValueError, 'broken stage'):
                    setup.setup(self.root, self.outputs)
                helpers['smoke'].assert_not_called()

    def test_smoke_uses_verified_local_bundle_offline_and_preserves_prior_outputs(self):
        self.root.mkdir()
        runner = Mock(return_value=Mock(stdout=json.dumps({'structures': [{'path': 'design.cif', 'atoms': 1}]})))
        first = setup.smoke(self.root, runner)
        second = setup.smoke(self.root, runner)
        self.assertNotEqual(first['output_dir'], second['output_dir'])
        self.assertTrue(Path(first['output_dir']).is_dir())
        for call in runner.call_args_list[::2]:
            self.assertEqual(call.kwargs['env']['HF_HUB_OFFLINE'], '1')
            self.assertIn('hf_ckpt_path=' + str(self.root / 'model-bundle'), call.args[0])
            self.assertIn('~metrics', call.args[0])
        runner.side_effect = subprocess.CalledProcessError(1, 'generation failed')
        with self.assertRaises(subprocess.CalledProcessError):
            setup.smoke(self.root, runner)

    def test_roots_inside_model_or_through_symlinks_are_refused(self):
        self.root.mkdir()
        link = Path(self.temp.name) / 'runtime-link'
        link.symlink_to(self.root, target_is_directory=True)
        with patch.object(setup, 'host_preflight') as host:
            for root, output in ((link, self.outputs), (self.root, self.root / 'model/runs'),
                                 (self.root, self.root / 'model-bundle/runs')):
                with self.subTest(root=root, output=output), self.assertRaises(ValueError):
                    setup.setup(root, output)
            host.assert_not_called()


if __name__ == '__main__':
    unittest.main()

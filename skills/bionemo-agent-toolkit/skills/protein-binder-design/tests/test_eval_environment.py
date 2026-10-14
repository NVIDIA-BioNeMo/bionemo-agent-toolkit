# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Ensure failed dependency setup cannot be reported as a ready evaluation."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eval_setup", SOURCE_ROOT / "evals/files/setup_eval_env.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class EvaluationEnvironmentTests(unittest.TestCase):
    def setUp(self):
        # Exercise the stdlib fallback independently of tools on the test host.
        self.find_tool = patch.object(setup.shutil, "which", return_value=None)
        self.find_tool.start()
        self.addCleanup(self.find_tool.stop)

    def test_install_failure_stops_before_import_check(self):
        errors = io.StringIO()
        with patch.object(setup, "select_python", return_value="/python3.12"), patch.object(setup.subprocess, "run", side_effect=[None, subprocess.CalledProcessError(1, ["pip"])]) as run, contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.setup(Path("/workspace/test-venv")), setup.EXIT_INSTALL)
        self.assertEqual(run.call_count, 2)
        self.assertIn("dependency installation", errors.getvalue())

    def test_missing_venv_support_fails_before_install(self):
        errors = io.StringIO()
        with patch.object(setup, "select_python", return_value="/python3.12"), patch.object(setup.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["venv"])) as run, contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.setup(), setup.EXIT_VENV)
        run.assert_called_once()
        self.assertIn("virtual environment creation", errors.getvalue())

    def test_uv_installs_into_the_isolated_environment_without_python_bootstrap(self):
        environment = Path("/workspace/test-venv")
        python = str(environment / "bin/python")
        with (
            patch.object(setup, "select_python", return_value="/python3.11"),
            patch.object(setup.shutil, "which", return_value="/usr/local/bin/uv"),
            patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(setup.setup(environment), 0)
        create, install, verify = run.call_args_list
        self.assertEqual(create.args[0][0:2], ["/usr/local/bin/uv", "venv"])
        self.assertEqual(create.args[0][-1], str(environment))
        self.assertEqual(install.args[0][0:5], ["/usr/local/bin/uv", "pip", "install", "--python", python])
        for command in (create, install):
            self.assertIn("--no-python-downloads", command.args[0])
            self.assertIn("--no-cache", command.args[0])
            self.assertFalse(command.kwargs["shell"])
            self.assertEqual(command.kwargs["env"]["UV_HTTP_RETRIES"], "1")
            self.assertEqual(command.kwargs["env"]["UV_HTTP_TIMEOUT"], "15")
        self.assertIn("--only-binary=:all:", install.args[0])
        self.assertEqual(install.args[0][-2:], list(setup.DEPENDENCIES))
        self.assertEqual(verify.args[0], [python, "-c", setup.IMPORT_CHECK])

    def test_uv_creation_failure_stops_before_install(self):
        errors = io.StringIO()
        with (
            patch.object(setup, "select_python", return_value="/python3.11"),
            patch.object(setup.shutil, "which", return_value="/usr/local/bin/uv"),
            patch.object(setup.subprocess, "run", side_effect=PermissionError("workspace is not writable")) as run,
            contextlib.redirect_stderr(errors),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(setup.setup(), setup.EXIT_VENV)
        run.assert_called_once()
        self.assertIn("workspace is not writable", errors.getvalue())

    def test_uv_install_failure_stops_before_import_check(self):
        output = io.StringIO()
        with (
            patch.object(setup, "select_python", return_value="/python3.11"),
            patch.object(setup.shutil, "which", return_value="/usr/local/bin/uv"),
            patch.object(setup.subprocess, "run", side_effect=[None, subprocess.CalledProcessError(1, ["uv", "pip"])]) as run,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(setup.setup(), setup.EXIT_INSTALL)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("Starting dependency import verification", output.getvalue())

    def test_interpreter_failure_is_distinct_and_runs_no_install_commands(self):
        errors = io.StringIO()
        with (
            patch.object(setup, "select_python", side_effect=RuntimeError("Python 3.10-3.13 unavailable")),
            patch.object(setup.subprocess, "run") as run,
            contextlib.redirect_stderr(errors),
        ):
            self.assertEqual(setup.setup(), setup.EXIT_INTERPRETER)
        run.assert_not_called()
        self.assertIn("interpreter selection", errors.getvalue())

    def test_import_failure_is_distinct_from_installation_failure(self):
        errors, output = io.StringIO(), io.StringIO()
        with (
            patch.object(setup, "select_python", return_value="/python3.12"),
            patch.object(setup.subprocess, "run", side_effect=[None, None, subprocess.CalledProcessError(1, ["python"])]) as run,
            contextlib.redirect_stderr(errors),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(setup.setup(), setup.EXIT_IMPORT)
        self.assertEqual(run.call_count, 3)
        self.assertIn("dependency import verification", errors.getvalue())
        self.assertNotIn("for Python commands", output.getvalue())

    def test_success_requires_all_setup_phases(self):
        with (
            patch.object(setup, "select_python", return_value="/python3.12"),
            patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(setup.setup(), 0)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args.args[0][-1], setup.IMPORT_CHECK)

    def test_supported_default_python_does_not_require_a_newer_interpreter(self):
        for version in ((3, 10), (3, 11), (3, 12), (3, 13)):
            with (
                self.subTest(version=version),
                patch.object(setup.sys, "version_info", version),
                patch.object(setup.shutil, "which") as find_python,
                patch.object(setup.subprocess, "run") as run,
            ):
                self.assertEqual(setup.select_python(), sys.executable)
                find_python.assert_not_called()
                run.assert_not_called()

    def test_old_default_python_uses_an_installed_compatible_one(self):
        with patch.object(setup.sys, "version_info", (3, 9)), patch.object(setup.shutil, "which", return_value="/opt/bin/python3.12"), patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(setup.select_python(), "/opt/bin/python3.12")

    def test_newer_python_without_pinned_wheels_uses_a_supported_interpreter(self):
        with patch.object(setup.sys, "version_info", (3, 14)), patch.object(setup.shutil, "which", return_value="/opt/bin/python3.13"), patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(setup.select_python(), "/opt/bin/python3.13")

    def test_broken_candidate_does_not_hide_an_available_interpreter(self):
        with (
            patch.object(setup.sys, "version_info", (3, 9)),
            patch.object(setup.shutil, "which", side_effect=["/broken/python3.13", "/opt/bin/python3.12"]),
            patch.object(setup.subprocess, "run", side_effect=[OSError("unavailable"), subprocess.CompletedProcess([], 0)]),
        ):
            self.assertEqual(setup.select_python(), "/opt/bin/python3.12")

    def test_no_compatible_python_is_an_explicit_failure(self):
        with patch.object(setup.sys, "version_info", (3, 9)), patch.object(setup.shutil, "which", return_value=None), self.assertRaisesRegex(RuntimeError, "Python 3.10-3.13"):
            setup.select_python()

    def test_failed_install_retains_real_child_stdout_and_stderr(self):
        run_process = subprocess.run

        def simulate_install(command, **kwargs):
            if command[1:3] == ["-m", "venv"]:
                return subprocess.CompletedProcess(command, 0)
            return run_process(
                [sys.executable, "-c", "import sys; print('package download started'); "
                 "print('package index unavailable', file=sys.stderr); sys.exit(1)"],
                **kwargs,
            )

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "artifacts/pbd-eval-setup.log"
            with (
                patch.object(setup, "SETUP_LOG", log_path),
                patch.object(setup, "select_python", return_value=sys.executable),
                patch.object(setup.subprocess, "run", side_effect=simulate_install) as run,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(setup.main(), setup.EXIT_INSTALL)
            transcript = log_path.read_text()
        self.assertEqual(run.call_count, 2)
        self.assertIn("Bootstrap interpreter:", transcript)
        self.assertIn("package download started", transcript)
        self.assertIn("package index unavailable", transcript)
        self.assertIn("Evaluation setup failed during dependency installation", transcript)
        self.assertNotIn("Starting dependency import verification", transcript)

    def test_missing_interpreter_reason_is_retained_without_starting_subprocesses(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "setup.log"
            with (
                patch.object(setup, "SETUP_LOG", log_path),
                patch.object(setup, "select_python", side_effect=RuntimeError("Python 3.10-3.13 unavailable")),
                patch.object(setup.subprocess, "run") as run,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(setup.main(), setup.EXIT_INTERPRETER)
            self.assertIn("Python 3.10-3.13 unavailable", log_path.read_text())
        run.assert_not_called()

    def test_unwritable_log_does_not_replace_the_setup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            occupied_path = Path(directory) / "file"
            occupied_path.write_text("already a file")
            errors = io.StringIO()
            with (
                patch.object(setup, "SETUP_LOG", occupied_path / "setup.log"),
                patch.object(setup, "setup", return_value=setup.EXIT_VENV) as run_setup,
                contextlib.redirect_stderr(errors),
            ):
                self.assertEqual(setup.main(), setup.EXIT_VENV)
            run_setup.assert_called_once_with(log=None)
            self.assertIn("Could not create setup log", errors.getvalue())


if __name__ == "__main__":
    unittest.main()

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
        self.assertIn("venv/ensurepip", errors.getvalue())

    def test_interpreter_failure_is_distinct_and_runs_no_install_commands(self):
        errors = io.StringIO()
        with (
            patch.object(setup, "select_python", side_effect=RuntimeError("Python 3.12+ unavailable")),
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

    def test_old_default_python_uses_an_installed_compatible_one(self):
        with patch.object(setup.sys, "version_info", (3, 10)), patch.object(setup.shutil, "which", return_value="/opt/bin/python3.12"), patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(setup.select_python(), "/opt/bin/python3.12")

    def test_no_compatible_python_is_an_explicit_failure(self):
        with patch.object(setup.sys, "version_info", (3, 10)), patch.object(setup.shutil, "which", return_value=None), self.assertRaisesRegex(RuntimeError, "Python 3.12"):
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
                patch.object(setup, "select_python", side_effect=RuntimeError("Python 3.12+ unavailable")),
                patch.object(setup.subprocess, "run") as run,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(setup.main(), setup.EXIT_INTERPRETER)
            self.assertIn("Python 3.12+ unavailable", log_path.read_text())
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

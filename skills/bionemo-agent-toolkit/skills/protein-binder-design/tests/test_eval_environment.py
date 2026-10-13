# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Ensure failed dependency setup cannot be reported as a ready evaluation."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eval_setup", SKILL / "evals/files/setup_eval_env.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class EvaluationEnvironmentTests(unittest.TestCase):
    def test_install_failure_stops_before_import_check(self):
        errors = io.StringIO()
        with patch.object(setup, "select_python", return_value="/python3.12"), patch.object(setup.subprocess, "run", side_effect=[None, subprocess.CalledProcessError(1, ["pip"])]) as run, contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.setup(Path("/workspace/test-venv")), 1)
        self.assertEqual(run.call_count, 2)
        self.assertIn("dependency installation", errors.getvalue())

    def test_missing_venv_support_fails_before_install(self):
        errors = io.StringIO()
        with patch.object(setup, "select_python", return_value="/python3.12"), patch.object(setup.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["venv"])) as run, contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.setup(), 1)
        run.assert_called_once()
        self.assertIn("venv/ensurepip", errors.getvalue())

    def test_old_default_python_uses_an_installed_compatible_one(self):
        with patch.object(setup.sys, "version_info", (3, 10)), patch.object(setup.shutil, "which", return_value="/opt/bin/python3.12"), patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(setup.select_python(), "/opt/bin/python3.12")

    def test_no_compatible_python_is_an_explicit_failure(self):
        with patch.object(setup.sys, "version_info", (3, 10)), patch.object(setup.shutil, "which", return_value=None), self.assertRaisesRegex(RuntimeError, "Python 3.12"):
            setup.select_python()


if __name__ == "__main__":
    unittest.main()

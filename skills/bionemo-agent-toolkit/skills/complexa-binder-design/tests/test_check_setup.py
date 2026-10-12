# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Readiness checks must distinguish CPU preparation from an absent runtime."""
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_setup.sh"


class SetupTests(unittest.TestCase):
    def run_check(self, *args, credential=None):
        with tempfile.TemporaryDirectory() as directory:
            env = {"PATH": "/usr/bin:/bin", "PYTHON": sys.executable,
                   "COMPLEXA_REPO": str(Path(directory) / "absent")}
            if credential:
                env["NGC_API_KEY"] = credential
            return subprocess.run(["bash", str(SCRIPT), *args], env=env,
                                  capture_output=True, text=True, timeout=30, shell=False)

    def test_preparation_succeeds_without_gpu_cli_weights_or_credentials(self):
        result = self.run_check("--prepare-only")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PREPARATION PREREQUISITES PRESENT", result.stdout)
        self.assertNotIn("complexa CLI", result.stdout)

    def test_absent_generation_runtime_returns_failure(self):
        result = self.run_check("--af2-bypass", "--endpoint", "local")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("NOT READY", result.stdout)
        self.assertIn("CLI not found", result.stdout)
        self.assertIn("COMPLEXA_REPO unset or not a directory", result.stdout)
        self.assertNotIn("=> PREREQUISITES PRESENT", result.stdout)

    def test_credential_value_is_never_echoed(self):
        credential = "SYNTHETIC_TEST_CREDENTIAL_MUST_NOT_APPEAR"
        result = self.run_check(credential=credential)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(credential, result.stdout + result.stderr)
        self.assertIn("credential present", result.stdout)

    def test_invalid_options_fail(self):
        for args in (("--endpoint",), ("--endpoint", "unknown"), ("--unknown",)):
            with self.subTest(args=args):
                self.assertEqual(self.run_check(*args).returncode, 2)

    def test_gpu_and_checkpoint_requirements_are_not_optional_warnings(self):
        # A copied checklist with synthetic inventory and a torch stub tests
        # prerequisite logic without installing models or requiring a GPU.
        for cuda, weights in ((False, True), (True, False), (True, True)):
            with self.subTest(cuda=cuda, weights=weights), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                scripts = root / "skill/scripts"
                scripts.mkdir(parents=True)
                script = scripts / "check_setup.sh"
                shutil.copy2(SCRIPT, script)
                ipsae = root / "skill/vendor/ipsae/ipsae.py"
                ipsae.parent.mkdir(parents=True)
                ipsae.write_text("# presence fixture only\n")
                repo = root / "repo"
                (repo / "configs").mkdir(parents=True)
                (repo / "configs/search_binder_local_pipeline.yaml").write_text("{}\n")
                if weights:
                    (repo / "ckpts").mkdir()
                    for name in ("complexa.ckpt", "complexa_ae.ckpt"):
                        (repo / "ckpts" / name).write_bytes(b"synthetic inventory fixture")
                executable = root / "complexa"
                executable.write_text("#!/bin/sh\nexit 0\n")
                executable.chmod(0o700)
                (root / "torch.py").write_text(
                    "from types import SimpleNamespace\ncuda=SimpleNamespace(is_available=lambda: " + str(cuda) + ")\n")
                result = subprocess.run(["bash", str(script), "--af2-bypass", "--endpoint", "local"],
                                        env={"PATH": "/usr/bin:/bin", "PYTHON": sys.executable,
                                             "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1",
                                             "COMPLEXA_REPO": str(repo), "COMPLEXA_BIN": str(executable)},
                                        capture_output=True, text=True, timeout=30, shell=False)
                self.assertEqual(result.returncode, 0 if cuda and weights else 1, result.stdout + result.stderr)
                if not cuda:
                    self.assertIn("[FAIL] CUDA unavailable", result.stdout)
                if not weights:
                    self.assertIn("[FAIL] default checkpoints missing/empty", result.stdout)


if __name__ == "__main__":
    unittest.main()

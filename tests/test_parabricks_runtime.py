# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Readiness probe regressions using synthetic nvidia-smi responses."""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPT = (Path(__file__).resolve().parents[1] / "library-skills" / "parabricks"
          / "scripts" / "check_parabricks_runtime.py")
spec = importlib.util.spec_from_file_location("parabricks_runtime", SCRIPT)
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)


class GpuProbeTests(unittest.TestCase):
    def probe(self, rows, banner="| Driver Version: 580.173.02 | CUDA Version: 13.0 |",
              banner_returncode=0, query_returncode=0):
        calls = []

        def runner(command, timeout):
            calls.append(command)
            self.assertEqual(timeout, 7)
            if len(command) > 1:
                # Reproduce the real driver rejecting the previous query.
                if "cuda_version" in command[1]:
                    return runtime.CommandResult(command, 2, "", 'Field "cuda_version" is not a valid field to query.')
                return runtime.CommandResult(command, query_returncode, rows, "query failed")
            return runtime.CommandResult(command, banner_returncode, banner, "banner failed")

        with patch.object(runtime.shutil, "which", return_value="/usr/bin/nvidia-smi"):
            report = runtime.check_nvidia_smi(runner, 7)
        return report, calls

    def test_supported_query_detects_multiple_gpus_and_driver_cuda(self):
        report, calls = self.probe(
            "NVIDIA RTX A6000, 49140, 48100, 580.173.02, 8.6\n"
            "NVIDIA A100, 81920, 80000, 580.173.02, 8.0\n"
        )
        self.assertEqual(report["status"], "ok")
        self.assertEqual(len(report["gpus"]), 2)
        self.assertEqual(report["gpus"][1]["memory_total_gb"], 80)
        self.assertEqual(report["gpus"][0]["driver_version"], "580.173.02")
        self.assertEqual(report["gpus"][0]["cuda_version"], "13.0")
        self.assertEqual(report["gpus"][0]["compute_capability"], "8.6")
        self.assertEqual(len(calls), 2)

    def test_optional_cuda_probe_cannot_invalidate_gpu_discovery(self):
        for banner, returncode in [("CUDA Version: N/A", 0), ("", 1), ("CUDA Version: 13.0", 1)]:
            with self.subTest(banner=banner, returncode=returncode):
                report, _ = self.probe("NVIDIA A100, 81920, N/A, 580.173.02, 8.0", banner, returncode)
                self.assertEqual(report["status"], "ok")
                self.assertIsNone(report["gpus"][0]["cuda_version"])
                self.assertIsNone(report["gpus"][0]["memory_free_gb"])
                self.assertIn("could not be read", report["detail"])

    def test_failed_query_remains_failed(self):
        report, calls = self.probe("", query_returncode=1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(calls), 1)

    def test_malformed_rows_do_not_claim_a_gpu(self):
        report, _ = self.probe("unexpected output")
        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["gpus"], [])

    def test_missing_nvidia_smi_does_not_execute_commands(self):
        with patch.object(runtime.shutil, "which", return_value=None), \
                patch.object(runtime, "run_command") as runner:
            report = runtime.check_nvidia_smi(runner, 7)
        runner.assert_not_called()
        self.assertEqual(report["status"], "missing")


if __name__ == "__main__":
    unittest.main()

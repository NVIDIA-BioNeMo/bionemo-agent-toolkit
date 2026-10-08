# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Readiness probe regressions using synthetic nvidia-smi responses."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "library-skills" / "parabricks"
          / "scripts" / "check_parabricks_runtime.sh")

# Host tools the script needs; everything else (including any real nvidia-smi
# or docker) is kept off PATH so the fake below is the only GPU probe.
HOST_TOOLS = ("awk", "basename", "cat", "df", "dirname", "getconf", "grep",
              "head", "mktemp", "rm", "sed", "tail", "tr", "uname")

FAKE_NVIDIA_SMI = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_DIR/calls"
if [ $# -gt 0 ]; then
  case "$*" in
    *cuda_version*)
      # Reproduce the real driver rejecting the previous query.
      echo 'Field "cuda_version" is not a valid field to query.' >&2
      exit 2 ;;
  esac
  cat "$FAKE_DIR/rows"
  echo 'query failed' >&2
  exit "$(cat "$FAKE_DIR/query_rc")"
fi
cat "$FAKE_DIR/banner"
echo 'banner failed' >&2
exit "$(cat "$FAKE_DIR/banner_rc")"
"""


class GpuProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for tool in HOST_TOOLS:
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)

    def install_fake_nvidia_smi(self, rows, banner, banner_returncode, query_returncode):
        (self.tmp / "rows").write_text(rows)
        (self.tmp / "banner").write_text(banner)
        (self.tmp / "banner_rc").write_text(str(banner_returncode))
        (self.tmp / "query_rc").write_text(str(query_returncode))
        fake = self.bin / "nvidia-smi"
        fake.write_text(FAKE_NVIDIA_SMI)
        fake.chmod(0o755)

    def run_script(self):
        env = {"PATH": str(self.bin), "FAKE_DIR": str(self.tmp), "HOME": str(self.tmp)}
        completed = subprocess.run(
            [shutil.which("bash"), str(SCRIPT), "--format", "json", "--timeout", "7"],
            check=True, capture_output=True, text=True, env=env,
        )
        return json.loads(completed.stdout)["checks"]["nvidia_smi"]

    def calls(self):
        calls_file = self.tmp / "calls"
        return calls_file.read_text().splitlines() if calls_file.exists() else []

    def probe(self, rows, banner="| Driver Version: 580.173.02 | CUDA Version: 13.0 |",
              banner_returncode=0, query_returncode=0):
        self.install_fake_nvidia_smi(rows, banner, banner_returncode, query_returncode)
        return self.run_script(), self.calls()

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
                (self.tmp / "calls").unlink(missing_ok=True)
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
        report = self.run_script()
        self.assertEqual(self.calls(), [])
        self.assertEqual(report["status"], "missing")


if __name__ == "__main__":
    unittest.main()

# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Readiness probe regressions using synthetic nvidia-smi responses."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "library-skills" / "parabricks"
          / "scripts" / "check_parabricks_runtime.sh")

# Host tools the script needs; everything else (including any real nvidia-smi
# or docker) is kept off PATH so the fake below is the only GPU probe.
HOST_TOOLS = ("awk", "basename", "bash", "cat", "df", "dirname", "getconf", "grep",
              "head", "mktemp", "rm", "sed", "sleep", "tail", "timeout", "gtimeout",
              "tr", "uname")

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


class FakeHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for tool in HOST_TOOLS:
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)


class GpuProbeTests(FakeHostTests):
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


class ContainerProbeTests(FakeHostTests):
    def setUp(self):
        super().setUp()
        fake = self.bin / "docker"
        fake.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_DIR/docker-calls"
case "$1" in
  --version) echo 'Docker version 27.0.0, build test' ;;
  info) echo '{}' ;;
  run) echo 'synthetic container probe' ;;
esac
''')
        fake.chmod(0o755)

    def run_probe(self, *args, legacy=False):
        command = ([sys.executable, str(SCRIPT.with_suffix(".py"))] if legacy else
                   [shutil.which("bash"), str(SCRIPT)])
        return subprocess.run(
            [*command, "--format", "json", *args],
            capture_output=True, text=True, timeout=10,
            env={"PATH": str(self.bin), "FAKE_DIR": str(self.tmp), "HOME": str(self.tmp)},
        )

    def container_calls(self):
        path = self.tmp / "docker-calls"
        return [line for line in path.read_text().splitlines() if line.startswith("run ")] if path.exists() else []

    def test_version_alone_does_not_launch_a_container(self):
        process = self.run_probe("--parabricks-version", "4.7.1-1")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.container_calls(), [])
        self.assertEqual(json.loads(process.stdout)["checks"]["parabricks_container"]["status"], "not_checked")

    def test_cuda_opt_in_does_not_authorize_parabricks_probe(self):
        process = self.run_probe("--run-container-check", "--parabricks-version", "4.7.1-1")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(len(self.container_calls()), 1)
        self.assertIn("nvidia-smi", self.container_calls()[0])
        self.assertNotIn("pbrun", self.container_calls()[0])

    def test_parabricks_opt_in_launches_only_selected_probe(self):
        process = self.run_probe("--run-parabricks-check", "--parabricks-version=4.7.1-1")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.container_calls(), [
            "run --rm --gpus all nvcr.io/nvidia/clara/clara-parabricks:4.7.1-1 pbrun --help"
        ])
        self.assertEqual(json.loads(process.stdout)["checks"]["parabricks_container"]["status"], "ok")

    def test_missing_version_fails_before_any_probe(self):
        process = self.run_probe("--run-parabricks-check")
        self.assertEqual(process.returncode, 2)
        self.assertIn("requires --parabricks-version", process.stderr)
        self.assertFalse((self.tmp / "docker-calls").exists())

    def test_digest_reference_is_preserved_and_requires_opt_in(self):
        image = "nvcr.io/nvidia/clara/clara-parabricks@sha256:" + "a" * 64
        process = self.run_probe("--parabricks-image", image)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.container_calls(), [])
        process = self.run_probe("--run-parabricks-check", "--parabricks-image", image)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.container_calls(), [f"run --rm --gpus all {image} pbrun --help"])

    def test_conflicting_image_selectors_fail_before_any_probe(self):
        process = self.run_probe("--parabricks-version", "4.7.1-1", "--parabricks-image", "example:tag")
        self.assertEqual(process.returncode, 2)
        self.assertFalse((self.tmp / "docker-calls").exists())

    def test_missing_docker_reports_gap_without_attempting_container(self):
        (self.bin / "docker").unlink()
        process = self.run_probe("--run-parabricks-check", "--parabricks-version", "4.7.1-1")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["checks"]["parabricks_container"]["status"], "missing")
        self.assertEqual(self.container_calls(), [])

    def test_missing_timeout_fails_before_any_probe(self):
        for name in ("timeout", "gtimeout"):
            (self.bin / name).unlink(missing_ok=True)
        process = self.run_probe("--timeout", "1", "--run-container-check")
        self.assertEqual(process.returncode, 2)
        self.assertIn("GNU timeout or gtimeout is required", process.stderr)
        self.assertFalse((self.tmp / "docker-calls").exists())

    def test_gtimeout_is_used_when_timeout_is_unavailable(self):
        timer = shutil.which("timeout") or shutil.which("gtimeout")
        self.assertIsNotNone(timer, "tests require GNU coreutils timeout")
        for name in ("timeout", "gtimeout"):
            (self.bin / name).unlink(missing_ok=True)
        (self.bin / "gtimeout").symlink_to(timer)
        process = self.run_probe("--timeout", "1")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["checks"]["docker"]["status"], "ok")

    def test_hung_probe_is_killed_even_if_it_ignores_termination(self):
        (self.bin / "docker").write_text("#!/bin/sh\ntrap '' TERM\nexec sleep 30\n")
        process = self.run_probe("--timeout", "1")
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)["checks"]["docker"]
        self.assertEqual(report["status"], "failed")
        self.assertIn("command timed out", report["detail"])

    def test_storage_probe_is_bounded_and_reported_as_unknown_on_timeout(self):
        # Replace the symlink, never write through it into the host df binary.
        (self.bin / "df").unlink()
        (self.bin / "df").write_text("#!/bin/sh\nexec sleep 30\n")
        (self.bin / "df").chmod(0o755)
        process = self.run_probe("--timeout", "1", "--path", str(self.tmp))
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["storage"][0]["status"], "failed")
        self.assertIn("command timed out", report["storage"][0]["detail"])
        self.assertTrue(any("Storage probe failed" in q for q in report["open_questions"]))

    def test_timeout_cannot_be_disabled_or_set_to_an_invalid_value(self):
        for value in ("0", "000", "-1", "abc"):
            with self.subTest(value=value):
                process = self.run_probe("--timeout", value)
                self.assertEqual(process.returncode, 2)
                self.assertFalse((self.tmp / "docker-calls").exists())

    def test_legacy_python_entry_point_preserves_report_arguments_and_exit_status(self):
        process = self.run_probe("--path", str(self.tmp), legacy=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["checks"]["docker"]["status"], "ok")
        self.assertEqual(report["storage"][0]["path"], str(self.tmp))
        self.assertEqual(self.container_calls(), [])
        invalid = self.run_probe("--timeout", "0", legacy=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("must be greater than zero", invalid.stderr)
        (self.bin / "bash").unlink()
        unavailable = self.run_probe(legacy=True)
        self.assertEqual(unavailable.returncode, 2)
        self.assertIn("Cannot start the Bash readiness helper", unavailable.stderr)
        self.assertNotIn("Traceback", unavailable.stderr)


if __name__ == "__main__":
    unittest.main()

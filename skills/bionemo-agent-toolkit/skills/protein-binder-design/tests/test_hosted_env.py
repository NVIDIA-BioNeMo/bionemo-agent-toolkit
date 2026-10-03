# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0
"""Check that delegated processes inherit the selected hosted credential."""
import os
import subprocess
import sys
import unittest
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "scripts" / "hosted_env.sh"


class HostedEnvironmentTests(unittest.TestCase):
    def run_child(self, keys, expected="", legacy=False):
        # Isolate from real credentials; these values are synthetic test inputs.
        env = {"PATH": os.defpath, **keys}
        child = [sys.executable, "-c",
                 "import os, sys; assert os.environ['NGC_API_KEY'] == sys.argv[1]; print('child-ran')",
                 expected]
        command = ["bash", str(HELPER), *child]
        if legacy:
            command = [
                "bash", "--noprofile", "--norc", "-c",
                'source "$1" && "$2" -c "$3" "$4"',
                "test-hosted-env", str(HELPER), sys.executable,
                "import os, sys; assert os.environ['NGC_API_KEY'] == sys.argv[1]; print('child-ran')",
                expected,
            ]
        return subprocess.run(
            command,
            env=env, text=True, capture_output=True,
        )

    def test_selected_key_reaches_delegated_process_without_logging(self):
        for keys, expected in (
            ({"NGC_API_KEY": "synthetic-ngc"}, "synthetic-ngc"),
            ({"NVIDIA_API_KEY": "synthetic-fallback"}, "synthetic-fallback"),
            ({"NGC_API_KEY": "", "NVIDIA_API_KEY": "synthetic-fallback"}, "synthetic-fallback"),
            ({"NGC_API_KEY": "synthetic-ngc", "NVIDIA_API_KEY": "synthetic-fallback"}, "synthetic-ngc"),
        ):
            with self.subTest(keys=sorted(keys)):
                result = self.run_child(keys, expected)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "child-ran\n")
                self.assertEqual(result.stderr, "")

    def test_missing_nim_key_stops_before_delegated_call(self):
        for keys in ({}, {"OPENAI_API_KEY": "synthetic-agent-key"}, {"NGC_API_KEY": "", "NVIDIA_API_KEY": ""}):
            with self.subTest(keys=sorted(keys)):
                result = self.run_child(keys)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("Set NGC_API_KEY or NVIDIA_API_KEY", result.stderr)
                self.assertNotIn("synthetic-agent-key", result.stderr)

    def test_legacy_source_still_exports_to_child(self):
        result = self.run_child({"NVIDIA_API_KEY": "synthetic-fallback"}, "synthetic-fallback", legacy=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrapper_preserves_arguments_and_failure_code_without_tracing_secret(self):
        result = subprocess.run(
            ["bash", "-x", str(HELPER), sys.executable, "-c",
             "import sys; assert sys.argv[1] == 'two words'; sys.exit(7)", "two words"],
            env={"PATH": os.defpath, "NVIDIA_API_KEY": "synthetic-secret"},
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 7)
        self.assertNotIn("synthetic-secret", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

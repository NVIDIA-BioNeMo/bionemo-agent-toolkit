#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Compatibility entry point for callers of the former Python readiness helper.

Usage:
    python3 scripts/check_parabricks_runtime.py [readiness options]
Arguments:
    Forwarded to and validated by the Bash helper; run with --help for options.
Output:
    The Bash helper's text or JSON report. Container probes remain opt-in.
Exit codes:
    0: report produced, including any readiness gaps.
    2: invalid arguments or missing helper dependencies.
    Other Bash exit statuses and signals are preserved.
"""

import os
from pathlib import Path
import sys


def main():
    script = Path(__file__).resolve().with_suffix(".sh")
    try:
        os.execvp("bash", ["bash", str(script), *sys.argv[1:]])
    except OSError as exc:
        print("Cannot start the Bash readiness helper: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

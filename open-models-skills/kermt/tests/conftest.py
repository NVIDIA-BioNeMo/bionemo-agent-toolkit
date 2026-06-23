# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Pytest configuration for agent/tests/.

Registers the `slow` marker for tests that take more than a few seconds (e.g.
end-to-end pretrain that actually launches pretrain_ddp.py). Slow tests are
SKIPPED by default; pass `--run-slow` to opt in:

    KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \\
        "python -m pytest agent/tests/ -v --run-slow"

Also exposes a `run_agent_script` fixture used by every test_*.py to shell
out to an agent/scripts/*.py and parse the JSON it emits to stdout. Before
this fixture existed, each test_*.py defined its own near-identical `_run()`
helper (D3 in the Phase-5.5 cleanup review).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "agent" / "scripts"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run @pytest.mark.slow tests (skipped by default). "
             "Used for the end-to-end pretrain smoke that exercises pretrain_ddp.py.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: marks tests that take more than a few seconds (deselect with default "
        "behavior; enable with --run-slow)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test; pass --run-slow to enable")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture
def run_agent_script():
    """Shell out to an agent/scripts/<name>.py and parse its JSON stdout.

    Usage:
        code, payload = run_agent_script("check_checkpoint.py",
                                         "--mode", "continue_pretrain",
                                         "--ckpt", str(ckpt_path))

    Returns (exit_code, parsed_json). If stdout is empty or unparseable,
    `payload` is a dict with `_no_json: True` + the raw stdout/stderr so
    failing tests can surface the actual error.

    Use this for any test that invokes a script via subprocess.run + json.loads —
    consistent error-on-no-stdout handling across all test files.
    """
    def _run(script_name: str, *args: str) -> tuple[int, dict[str, Any]]:
        script_path = SCRIPTS_DIR / script_name
        proc = subprocess.run(
            [sys.executable, str(script_path), *args],
            capture_output=True, text=True,
        )
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"_no_json": True, "_stdout": proc.stdout, "_stderr": proc.stderr}
        else:
            payload = {"_no_json": True, "_stdout": proc.stdout, "_stderr": proc.stderr}
        return proc.returncode, payload
    return _run

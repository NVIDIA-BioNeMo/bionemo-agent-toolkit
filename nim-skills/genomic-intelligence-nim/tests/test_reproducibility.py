"""Reproducibility replay guard for the Genomic Intelligence runner.

Regression target: ``reproducibility/command.sh`` must reproduce the original
invocation. It historically dropped ``--description`` (required by expression,
no default) and a non-default ``--model``, so replaying an expression job hit
the runner's own validation gate and exited 1.

All tests are offline (no network, no API key) except the one marked
``@pytest.mark.integration``, which replays ``command.sh`` against the live API
when ``GI_API_KEY`` is set. Run from the skill directory: ``pytest tests/``.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import gi_predict  # noqa: E402


def _reparse(cmd: str):
    """Tokenize a generated command and run it back through the runner's parser.

    This is the heart of the replay guard: if the generated command survives the
    runner's own argument parsing with the required flags intact, a real replay
    will pass the same pre-flight it originally passed.
    """
    argv = shlex.split(cmd)
    assert argv[:2] == ["python3", "scripts/gi_predict.py"], argv
    saved = sys.argv
    try:
        sys.argv = ["gi_predict.py"] + argv[2:]
        return gi_predict._parse_args()
    finally:
        sys.argv = saved


def test_expression_command_keeps_description():
    cmd = gi_predict._repro_command(
        "expression", Path("in.fa"), Path("out"), model=None, description="K562 cells"
    )
    ns = _reparse(cmd)
    assert ns.task == "expression"
    assert ns.description == "K562 cells", f"replay would fail the --description gate: {cmd}"


def test_command_keeps_nondefault_model():
    cmd = gi_predict._repro_command(
        "promoter", Path("in.fa"), Path("out"), model="g0-promoter-2000bp", description=None
    )
    assert _reparse(cmd).model == "g0-promoter-2000bp"


def test_command_omits_absent_flags():
    cmd = gi_predict._repro_command("promoter", Path("in.fa"), Path("out"))
    assert "--description" not in cmd and "--model" not in cmd


def test_command_uses_python3_and_quotes_spaces():
    cmd = gi_predict._repro_command(
        "expression", Path("a b.fa"), Path("out dir"), description="K562 cells"
    )
    assert cmd.startswith("python3 ")
    # spaces must be quoted so the replay tokenizes back to the same values
    ns = _reparse(cmd)
    assert ns.input_file == Path("a b.fa")
    assert ns.output == Path("out dir")
    assert ns.description == "K562 cells"


@pytest.mark.integration
def test_expression_bundle_replays_end_to_end(tmp_path):
    """Full round-trip against the live API: run expression, then replay the
    generated command.sh verbatim; both must exit 0. Requires GI_API_KEY."""
    if not os.environ.get("GI_API_KEY"):
        pytest.skip("GI_API_KEY not set")
    out = tmp_path / "expr"
    first = subprocess.run(
        [sys.executable, "scripts/gi_predict.py", "--task", "expression", "--demo",
         "--description", "K562 cells", "--output", str(out)],
        cwd=SKILL_DIR, capture_output=True, text=True, timeout=180,
    )
    assert first.returncode == 0, first.stderr
    command_sh = out / "reproducibility" / "command.sh"
    body = command_sh.read_text()
    # Ran without --model, so the default was used: the replay must NOT inject
    # --model (regression guard for the _write_report model-shadowing bug).
    assert "--description" in body, "expression replay must carry --description"
    assert "--model" not in body, "must not inject --model when the user relied on the default"
    replay = subprocess.run(
        ["bash", str(command_sh)], cwd=SKILL_DIR,
        capture_output=True, text=True, timeout=180,
    )
    assert replay.returncode == 0, f"replay failed: {replay.stderr}"

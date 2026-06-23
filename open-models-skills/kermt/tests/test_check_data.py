# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/check_data.py.

Mix of synthetic CSV fixtures (full control of edge cases) and a few real
fixtures under tests/data/ (sanity that the validator behaves correctly on
shapes that match what users actually have).

Run from the kermt repo root:
    pytest agent/tests/test_check_data.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "agent" / "scripts" / "check_data.py"


# Pre-canned real fixtures the test suite uses.
PRETRAIN_SHARD = REPO_ROOT / "tests" / "data" / "pretrain" / "train_9k" / "graph" / "0.csv"
FINETUNE_TRAIN = REPO_ROOT / "tests" / "data" / "finetune" / "train.csv"
BIOGEN_TRAIN = REPO_ROOT / "tests" / "data" / "Biogen_for_grover" / "scaffold" / "balance" / "HLM_RLM_MDCK_logS" / "train.csv"
CHEMBL_MT_TRAIN = REPO_ROOT / "tests" / "data" / "ChEMBL_MT" / "all_train_fold_0_cluster_morgan.csv"


def _run(csv_path: Path, mode: str, *extra: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", mode, "--csv", str(csv_path), *extra],
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc.returncode, payload


def _write_csv(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n")
    return p


# ---------------------------------------------------------------------------
# Synthetic positive cases — one per mode.
# ---------------------------------------------------------------------------

def test_pretrain_minimal_smiles_only(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "p.csv", ["smiles", "CCO", "c1ccccc1", "CC(=O)O"])
    code, out = _run(csv, "pretrain")
    assert code == 0, out
    assert out["ok"] is True
    assert out["smiles_column_name"] == "smiles"
    assert out["num_rows"] == 3
    assert out["num_invalid_smiles"] == 0
    assert out["target_columns"] == []  # not relevant for pretrain


def test_embed_smiles_only(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "e.csv", ["smiles", "CCO", "CCN"])
    code, out = _run(csv, "embed")
    assert code == 0, out
    assert out["ok"] is True


def test_inference_smiles_only(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "i.csv", ["smiles", "CCO", "CCN", "CCC"])
    code, out = _run(csv, "inference")
    assert code == 0, out
    assert out["ok"] is True


def test_finetune_with_explicit_target(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "f.csv", ["smiles,y_mean", "CCO,1.2", "CCN,2.3", "CCC,3.4"])
    code, out = _run(csv, "finetune", "--targets", "y_mean")
    assert code == 0, out
    assert out["ok"] is True
    assert out["target_columns"] == ["y_mean"]
    assert out["num_missing_per_target"] == {"y_mean": 0}


def test_finetune_autodetect_targets(tmp_path: Path) -> None:
    """Without --targets the validator surfaces numeric non-smiles columns as candidates."""
    csv = _write_csv(tmp_path, "f.csv", ["smiles,y_mean,notes", "CCO,1.2,foo", "CCN,2.3,bar"])
    code, out = _run(csv, "finetune")
    assert code == 0, out
    assert out["ok"] is True
    assert "y_mean" in out["auto_detected_targets"]
    assert "notes" not in out["auto_detected_targets"]
    assert any("auto-detected" in w for w in out["warnings"])


def test_finetune_multi_target(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "f.csv",
                     ["smiles,HLM,RLM,logS", "CCO,1,2,3", "CCN,4,5,6", "CCC,7,8,9"])
    code, out = _run(csv, "finetune", "--targets", "HLM", "RLM", "logS")
    assert code == 0, out
    assert out["target_columns"] == ["HLM", "RLM", "logS"]
    assert out["num_missing_per_target"] == {"HLM": 0, "RLM": 0, "logS": 0}


# ---------------------------------------------------------------------------
# Synthetic negative / edge cases.
# ---------------------------------------------------------------------------

def test_no_smiles_column(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "x.csv", ["compound,y", "foo,1.0", "bar,2.0"])
    code, out = _run(csv, "pretrain")
    assert code == 1
    assert out["ok"] is False
    assert out["has_smiles_column"] is False
    assert any("smiles" in e for e in out["errors"])


def test_uppercase_smiles_column_is_accepted_with_warning(tmp_path: Path) -> None:
    """Some Biogen fixtures use 'SMILES' (uppercase). Accept and warn — the rest
    of the codebase expects lowercase."""
    csv = _write_csv(tmp_path, "x.csv", ["SMILES,y_mean", "CCO,1.0", "CCN,2.0"])
    code, out = _run(csv, "finetune", "--targets", "y_mean")
    assert code == 0, out
    assert out["smiles_column_name"] == "SMILES"
    assert any("lowercase" in w for w in out["warnings"])


def test_finetune_missing_target_column(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "f.csv", ["smiles,y_mean", "CCO,1.0", "CCN,2.0"])
    code, out = _run(csv, "finetune", "--targets", "not_a_real_col")
    assert code == 1
    assert out["ok"] is False
    assert any("not_a_real_col" in e for e in out["errors"])


def test_invalid_smiles_in_sample_fails(tmp_path: Path) -> None:
    """If RDKit can't parse a sampled SMILES, surface it as an error."""
    csv = _write_csv(tmp_path, "x.csv", ["smiles", "CCO", "not_a_smiles_at_all", "CCN"])
    code, out = _run(csv, "pretrain")
    assert code == 1
    assert out["num_invalid_smiles"] >= 1


def test_blank_smiles_counted(tmp_path: Path) -> None:
    """Rows with an EXPLICITLY empty SMILES cell (still parseable CSV row)
    should be counted. Pandas drops blank lines silently by default, so this
    only fires for the empty-cell case, which is the realistic one (rows with
    a missing SMILES alongside other populated cells)."""
    csv = _write_csv(
        tmp_path, "x.csv",
        ["smiles,note", "CCO,a", ",blank-smiles-cell", "CCN,b", ",another-blank"],
    )
    code, out = _run(csv, "pretrain")
    assert out["num_blank_smiles"] == 2
    assert out["num_invalid_smiles"] == 0
    assert out["ok"] is True


def test_duplicate_smiles_counted(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "x.csv", ["smiles", "CCO", "CCN", "CCO", "CCO"])
    code, out = _run(csv, "pretrain")
    assert out["num_duplicate_smiles"] == 2  # CCO appears 3x -> 2 duplicates
    assert out["ok"] is True


def test_pretrain_small_corpus_warning(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path, "p.csv", ["smiles"] + ["CCO"] * 5)
    code, out = _run(csv, "pretrain")
    assert out["ok"] is True
    assert any("pretrain corpus is only" in w for w in out["warnings"])


def test_missing_csv_file(tmp_path: Path) -> None:
    code, out = _run(tmp_path / "does_not_exist.csv", "pretrain")
    assert code == 1
    assert any("not found" in e for e in out["errors"])


def test_empty_csv(tmp_path: Path) -> None:
    p = tmp_path / "empty.csv"
    p.write_text("")
    code, out = _run(p, "pretrain")
    assert code == 1
    assert any("empty" in e.lower() for e in out["errors"])


def test_strict_rdkit_runs_full(tmp_path: Path) -> None:
    """--strict-rdkit should report check method 'full' and parse every SMILES."""
    rows = ["smiles"] + ["CCO"] * 50 + ["CCN"] * 50
    csv = _write_csv(tmp_path, "p.csv", rows)
    code, out = _run(csv, "pretrain", "--strict-rdkit")
    assert out["ok"] is True
    assert out["smiles_check_method"] == "full"
    assert out["smiles_check_count"] == 100


def test_sampled_default_runs_partial(tmp_path: Path) -> None:
    rows = ["smiles"] + ["CCO"] * 100
    csv = _write_csv(tmp_path, "p.csv", rows)
    code, out = _run(csv, "pretrain")
    assert out["smiles_check_method"] == "sampled"
    assert out["smiles_check_count"] == 20  # 10 head + 10 tail by design


# ---------------------------------------------------------------------------
# Real-fixture integration tests.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PRETRAIN_SHARD.is_file(), reason="pretrain shard fixture not present")
def test_real_pretrain_shard_passes() -> None:
    code, out = _run(PRETRAIN_SHARD, "pretrain")
    assert code == 0, out
    assert out["ok"] is True
    assert out["smiles_column_name"] == "smiles"
    assert out["num_invalid_smiles"] == 0
    assert out["num_rows"] > 0


@pytest.mark.skipif(not FINETUNE_TRAIN.is_file(), reason="finetune fixture not present")
def test_real_finetune_train_y_mean_explicit_and_autodetect() -> None:
    """Both code paths on the same fixture: explicit --targets y_mean must
    produce target_columns=['y_mean'] with no missing values, and the no-flag
    invocation must surface y_mean via auto_detected_targets."""
    code, out = _run(FINETUNE_TRAIN, "finetune", "--targets", "y_mean")
    assert code == 0, out
    assert out["target_columns"] == ["y_mean"]
    assert out["num_missing_per_target"]["y_mean"] == 0

    code, out = _run(FINETUNE_TRAIN, "finetune")
    assert code == 0, out
    assert "y_mean" in out["auto_detected_targets"]


@pytest.mark.skipif(not BIOGEN_TRAIN.is_file(), reason="Biogen fixture not present")
def test_real_biogen_hlm_rlm_mdck_logs_autodetect() -> None:
    """Auto-detection on the real Biogen HLM_RLM_MDCK_logS train CSV should
    surface all four target columns (note the _CLint suffix on HLM/RLM)."""
    code, out = _run(BIOGEN_TRAIN, "finetune")
    assert code == 0, out
    auto = set(out["auto_detected_targets"])
    expected = {"HLM_CLint_mean", "RLM_CLint_mean", "MDCK_mean", "logS_mean"}
    assert expected.issubset(auto), f"expected {expected} subset of {auto}"


@pytest.mark.skipif(not CHEMBL_MT_TRAIN.is_file(), reason="ChEMBL_MT fixture not present")
def test_real_chembl_mt_autodetects_many_targets() -> None:
    """ChEMBL-MT has 25 target columns with sparse coverage. Auto-detect should
    still find them (those with >=80% numeric non-null values).
    Note: many columns are mostly NaN, so we just assert at least a few are detected."""
    code, out = _run(CHEMBL_MT_TRAIN, "finetune")
    assert code == 0, out
    assert len(out["auto_detected_targets"]) >= 5, out["auto_detected_targets"]

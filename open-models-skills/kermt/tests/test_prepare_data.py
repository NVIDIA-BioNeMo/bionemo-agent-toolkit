# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/prepare_data.py.

Runs the prepare_data CLI as a subprocess (the same way the agent skills will
invoke it), inspects the produced manifest + output files, and asserts the
per-mode contracts.

Designed to run in-container via:
    KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \
        "python -m pytest agent/tests/test_prepare_data.py -v --no-header -p no:cacheprovider"

The tests use small synthetic CSVs (50-100 SMILES) so feature generation
finishes quickly. Total in-container runtime ≈ 1-2 minutes (vocab build +
save_features are the slow steps).
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "agent" / "scripts" / "prepare_data.py"


# A small pool of valid drug-like SMILES used to build synthetic CSVs.
VALID_SMILES_POOL = [
    "CCO", "CCN", "CCC", "c1ccccc1", "c1ccncc1", "CC(=O)O", "CC(C)O",
    "CCOC(=O)C", "CC(=O)Nc1ccccc1", "Nc1ccccc1", "OC(=O)c1ccccc1", "CC(C)C",
    "CCCCO", "CCCCN", "c1ccc2ccccc2c1", "CCNC(=O)C", "CC(C)(C)O",
    "CCS", "CN(C)C", "CC(=O)C", "C1CCCCC1", "C1CCNCC1", "OCC(=O)O",
    "Nc1ncccn1", "Cc1ccccn1", "Cc1ccncc1", "CCc1ccccc1", "Clc1ccccc1",
    "Brc1ccccc1", "Fc1ccccc1", "CC(=O)OC", "CCCCC", "CCCCCC", "OCC",
    "OCN", "CCOC", "CCCN", "CCCO", "CCCS", "OCC(C)O", "CC(N)C",
    "Cc1ccc(O)cc1", "Cc1ccc(N)cc1", "OC(=O)CC", "CC(=O)N", "CC#N",
    "CC=O", "CC=C", "C=C", "C#C",
]


def _write_pretrain_csv(path: Path, n: int) -> None:
    """Write a pretrain-shaped CSV: one 'smiles' column, n rows."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["smiles"])
        for i in range(n):
            w.writerow([VALID_SMILES_POOL[i % len(VALID_SMILES_POOL)]])


def _write_finetune_csv(path: Path, n: int) -> None:
    """Write a finetune-shaped CSV: smiles + y_mean."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["smiles", "y_mean"])
        for i in range(n):
            w.writerow([VALID_SMILES_POOL[i % len(VALID_SMILES_POOL)], float(i) / n])


def _run(out_dir: Path, *args: str) -> tuple[int, dict]:
    """Invoke prepare_data.py via subprocess. Returns (exit_code, manifest)."""
    cmd = [sys.executable, str(SCRIPT), "--out", str(out_dir), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    manifest_path = out_dir / "prepare_data.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
    else:
        # Surface a useful error if the manifest wasn't written at all.
        manifest = {"_no_manifest": True, "_stderr": proc.stderr, "_stdout": proc.stdout}
    return proc.returncode, manifest


# ---------------------------------------------------------------------------
# embed mode — simplest path
# ---------------------------------------------------------------------------

def test_embed_mode_minimal(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=20)
    code, m = _run(tmp_path / "out", "--mode", "embed", "--csv", str(csv))
    assert code == 0, m
    assert m["ok"] is True
    assert m["split_method"] == "n/a"
    assert Path(m["outputs"]["clean_csv"]).is_file()
    # embed should NOT have produced features
    assert "clean_npz" not in m["outputs"]


def test_embed_mode_skip_clean(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=10)
    code, m = _run(tmp_path / "out", "--mode", "embed", "--csv", str(csv), "--skip-clean")
    assert code == 0, m
    # The clean step shows up as skipped_by_flag, output points back to the original CSV
    skipped = [s for s in m["steps"] if s.get("skipped_by_flag")]
    assert any(s.get("name") == "clean_smiles" for s in skipped)


# ---------------------------------------------------------------------------
# inference mode
# ---------------------------------------------------------------------------

def test_inference_mode_full(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=20)
    code, m = _run(tmp_path / "out", "--mode", "inference", "--csv", str(csv))
    assert code == 0, m
    assert m["ok"] is True
    assert m["split_method"] == "n/a"
    assert Path(m["outputs"]["clean_csv"]).is_file()
    assert Path(m["outputs"]["clean_npz"]).is_file()
    # save_features step should record the rdkit_2d_normalized generator
    feature_steps = [s for s in m["steps"] if "save_features" in s.get("name", "")]
    assert any("rdkit_2d_normalized" in str(s.get("cmd", "")) for s in feature_steps)


def test_inference_mode_skip_features(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=10)
    code, m = _run(tmp_path / "out", "--mode", "inference", "--csv", str(csv), "--skip-features")
    assert code == 0, m
    assert Path(m["outputs"]["clean_csv"]).is_file()
    assert "clean_npz" not in m["outputs"]


# ---------------------------------------------------------------------------
# finetune mode
# ---------------------------------------------------------------------------

def test_finetune_user_provided_splits(tmp_path: Path) -> None:
    """When --val-csv and --test-csv are both provided, no auto-split happens
    and no warning is emitted."""
    train = tmp_path / "train.csv"
    val = tmp_path / "val.csv"
    test = tmp_path / "test.csv"
    _write_finetune_csv(train, n=30)
    _write_finetune_csv(val, n=10)
    _write_finetune_csv(test, n=10)
    code, m = _run(
        tmp_path / "out", "--mode", "finetune",
        "--csv", str(train), "--val-csv", str(val), "--test-csv", str(test),
        "--targets", "y_mean",
    )
    assert code == 0, m
    assert m["split_method"] == "user_provided"
    assert m["warnings"] == []  # no auto-split warning
    for k in ("clean_train_csv", "clean_val_csv", "clean_test_csv",
              "clean_train_npz", "clean_val_npz", "clean_test_npz"):
        assert Path(m["outputs"][k]).is_file(), f"missing {k}"
    assert m["targets"] == ["y_mean"]


def test_finetune_auto_split_emits_warning(tmp_path: Path) -> None:
    csv = tmp_path / "all.csv"
    _write_finetune_csv(csv, n=50)
    code, m = _run(
        tmp_path / "out", "--mode", "finetune", "--csv", str(csv),
        "--targets", "y_mean",
    )
    assert code == 0, m
    assert m["split_method"] == "random"
    assert m["split_fractions"] == {"train": 0.8, "val": 0.1, "test": 0.1}
    assert m["split_seed"] == 0
    # Warning text mentions RANDOM and points the user at the proper override.
    assert len(m["warnings"]) == 1
    w = m["warnings"][0]
    assert "RANDOM" in w and "--train-csv" in w and "scaffold-balanced" in w
    # 80/10/10 of 50 rows = 40/5/5
    random_split_step = [s for s in m["steps"] if "random_split" in s.get("name", "")][0]
    assert random_split_step["row_counts"] == {"train": 40, "val": 5, "test": 5}


def test_finetune_deferred_split_scaffold_balanced(tmp_path: Path) -> None:
    """--split-type scaffold_balanced (no val/test CSVs given) defers the
    actual split to the runner: prep cleans + featurizes a single full CSV."""
    csv = tmp_path / "all.csv"
    _write_finetune_csv(csv, n=40)
    code, m = _run(
        tmp_path / "out", "--mode", "finetune", "--csv", str(csv),
        "--targets", "y_mean", "--split-type", "scaffold_balanced",
    )
    assert code == 0, m
    assert m["split_method"] == "deferred_to_runner"
    assert m["split_type"] == "scaffold_balanced"
    # Single full CSV + features, NO train/val/test pre-splits.
    outputs = m["outputs"]
    assert "clean_full_csv" in outputs
    assert "clean_full_npz" in outputs
    assert "clean_train_csv" not in outputs
    assert "clean_val_csv" not in outputs
    assert "clean_test_csv" not in outputs
    # No random-split step (the runner handles splitting).
    assert not any(s.get("name", "").startswith("random_split") for s in m["steps"])


def test_finetune_deferred_split_index_predetermined(tmp_path: Path) -> None:
    """--split-type index_predetermined is the other deferred-to-runner choice."""
    csv = tmp_path / "all.csv"
    _write_finetune_csv(csv, n=20)
    code, m = _run(
        tmp_path / "out", "--mode", "finetune", "--csv", str(csv),
        "--targets", "y_mean", "--split-type", "index_predetermined",
    )
    assert code == 0, m
    assert m["split_method"] == "deferred_to_runner"
    assert m["split_type"] == "index_predetermined"
    assert "clean_full_csv" in m["outputs"]


def test_finetune_partial_separate_paths_rejected(tmp_path: Path) -> None:
    """Providing --val-csv but not --test-csv (or vice versa) is rejected."""
    train = tmp_path / "train.csv"
    val = tmp_path / "val.csv"
    _write_finetune_csv(train, n=20)
    _write_finetune_csv(val, n=10)
    code, m = _run(
        tmp_path / "out", "--mode", "finetune",
        "--csv", str(train), "--val-csv", str(val),
        "--targets", "y_mean",
    )
    assert code == 1, m
    assert any("BOTH --val-csv and --test-csv" in e for e in m["errors"])


# ---------------------------------------------------------------------------
# pretrain mode
# ---------------------------------------------------------------------------

def test_pretrain_user_provided_val(tmp_path: Path) -> None:
    train = tmp_path / "train.csv"
    val = tmp_path / "val.csv"
    _write_pretrain_csv(train, n=80)
    _write_pretrain_csv(val, n=20)
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(train), "--val-csv", str(val),
        "--sample-per-file", "50",   # force >1 shard so split_data is exercised
    )
    assert code == 0, m
    assert m["split_method"] == "user_provided"
    for k in ("clean_train_csv", "clean_val_csv",
              "clean_train_npz", "clean_val_npz",
              "atom_vocab", "bond_vocab", "smiles_vocab",
              "train_dir", "val_dir"):
        assert Path(m["outputs"][k]).exists(), f"missing {k}"
    # Vocab files follow the --dataset-name pretrain convention.
    assert m["outputs"]["atom_vocab"].endswith("pretrain_atom_vocab.json")
    assert m["outputs"]["bond_vocab"].endswith("pretrain_bond_vocab.json")
    assert m["outputs"]["smiles_vocab"].endswith("pretrain_smiles_vocab.pkl")
    # Shard dirs have summary.txt + graph/ + feature/
    train_dir = Path(m["outputs"]["train_dir"])
    assert (train_dir / "summary.txt").is_file()
    assert (train_dir / "graph").is_dir()
    assert (train_dir / "feature").is_dir()
    assert len(list((train_dir / "graph").glob("*.csv"))) >= 1


def test_pretrain_auto_split_single_csv(tmp_path: Path) -> None:
    csv = tmp_path / "all.csv"
    _write_pretrain_csv(csv, n=100)
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(csv), "--val-frac", "0.2",
        "--sample-per-file", "50",
    )
    assert code == 0, m
    assert m["split_method"] == "random"
    assert m["split_fractions"] == {"train": 0.8, "val": 0.2}
    rs = [s for s in m["steps"] if "random_split" in s.get("name", "")][0]
    assert rs["row_counts"] == {"train": 80, "val": 20}


def test_pretrain_skip_features_for_cmim(tmp_path: Path) -> None:
    """--skip-features is the CMIM-only opt-out: vocabs and shards still produced,
    just no feature shards."""
    train = tmp_path / "train.csv"
    val = tmp_path / "val.csv"
    _write_pretrain_csv(train, n=60)
    _write_pretrain_csv(val, n=20)
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(train), "--val-csv", str(val),
        "--skip-features",
        "--sample-per-file", "50",
    )
    assert code == 0, m
    assert "clean_train_npz" not in m["outputs"]
    train_dir = Path(m["outputs"]["train_dir"])
    assert (train_dir / "graph").is_dir()
    assert not (train_dir / "feature").exists()


# ---------------------------------------------------------------------------
# Idempotency: re-running on the same out dir skips existing steps
# ---------------------------------------------------------------------------

def test_idempotent_rerun_skips_existing(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=20)
    out = tmp_path / "out"
    code1, m1 = _run(out, "--mode", "inference", "--csv", str(csv))
    assert code1 == 0
    code2, m2 = _run(out, "--mode", "inference", "--csv", str(csv))
    assert code2 == 0
    # Second run should record every step as skipped_due_to_existing.
    skipped = [s for s in m2["steps"] if s.get("skipped_due_to_existing")]
    assert len(skipped) >= 2, m2["steps"]


def test_force_rerun_redoes_existing(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=20)
    out = tmp_path / "out"
    code1, _ = _run(out, "--mode", "inference", "--csv", str(csv))
    assert code1 == 0
    code2, m2 = _run(out, "--mode", "inference", "--csv", str(csv), "--force")
    assert code2 == 0
    # With --force, no step should be skipped_due_to_existing.
    skipped_existing = [s for s in m2["steps"] if s.get("skipped_due_to_existing")]
    assert skipped_existing == []


# ---------------------------------------------------------------------------
# Error path: missing input
# ---------------------------------------------------------------------------

def test_missing_input_csv_produces_clean_error(tmp_path: Path) -> None:
    code, m = _run(
        tmp_path / "out", "--mode", "embed",
        "--csv", str(tmp_path / "does_not_exist.csv"),
    )
    assert code == 1
    # Either the underlying clean_smiles step fails OR our wrapper does — both
    # surface as manifest.errors[].
    assert m.get("errors"), m


# ---------------------------------------------------------------------------
# Vocab pass-through (continue-pretrain hardening)
# ---------------------------------------------------------------------------

def _seed_vocab_dir(d: Path) -> None:
    """Copy the existing test-fixture vocab files into <d> with the conventional
    'pretrain_*_vocab.{json,pkl}' names."""
    import shutil
    d.mkdir(parents=True, exist_ok=True)
    fixture = REPO_ROOT / "tests" / "data" / "pretrain"
    for fname in ("pretrain_atom_vocab.json", "pretrain_bond_vocab.json"):
        shutil.copy2(fixture / fname, d / fname)


def test_pretrain_vocab_dir_passthrough(tmp_path: Path) -> None:
    """--vocab-dir <d> copies the user's vocab files into the output dir
    under the conventional pretrain_*_vocab.{json,pkl} names; vocab_source
    is recorded as 'user_provided'."""
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=30)
    vocab_dir = tmp_path / "vocab"
    _seed_vocab_dir(vocab_dir)
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(csv),
        "--vocab-dir", str(vocab_dir),
        "--sample-per-file", "50",
    )
    assert code == 0, m
    assert m["vocab_source"] == "user_provided"
    assert Path(m["outputs"]["atom_vocab"]).is_file()
    assert Path(m["outputs"]["bond_vocab"]).is_file()
    # No build_vocab step in the manifest; only copy_vocab steps.
    step_names = [s.get("name", "") for s in m["steps"]]
    assert not any(s.startswith("build_vocab") for s in step_names), step_names
    assert any(s.startswith("copy_vocab") for s in step_names), step_names


def test_pretrain_vocab_passthrough_via_explicit_flags(tmp_path: Path) -> None:
    """--atom-vocab + --bond-vocab work directly without --vocab-dir."""
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=30)
    fixture = REPO_ROOT / "tests" / "data" / "pretrain"
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(csv),
        "--atom-vocab", str(fixture / "pretrain_atom_vocab.json"),
        "--bond-vocab", str(fixture / "pretrain_bond_vocab.json"),
        "--sample-per-file", "50",
    )
    assert code == 0, m
    assert m["vocab_source"] == "user_provided"


def test_pretrain_vocab_unpaired_flags_rejected(tmp_path: Path) -> None:
    """--atom-vocab without --bond-vocab is rejected (and vice versa)."""
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=20)
    fixture = REPO_ROOT / "tests" / "data" / "pretrain"
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(csv),
        "--atom-vocab", str(fixture / "pretrain_atom_vocab.json"),
        "--sample-per-file", "50",
    )
    assert code == 1
    assert any("paired" in e for e in m["errors"])


def test_pretrain_no_vocab_flag_falls_through_to_build(tmp_path: Path) -> None:
    """Without any vocab flag, prepare_data builds the vocab from corpus
    (existing behavior). vocab_source = 'built_fresh'."""
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=30)
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(csv),
        "--sample-per-file", "50",
    )
    assert code == 0, m
    assert m["vocab_source"] == "built_fresh"
    step_names = [s.get("name", "") for s in m["steps"]]
    assert any(s.startswith("build_vocab") for s in step_names), step_names


def test_pretrain_vocab_dir_missing_files_errors(tmp_path: Path) -> None:
    """--vocab-dir pointing at an empty directory is rejected with a clear msg."""
    csv = tmp_path / "in.csv"
    _write_pretrain_csv(csv, n=20)
    empty_dir = tmp_path / "empty_vocab"
    empty_dir.mkdir()
    code, m = _run(
        tmp_path / "out", "--mode", "pretrain",
        "--csv", str(csv),
        "--vocab-dir", str(empty_dir),
        "--sample-per-file", "50",
    )
    assert code == 1
    assert any("pretrain_" in e for e in m["errors"])

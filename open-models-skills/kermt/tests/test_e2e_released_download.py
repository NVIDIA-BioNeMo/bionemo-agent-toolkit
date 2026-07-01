# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Opt-in end-to-end tests for the released-model download path.

These perform a REAL Hugging Face download (~282 MB) of nvidia/NV-KERMT-70M-v2
and then drive each applicable downstream workflow (embed / finetune /
continue-pretrain) from the downloaded bundle. They are marked `slow` and are
SKIPPED by default; opt in with `--run-slow`, and run inside the kermt
container (which, after a `kermt-setup` rebuild, ships huggingface_hub):

    agent/scripts/kermt_container.sh run --run-dir /tmp/e2e -- \\
        "python -m pytest agent/tests/test_e2e_released_download.py -v --run-slow"

The bundle is downloaded ONCE per session (module-scoped fixture); the
idempotent fetch means re-runs don't re-download. If the download can't run
(no huggingface_hub / no network), the whole module is skipped.

The downstream invocations mirror the existing real-ckpt slow tests in
test_run_extract_embeddings.py / test_run_pretrain_local.py — the only change
is that the checkpoint comes from the HF bundle rather than a local model/ dir.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "agent" / "scripts"
CKPT_NAME = "kermt_contrastive_v2.0.pt"

FINETUNE_CSV = REPO_ROOT / "tests" / "data" / "finetune" / "train.csv"
EMBED_CSV = REPO_ROOT / "tests" / "data" / "finetune" / "test.csv"
PRETRAIN_TRAIN = REPO_ROOT / "tests" / "data" / "pretrain" / "train.csv"
PRETRAIN_VAL = REPO_ROOT / "tests" / "data" / "pretrain" / "val.csv"

pytestmark = pytest.mark.slow


def _run_script(name: str, *args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / name), *args],
        capture_output=True,
        text=True,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = {"_no_json": True, "_stdout": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, out


@pytest.fixture(scope="module")
def released_bundle(tmp_path_factory) -> dict:
    """Download the released bundle once. Skips the module if the download
    can't run (huggingface_hub missing -> stale image, or no network)."""
    out = tmp_path_factory.mktemp("released_model")
    code, manifest = _run_script("fetch_released_model.py", "--out", str(out))
    if not manifest.get("ok"):
        pytest.skip(
            f"released-model download unavailable (exit {code}): "
            f"{manifest.get('errors') or manifest}"
        )
    return manifest


def test_download_bundle_is_hybrid(released_bundle):
    """The downloaded bundle is complete and classifies as a hybrid pretrain
    checkpoint (the contract every downstream skill relies on)."""
    bundle_dir = Path(released_bundle["vocab_dir"])
    ckpt = Path(released_bundle["ckpt"])
    assert ckpt.is_file()
    for vocab in (
        "pretrain_atom_vocab.json",
        "pretrain_bond_vocab.json",
        "pretrain_smiles_vocab.pkl",
    ):
        assert (bundle_dir / vocab).is_file(), f"missing bundled vocab: {vocab}"

    code, info = _run_script(
        "check_checkpoint.py", "--mode", "embed", "--ckpt", str(ckpt)
    )
    assert code == 0, info
    assert info["model_type"] == "hybrid", info
    assert info["has_task_ffn"] is False  # pretrain ckpt, not finetuned


def test_download_then_embed(released_bundle, tmp_path):
    """Bundle -> embed: extract the 4 readouts (mirrors the grover_base embed
    slow test, swapping in the downloaded hybrid ckpt)."""
    if not EMBED_CSV.is_file():
        pytest.skip(f"embed fixture CSV not found at {EMBED_CSV}")
    out_dir = tmp_path / "run"
    data_dir = out_dir / "data"
    code, _ = _run_script(
        "prepare_data.py",
        "--mode",
        "embed",
        "--csv",
        str(EMBED_CSV),
        "--out",
        str(data_dir),
    )
    assert code == 0
    code, m = _run_script(
        "run_extract_embeddings.py",
        "--ckpt",
        released_bundle["ckpt"],
        "--prepare-manifest",
        str(data_dir / "prepare_data.json"),
        "--out",
        str(out_dir),
        "--batch-size",
        "16",
    )
    assert code == 0, m
    assert m["manifest"]["status"] == "ok"
    assert m["manifest"]["model_type"] == "hybrid"
    output_dir = Path(m["manifest"]["output_dir"])
    expected = {
        "atom_from_atom.npy",
        "bond_from_atom.npy",
        "atom_from_bond.npy",
        "bond_from_bond.npy",
    }
    assert expected.issubset({p.name for p in output_dir.glob("*.npy")})


def test_download_then_finetune(released_bundle, tmp_path):
    """Bundle -> finetune (1 epoch, single regression target y_mean) -> a
    held-out test_result.csv lands."""
    if not FINETUNE_CSV.is_file():
        pytest.skip(f"finetune fixture CSV not found at {FINETUNE_CSV}")
    out_dir = tmp_path / "run"
    data_dir = out_dir / "data"
    code, prep = _run_script(
        "prepare_data.py",
        "--mode",
        "finetune",
        "--csv",
        str(FINETUNE_CSV),
        "--out",
        str(data_dir),
        "--split-type",
        "random",
        "--targets",
        "y_mean",
    )
    assert code == 0, prep
    code, m = _run_script(
        "run_finetune_local.py",
        "--ckpt",
        released_bundle["ckpt"],
        "--prepare-manifest",
        str(data_dir / "prepare_data.json"),
        "--dataset-type",
        "regression",
        "--out",
        str(out_dir),
        "--gpus",
        "0",
        "--epochs",
        "1",
    )
    assert code == 0, m
    assert m["manifest"]["status"] == "ok", m["manifest"]
    test_result = out_dir / "ckpt" / "fold_0" / "test_result.csv"
    assert test_result.is_file(), f"expected held-out predictions at {test_result}"


def test_download_then_continue_pretrain(released_bundle, tmp_path):
    """Bundle -> continue-pretrain (1 epoch) using the bundle's own vocab files
    as the authoritative vocab (the released-bundle pass-through path)."""
    if not PRETRAIN_TRAIN.is_file():
        pytest.skip(f"pretrain fixture not found at {PRETRAIN_TRAIN}")
    bundle_dir = released_bundle["vocab_dir"]
    out_dir = tmp_path / "run"
    data_dir = out_dir / "data"
    prep_args = [
        "prepare_data.py",
        "--mode",
        "pretrain",
        "--csv",
        str(PRETRAIN_TRAIN),
        "--out",
        str(data_dir),
        "--vocab-dir",
        bundle_dir,
    ]
    if PRETRAIN_VAL.is_file():
        prep_args += ["--val-csv", str(PRETRAIN_VAL)]
    code, prep = _run_script(*prep_args)
    assert code == 0, prep
    assert prep.get("vocab_source") == "user_provided", prep

    code, m = _run_script(
        "run_pretrain_local.py",
        "--ckpt",
        released_bundle["ckpt"],
        "--prepare-manifest",
        str(data_dir / "prepare_data.json"),
        "--out",
        str(out_dir),
        "--gpus",
        "0",
        "--epochs",
        "1",
        "--warmup-epochs",
        "0",
        "--save-interval",
        "100",
        "--batch-size",
        "32",
    )
    assert code == 0, m
    assert m["manifest"]["status"] == "ok", m["manifest"]
    final_ckpt = out_dir / "ckpt" / "last_checkpoint.pt"
    assert final_ckpt.is_file()

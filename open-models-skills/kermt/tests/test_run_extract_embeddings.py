# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/run_extract_embeddings.py.

Exercises the argv builder + manifest writer via --dry-run, using cached
check_checkpoint.py JSON + a synthesized prepare_data.json (mode=embed).

Run in-container:
    KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \\
        "python -m pytest agent/tests/test_run_extract_embeddings.py -v \\
            --no-header -p no:cacheprovider"
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "agent" / "scripts" / "run_extract_embeddings.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_validator_out(*, model_type: str = "hybrid", has_encoder: bool = True) -> dict:
    """Synthetic check_checkpoint.py --mode embed output."""
    return {
        "ok": has_encoder,
        "model_type": model_type if has_encoder else "unknown",
        "has_encoder": has_encoder,
        "has_vocab_head": model_type in ("grover_base", "hybrid"),
        "has_contrast_head": model_type in ("cmim", "hybrid"),
        "has_task_ffn": model_type == "finetuned",
        "task_output_dims": [4] if model_type == "finetuned" else [],
        "vocab_sizes": {"atom": None, "bond": None, "smiles": None},
        "arch": {
            "hidden_size": 800, "depth": 6, "num_attn_head": 4,
            "activation": "PReLU", "backbone": "gtrans",
            "embedding_output_type": "both", "self_attention": False,
            "attn_hidden": None, "attn_out": None,
        },
        "saved_args": {},
        "errors": [] if has_encoder else ["checkpoint has no encoder weights"],
        "warnings": [],
    }


def _make_prepare_manifest(out_dir: Path, skip_clean: bool = False) -> Path:
    data = out_dir / "data"
    data.mkdir(parents=True, exist_ok=True)
    clean_csv = data / "clean.csv"
    clean_csv.write_text("smiles\nCCO\nc1ccccc1\n")
    manifest = {
        "ok": True,
        "mode": "embed",
        "input_csv": str(out_dir / "in.csv"),
        "val_csv": None,
        "test_csv": None,
        "output_dir": str(data),
        "split_method": "n/a",
        "steps": [
            {"name": "clean_smiles" if not skip_clean else "clean_smiles(skipped)",
             "ok": True, "skipped_by_flag": skip_clean},
        ],
        "outputs": {"clean_csv": str(clean_csv)},
        "errors": [],
        "warnings": [],
    }
    mpath = data / "prepare_data.json"
    mpath.write_text(json.dumps(manifest, indent=2))
    return mpath


def _setup(tmp_path: Path, *, model_type: str = "hybrid", has_encoder: bool = True
           ) -> tuple[Path, Path, Path]:
    ckpt = tmp_path / "dummy.pt"
    ckpt.write_bytes(b"\x00")
    prep = _make_prepare_manifest(tmp_path)
    val = _make_validator_out(model_type=model_type, has_encoder=has_encoder)
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val, indent=2))
    return ckpt, prep, val_path


def _run(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = {"_no_json": True, "_stdout": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, out


# ---------------------------------------------------------------------------
# Dispatch — every model_type with an encoder is accepted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_type", ["grover_base", "cmim", "hybrid", "finetuned"])
def test_dispatch_accepts_every_encoder_bearing_type(tmp_path: Path, model_type: str) -> None:
    ckpt, prep, val = _setup(tmp_path, model_type=model_type)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / f"run_{model_type}"),
        "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["workflow"] == "embed"
    assert manifest["model_type"] == model_type
    argv = manifest["argv"]
    # task/extract_embeddings.py, NOT main.py
    assert "extract_embeddings.py" in argv[2]
    assert "--checkpoint" in argv
    assert "--input_file" in argv
    assert "--output_path" in argv


def test_rejects_encoder_less_ckpt(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, has_encoder=False)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 1
    err_blob = " ".join(m["errors"])
    assert "no encoder" in err_blob or "rejected the input ckpt" in err_blob


# ---------------------------------------------------------------------------
# argv shape guards
# ---------------------------------------------------------------------------

def test_argv_omits_format_flag(tmp_path: Path) -> None:
    """The skill always uses task/extract_embeddings.py's default --format npy
    (4 separate .npy files), so the argv must NOT carry a --format flag."""
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 0, m
    assert "--format" not in m["manifest"]["argv"]


def test_argv_omits_projection_flags(tmp_path: Path) -> None:
    """The skill writes only the 4 encoder readouts — no projected.npy — so
    the argv must NOT carry --projection or --projection_only."""
    ckpt, prep, val = _setup(tmp_path, model_type="hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert "--projection" not in argv
    assert "--projection_only" not in argv


# ---------------------------------------------------------------------------
# args_applied source attribution
# ---------------------------------------------------------------------------

def test_args_applied_user_vs_default(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--batch-size", "256", "--dry-run",
    )
    assert code == 0, m
    applied = m["manifest"]["args_applied"]
    assert applied["batch_size"]["value"] == 256
    assert applied["batch_size"]["source"] == "user"
    # batch_size is the only runtime knob the skill exposes.
    assert set(applied.keys()) == {"batch_size"}


def test_args_applied_default_batch_size(tmp_path: Path) -> None:
    """Without --batch-size, the value comes from defaults_embed.runtime.batch_size."""
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 0, m
    applied = m["manifest"]["args_applied"]
    assert applied["batch_size"]["source"] == "default-config"
    assert applied["batch_size"]["value"] == 64


# ---------------------------------------------------------------------------
# GPU handling
# ---------------------------------------------------------------------------

def test_multi_gpu_rejected(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--gpus", "0,1", "--dry-run",
    )
    assert code == 1
    assert any("single-GPU" in e for e in m["errors"])


# ---------------------------------------------------------------------------
# Manifest schema
# ---------------------------------------------------------------------------

def test_manifest_required_keys(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 0, m
    required = (
        "workflow", "started_at", "container", "repo", "inputs",
        "args_applied", "arch", "output_dir", "argv", "cmd_replay",
        "ok_to_replay",
    )
    for k in required:
        assert k in m["manifest"], f"missing required manifest key: {k}"


def test_manifest_persisted(tmp_path: Path) -> None:
    out = tmp_path / "run"
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(out), "--dry-run",
    )
    assert code == 0, m
    disk = json.loads((out / "run.json").read_text())
    assert disk["workflow"] == "embed"
    assert disk["dry_run"] is True


# ---------------------------------------------------------------------------
# prepare_data manifest gating
# ---------------------------------------------------------------------------

def test_rejects_wrong_mode_manifest(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    m_data = json.loads(prep.read_text())
    m_data["mode"] = "inference"
    prep.write_text(json.dumps(m_data))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 1
    err_blob = " ".join(m["errors"])
    assert "expected 'embed'" in err_blob


def test_rejects_missing_clean_csv(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    m_data = json.loads(prep.read_text())
    m_data["outputs"] = {}  # remove clean_csv
    prep.write_text(json.dumps(m_data))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 1
    assert any("clean_csv" in e for e in m["errors"])


# ---------------------------------------------------------------------------
# Slow end-to-end smoke (real encoder-bearing ckpt + real prep)
# ---------------------------------------------------------------------------

# Use the legacy grover_base ckpt — encoder-only, smallest of the real ckpts,
# and exercises the legacy `grover.*` encoder prefix path.
REAL_GROVER_BASE_CKPT = REPO_ROOT / "model" / "grover_base" / "grover_base.pt"
REAL_TEST_CSV = REPO_ROOT / "tests" / "data" / "finetune" / "test.csv"
PREPARE_DATA_SCRIPT = REPO_ROOT / "agent" / "scripts" / "prepare_data.py"


@pytest.mark.slow
def test_end_to_end_embed_with_real_grover_base_ckpt(tmp_path: Path) -> None:
    """Real-ckpt smoke: prep an embed CSV, run extract_embeddings, verify the
    4 readout .npy files land in <out>/out/."""
    if not REAL_GROVER_BASE_CKPT.is_file():
        pytest.skip(f"real grover_base ckpt not found at {REAL_GROVER_BASE_CKPT}")
    if not REAL_TEST_CSV.is_file():
        pytest.skip(f"real test CSV not found at {REAL_TEST_CSV}")

    out_dir = tmp_path / "run"
    out_dir.mkdir()
    data_dir = out_dir / "data"
    prep_proc = subprocess.run(
        [sys.executable, str(PREPARE_DATA_SCRIPT),
         "--mode", "embed",
         "--csv", str(REAL_TEST_CSV),
         "--out", str(data_dir)],
        capture_output=True, text=True,
    )
    assert prep_proc.returncode == 0, (
        f"prepare_data failed: stdout={prep_proc.stdout[-500:]} stderr={prep_proc.stderr[-500:]}"
    )
    prep_manifest = data_dir / "prepare_data.json"
    assert prep_manifest.is_file()

    code, m = _run(
        "--ckpt", str(REAL_GROVER_BASE_CKPT),
        "--prepare-manifest", str(prep_manifest),
        "--out", str(out_dir),
        "--batch-size", "16",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["workflow"] == "embed"
    assert manifest["status"] == "ok"
    # grover_base ckpt: model_type comes back as "grover_base" (legacy ckpt has
    # no vocab heads, but check_checkpoint's broadened rule still tags it).
    assert manifest["model_type"] == "grover_base"

    # Output: 4 readouts written by task/extract_embeddings.py.
    output_dir = Path(manifest["output_dir"])
    expected_files = {"atom_from_atom.npy", "bond_from_atom.npy",
                      "atom_from_bond.npy", "bond_from_bond.npy"}
    actual_files = {p.name for p in output_dir.glob("*.npy")}
    assert expected_files.issubset(actual_files), (
        f"expected {expected_files}, got {actual_files}"
    )
    # The skill writes only the 4 encoder readouts — never projected.npy.
    assert "projected.npy" not in actual_files

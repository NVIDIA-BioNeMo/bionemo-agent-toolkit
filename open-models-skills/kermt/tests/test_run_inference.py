# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/run_inference.py.

Exercises the argv builder + manifest writer via --dry-run, using cached
check_checkpoint.py JSON + a synthesized prepare_data.json. No real ckpt is
loaded; the runner reads the cached validator output directly.

Run in-container:
    KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \\
        "python -m pytest agent/tests/test_run_inference.py -v \\
            --no-header -p no:cacheprovider"
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "agent" / "scripts" / "run_inference.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_validator_out(*, has_task_ffn: bool = True, task_output_dims: list[int] | None = None,
                        ok: bool | None = None) -> dict:
    """Synthetic check_checkpoint.py --mode inference output.
    has_task_ffn=True means a finetuned ckpt (validator accepts).
    has_task_ffn=False means a pretrain ckpt (validator rejects)."""
    if ok is None:
        ok = has_task_ffn
    return {
        "ok": ok,
        "model_type": "finetuned" if has_task_ffn else "grover_base",
        "has_encoder": True,
        "has_vocab_head": not has_task_ffn,
        "has_contrast_head": False,
        "has_task_ffn": has_task_ffn,
        "task_output_dims": task_output_dims if task_output_dims is not None else ([4] if has_task_ffn else []),
        "vocab_sizes": {"atom": None, "bond": None, "smiles": None},
        "arch": {
            "hidden_size": 800, "depth": 6, "num_attn_head": 4,
            "activation": "PReLU", "backbone": "gtrans",
            "embedding_output_type": "both", "self_attention": False,
            "attn_hidden": None, "attn_out": None,
        },
        "saved_args": {},
        "errors": (
            [] if has_task_ffn
            else ["inference requires a finetuned ckpt with task FFN heads"]
        ),
        "warnings": [],
    }


def _make_prepare_manifest(out_dir: Path, with_features: bool = True) -> Path:
    data = out_dir / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "clean.csv").write_text("smiles\nCCO\n")
    outputs: dict[str, str] = {"clean_csv": str(data / "clean.csv")}
    if with_features:
        (data / "clean.npz").write_bytes(b"\x00")
        outputs["clean_npz"] = str(data / "clean.npz")
    manifest = {
        "ok": True,
        "mode": "inference",
        "input_csv": str(out_dir / "in.csv"),
        "val_csv": None,
        "test_csv": None,
        "output_dir": str(data),
        "split_method": "n/a",
        "steps": [],
        "outputs": outputs,
        "errors": [],
        "warnings": [],
    }
    mpath = data / "prepare_data.json"
    mpath.write_text(json.dumps(manifest, indent=2))
    return mpath


def _setup(tmp_path: Path, *, has_task_ffn: bool = True, with_features: bool = True
           ) -> tuple[Path, Path, Path]:
    ckpt = tmp_path / "dummy.pt"
    ckpt.write_bytes(b"\x00")
    prep = _make_prepare_manifest(tmp_path, with_features=with_features)
    val = _make_validator_out(has_task_ffn=has_task_ffn)
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
# Dispatch + argv shape
# ---------------------------------------------------------------------------

def test_dispatch_basic(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["workflow"] == "inference"
    assert manifest["model_type"] == "finetuned"
    assert manifest["gpu"] == 0
    argv = manifest["argv"]
    assert "main.py" in argv[2]
    assert argv[3] == "predict"
    assert "--data_path" in argv
    assert "--output_path" in argv
    assert "--checkpoint_dir" in argv
    assert "--features_path" in argv
    # task_output_dims plumbed through for downstream display
    assert manifest["task_output_dims"] == [4]


def test_dispatch_without_features(tmp_path: Path) -> None:
    """If prepare ran with --skip-features, --features_path is absent."""
    ckpt, prep, val = _setup(tmp_path, with_features=False)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert "--features_path" not in argv
    assert "--data_path" in argv


# ---------------------------------------------------------------------------
# Ckpt validator gating
# ---------------------------------------------------------------------------

def test_rejects_pretrain_ckpt(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, has_task_ffn=False)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 1
    # The validator's stock error message gets passed through.
    err_blob = " ".join(m["errors"])
    assert "task FFN heads" in err_blob or "rejected the input ckpt" in err_blob


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


def test_gpu_id_propagates(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--gpus", "3", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["gpu"] == 3
    argv = manifest["argv"]
    assert argv[argv.index("--gpu") + 1] == "3"


# ---------------------------------------------------------------------------
# args_applied source attribution
# ---------------------------------------------------------------------------

def test_args_applied_user_vs_default(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--batch-size", "128", "--dry-run",
    )
    assert code == 0, m
    applied = m["manifest"]["args_applied"]
    assert applied["batch_size"]["value"] == 128
    assert applied["batch_size"]["source"] == "user"
    assert applied["seed"]["source"] == "default-config"
    # batch_size + seed are the only knobs the skill exposes.
    assert set(applied.keys()) == {"batch_size", "seed"}


def test_argv_omits_features_scaling_flag(tmp_path: Path) -> None:
    """task/predict.py honors only the train-time features_scaling stored in
    the ckpt's saved args, so the predict-time --no_features_scaling flag
    has no effect. The runner therefore does not forward it."""
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 0, m
    assert "--no_features_scaling" not in m["manifest"]["argv"]


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
        "args_applied", "arch", "task_output_dims", "output_csv",
        "argv", "cmd_replay", "ok_to_replay",
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
    assert disk["workflow"] == "inference"
    assert disk["dry_run"] is True


# ---------------------------------------------------------------------------
# prepare_data manifest gating
# ---------------------------------------------------------------------------

def test_rejects_wrong_mode_manifest(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    m_data = json.loads(prep.read_text())
    m_data["mode"] = "finetune"
    prep.write_text(json.dumps(m_data))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 1
    err_blob = " ".join(m["errors"])
    assert "expected 'inference'" in err_blob or "mode=" in err_blob


def test_rejects_failed_prepare(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    m_data = json.loads(prep.read_text())
    m_data["ok"] = False
    m_data["errors"] = ["clean_smiles failed"]
    prep.write_text(json.dumps(m_data))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dry-run",
    )
    assert code == 1
    assert any("ok=False" in e for e in m["errors"])


# ---------------------------------------------------------------------------
# Slow end-to-end smoke (real finetuned ckpt + real prep)
# ---------------------------------------------------------------------------

REAL_FINETUNED_CKPT = (
    REPO_ROOT / "model" / "biogen"
    / "biogen_HLM_RLM_MDCK_logS_grover_base_seed0"
    / "fold_0" / "model_0" / "model.pt"
)
REAL_TEST_CSV = REPO_ROOT / "tests" / "data" / "finetune" / "test.csv"
PREPARE_DATA_SCRIPT = REPO_ROOT / "agent" / "scripts" / "prepare_data.py"


@pytest.mark.slow
def test_end_to_end_inference_with_real_ckpt(tmp_path: Path) -> None:
    """Real-ckpt smoke: prep an inference CSV, run inference, verify predictions.csv
    contains one row per input SMILES + one column per task head."""
    if not REAL_FINETUNED_CKPT.is_file():
        pytest.skip(f"real finetuned ckpt not found at {REAL_FINETUNED_CKPT}")
    if not REAL_TEST_CSV.is_file():
        pytest.skip(f"real test CSV not found at {REAL_TEST_CSV}")

    # 1. Prepare data (mode=inference): clean + features.
    out_dir = tmp_path / "run"
    out_dir.mkdir()
    data_dir = out_dir / "data"
    prep_proc = subprocess.run(
        [sys.executable, str(PREPARE_DATA_SCRIPT),
         "--mode", "inference",
         "--csv", str(REAL_TEST_CSV),
         "--out", str(data_dir)],
        capture_output=True, text=True,
    )
    assert prep_proc.returncode == 0, (
        f"prepare_data failed: stdout={prep_proc.stdout[-500:]} stderr={prep_proc.stderr[-500:]}"
    )
    prep_manifest = data_dir / "prepare_data.json"
    assert prep_manifest.is_file()

    # 2. Run inference (blocking; not --dry-run this time).
    code, m = _run(
        "--ckpt", str(REAL_FINETUNED_CKPT),
        "--prepare-manifest", str(prep_manifest),
        "--out", str(out_dir),
        "--batch-size", "16",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["workflow"] == "inference"
    assert manifest["status"] == "ok"

    # 3. predictions.csv exists and has the expected shape.
    output_csv = Path(manifest["output_csv"])
    assert output_csv.is_file(), f"predictions.csv missing at {output_csv}"
    lines = output_csv.read_text().strip().split("\n")
    assert len(lines) >= 2, "expected at least one header + one prediction row"
    header = lines[0].split(",")
    # First column is the smiles index (unnamed), then one column per task.
    # The biogen grover_base finetune ckpt has 4 targets: HLM/RLM/MDCK/logS.
    assert len(header) >= 2, f"unexpected header shape: {header}"
    # Each subsequent row is a SMILES + N predictions.
    for ln in lines[1:]:
        cells = ln.split(",")
        assert len(cells) == len(header), f"row shape != header: {cells}"

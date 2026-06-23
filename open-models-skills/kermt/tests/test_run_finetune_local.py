# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/run_finetune_local.py.

Exercises the argv builder + manifest writer via --dry-run, using cached
check_checkpoint.py JSON + a synthesized prepare_data.json so we don't have to
forge a real torch checkpoint or featurize anything. Tests run in a few
seconds.

Run in-container:
    KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \\
        "python -m pytest agent/tests/test_run_finetune_local.py -v \\
            --no-header -p no:cacheprovider"
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "agent" / "scripts" / "run_finetune_local.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_validator_out(
    *, model_type: str = "grover_base",
    self_attention: bool = False,
    has_task_ffn: bool = False,
    arch_overrides: dict | None = None,
) -> dict:
    """Synthetic check_checkpoint.py --mode finetune_init output. arch fields
    match the defaults used to build pretrain ckpts in this repo."""
    arch = {
        "hidden_size": 800, "depth": 6, "num_attn_head": 4,
        "activation": "PReLU", "backbone": "gtrans",
        "embedding_output_type": "both",
        "self_attention": self_attention,
        "attn_hidden": 4 if self_attention else None,
        "attn_out": 128 if self_attention else None,
    }
    if arch_overrides:
        arch.update(arch_overrides)
    # Mirror what check_checkpoint.py --mode finetune_init actually does:
    # already-finetuned ckpts (has_task_ffn=True) are rejected with the
    # finetune-on-finetune error; pretrain ckpts pass.
    return {
        "ok": not has_task_ffn,
        "model_type": "finetuned" if has_task_ffn else model_type,
        "has_encoder": True,
        "has_vocab_head": model_type in ("grover_base", "hybrid"),
        "has_contrast_head": model_type in ("cmim", "hybrid"),
        "has_task_ffn": has_task_ffn,
        "task_output_dims": [4] if has_task_ffn else [],
        "vocab_sizes": {"atom": 311, "bond": 539, "smiles": 60},
        "arch": arch,
        "saved_args": {},
        "errors": (
            ["finetune_init requires a pretrain ckpt (grover_base / cmim / hybrid); "
             "this ckpt is classified as 'finetuned' with task FFN heads attached."]
            if has_task_ffn else []
        ),
        "warnings": [],
    }


def _make_prepare_manifest_random(out_dir: Path, targets: list[str] | None = None) -> Path:
    """random split: prep emits clean_train/val/test CSVs + .npz."""
    data = out_dir / "data"
    data.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        (data / f"clean_{split}.csv").write_text("smiles,t1\nCCO,0.5\n")
        (data / f"clean_{split}.npz").write_bytes(b"\x00")  # placeholder
    manifest = {
        "ok": True,
        "mode": "finetune",
        "input_csv": str(out_dir / "in.csv"),
        "val_csv": None,
        "test_csv": None,
        "output_dir": str(data),
        "split_method": "random",
        "split_seed": 0,
        "split_fractions": {"train": 0.8, "val": 0.1, "test": 0.1},
        "steps": [],
        "outputs": {
            "clean_train_csv": str(data / "clean_train.csv"),
            "clean_val_csv":   str(data / "clean_val.csv"),
            "clean_test_csv":  str(data / "clean_test.csv"),
            "clean_train_npz": str(data / "clean_train.npz"),
            "clean_val_npz":   str(data / "clean_val.npz"),
            "clean_test_npz":  str(data / "clean_test.npz"),
        },
        "targets": targets or ["t1"],
        "errors": [],
        "warnings": [],
    }
    mpath = data / "prepare_data.json"
    mpath.write_text(json.dumps(manifest, indent=2))
    return mpath


def _make_prepare_manifest_deferred(out_dir: Path, split_type: str = "scaffold_balanced") -> Path:
    """deferred_to_runner: prep emits a single clean_full CSV + .npz; the
    runner asks task/train.py to split internally."""
    data = out_dir / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "clean_full.csv").write_text("smiles,t1\nCCO,0.5\n")
    (data / "clean_full.npz").write_bytes(b"\x00")
    manifest = {
        "ok": True,
        "mode": "finetune",
        "input_csv": str(out_dir / "in.csv"),
        "val_csv": None,
        "test_csv": None,
        "output_dir": str(data),
        "split_method": "deferred_to_runner",
        "split_type": split_type,
        "split_seed": 7,
        "split_fractions": {"train": 0.8, "val": 0.1, "test": 0.1},
        "steps": [],
        "outputs": {
            "clean_full_csv": str(data / "clean_full.csv"),
            "clean_full_npz": str(data / "clean_full.npz"),
        },
        "targets": ["t1"],
        "errors": [],
        "warnings": [],
    }
    mpath = data / "prepare_data.json"
    mpath.write_text(json.dumps(manifest, indent=2))
    return mpath


def _setup(
    tmp_path: Path, *,
    split: str = "random",
    self_attention: bool = False,
    has_task_ffn: bool = False,
    split_type: str = "scaffold_balanced",
) -> tuple[Path, Path, Path]:
    """Builds (dummy_ckpt_path, prepare_manifest_path, validator_json_path)."""
    ckpt = tmp_path / "dummy.pt"
    ckpt.write_bytes(b"\x00")  # path-only; runner reads via cached validator_out
    if split == "random":
        prep = _make_prepare_manifest_random(tmp_path)
    elif split == "deferred":
        prep = _make_prepare_manifest_deferred(tmp_path, split_type=split_type)
    else:
        raise ValueError(f"unknown split fixture: {split}")
    val = _make_validator_out(self_attention=self_attention, has_task_ffn=has_task_ffn)
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
# Dispatch tests — argv shape per prep split mode
# ---------------------------------------------------------------------------

def test_dispatch_random_split(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, split="random")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["workflow"] == "finetune"
    assert manifest["model_type"] == "grover_base"
    assert manifest["gpu"] == 0

    argv = manifest["argv"]
    # main.py finetune subcommand
    assert "main.py" in argv[2]
    assert argv[3] == "finetune"
    # random split uses separate train/val/test paths
    assert "--data_path" in argv
    assert "--separate_val_path" in argv
    assert "--separate_test_path" in argv
    assert "--features_path" in argv
    assert "--separate_val_features_path" in argv
    assert "--separate_test_features_path" in argv
    # checkpoint pass-through
    assert "--checkpoint_path" in argv
    assert argv[argv.index("--checkpoint_path") + 1] == str(ckpt)


def test_dispatch_deferred_scaffold_split(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, split="deferred", split_type="scaffold_balanced")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    # deferred split passes single data_path; train.py splits internally
    assert "--data_path" in argv
    assert "--separate_val_path" not in argv
    assert "--separate_test_path" not in argv
    # split_type comes from manifest, not from defaults_finetune (since prep set it)
    assert "--split_type" in argv
    assert argv[argv.index("--split_type") + 1] == "scaffold_balanced"
    # split_sizes is plumbed for deferred path
    assert "--split_sizes" in argv


def test_dispatch_deferred_index_predetermined(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, split="deferred", split_type="index_predetermined")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert argv[argv.index("--split_type") + 1] == "index_predetermined"


# ---------------------------------------------------------------------------
# Ckpt validator gating
# ---------------------------------------------------------------------------

def test_rejects_finetuned_ckpt(tmp_path: Path) -> None:
    """The kermt-finetune skill rejects already-finetuned ckpts. Finetune-on-
    finetune isn't supported: saved-task identity can't be machine-verified
    against the new training data (dim match doesn't prove target or dataset
    identity). Manual escape hatch: call `main.py finetune` directly."""
    ckpt, prep, val = _setup(tmp_path, has_task_ffn=True)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 1
    err_blob = " ".join(m["errors"])
    assert "finetune_init requires a pretrain ckpt" in err_blob
    assert "finetuned" in err_blob


# ---------------------------------------------------------------------------
# Arch plumbing
# ---------------------------------------------------------------------------

def test_arch_pulled_from_ckpt_validator(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert "--hidden_size" in argv and argv[argv.index("--hidden_size") + 1] == "800"
    assert "--depth" in argv and argv[argv.index("--depth") + 1] == "6"
    assert "--num_attn_head" in argv and argv[argv.index("--num_attn_head") + 1] == "4"
    # self_attention=False in this fixture -> flag absent
    assert "--self_attention" not in argv


def test_self_attention_arch_propagated(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, self_attention=True)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert "--self_attention" in argv
    assert "--attn_hidden" in argv and argv[argv.index("--attn_hidden") + 1] == "4"
    assert "--attn_out" in argv and argv[argv.index("--attn_out") + 1] == "128"


# ---------------------------------------------------------------------------
# MTL FFN handling
# ---------------------------------------------------------------------------

def test_extended_training_overrides_propagate(tmp_path: Path) -> None:
    """User CLI flags --warmup-epochs, --weight-decay, --early-stop-epoch, and
    --show-individual-scores reach main.py finetune. These weren't in the
    initial FLAG tuples and silently no-op'd until the dead-knob audit."""
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression",
        "--warmup-epochs", "3.5",
        "--weight-decay", "1e-6",
        "--early-stop-epoch", "10",
        "--show-individual-scores",
        "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert "--warmup_epochs" in argv and argv[argv.index("--warmup_epochs") + 1] == "3.5"
    assert "--weight_decay" in argv and argv[argv.index("--weight_decay") + 1] == "1e-06"
    assert "--early_stop_epoch" in argv and argv[argv.index("--early_stop_epoch") + 1] == "10"
    assert "--show_individual_scores" in argv
    applied = m["manifest"]["args_applied"]
    for key in ("warmup_epochs", "weight_decay", "early_stop_epoch", "show_individual_scores"):
        assert applied[key]["source"] == "user", f"{key} not recorded as user-source"


def test_mtl_ffn_off_by_default(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    # default ffn_num_task_specific_layers=0 -> MTL flags omitted
    assert "--ffn_num_task_specific_layers" not in argv
    assert "--ffn_task_specific_hidden_size" not in argv


def test_mtl_ffn_user_override_propagates(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression",
        "--ffn-num-task-specific-layers", "2",
        "--ffn-task-specific-hidden-size", "200",
        "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert "--ffn_num_task_specific_layers" in argv
    assert argv[argv.index("--ffn_num_task_specific_layers") + 1] == "2"
    assert "--ffn_task_specific_hidden_size" in argv
    assert argv[argv.index("--ffn_task_specific_hidden_size") + 1] == "200"


def test_mtl_ffn_inconsistent_rejected(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression",
        "--ffn-num-task-specific-layers", "2",
        # missing --ffn-task-specific-hidden-size
        "--dry-run",
    )
    assert code == 1
    assert any("ffn_task_specific_hidden_size" in e for e in m["errors"])


# ---------------------------------------------------------------------------
# dataset_type defaulting
# ---------------------------------------------------------------------------

def test_dataset_type_defaults_to_regression(tmp_path: Path) -> None:
    """defaults_finetune.json provides dataset_type='regression' as the default
    (ADMET-friendly); the runner picks it up if --dataset-type wasn't passed.
    For classification tasks the user overrides via --dataset-type classification."""
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        # no --dataset-type
        "--dry-run",
    )
    assert code == 0, m
    applied = m["manifest"]["args_applied"]
    assert applied["dataset_type"]["value"] == "regression"
    assert applied["dataset_type"]["source"] == "default-config"


def test_dataset_type_user_override_propagates(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "classification", "--dry-run",
    )
    assert code == 0, m
    applied = m["manifest"]["args_applied"]
    assert applied["dataset_type"]["value"] == "classification"
    assert applied["dataset_type"]["source"] == "user"
    argv = m["manifest"]["argv"]
    assert argv[argv.index("--dataset_type") + 1] == "classification"


# ---------------------------------------------------------------------------
# args_applied source attribution
# ---------------------------------------------------------------------------

def test_args_applied_records_user_vs_default(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression",
        "--epochs", "50",   # user override
        "--dry-run",
    )
    assert code == 0, m
    applied = m["manifest"]["args_applied"]
    assert applied["epochs"]["value"] == 50
    assert applied["epochs"]["source"] == "user"
    # batch_size left to default -> source=default-config
    assert applied["batch_size"]["source"] == "default-config"


# ---------------------------------------------------------------------------
# GPU handling
# ---------------------------------------------------------------------------

def test_multi_gpu_rejected(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression",
        "--gpus", "0,1", "--dry-run",
    )
    assert code == 1
    assert any("single-GPU" in e for e in m["errors"])


def test_gpu_id_propagates(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression",
        "--gpus", "2", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["gpu"] == 2
    argv = manifest["argv"]
    assert argv[argv.index("--gpu") + 1] == "2"


# ---------------------------------------------------------------------------
# Manifest schema
# ---------------------------------------------------------------------------

def test_manifest_required_keys_present(tmp_path: Path) -> None:
    """Reproducibility metadata: every finetune run.json carries these."""
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 0, m
    required = (
        "workflow", "started_at", "container", "repo",
        "inputs", "args_applied", "arch", "argv",
        "cmd_replay", "ok_to_replay", "save_dir", "logs_dir",
    )
    manifest = m["manifest"]
    for k in required:
        assert k in manifest, f"missing required manifest key: {k}"
    assert "commit" in manifest["repo"]
    assert "dirty" in manifest["repo"]
    assert "image_tag" in manifest["container"]
    assert manifest["inputs"]["targets"] == ["t1"]


def test_manifest_persisted_to_disk(tmp_path: Path) -> None:
    out = tmp_path / "run"
    ckpt, prep, val = _setup(tmp_path)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(out),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 0, m
    disk_manifest = json.loads((out / "run.json").read_text())
    assert disk_manifest["workflow"] == "finetune"
    assert disk_manifest["dry_run"] is True


# ---------------------------------------------------------------------------
# prepare_data manifest gating
# ---------------------------------------------------------------------------

def test_rejects_wrong_mode_manifest(tmp_path: Path) -> None:
    """A pretrain prepare_data.json should be rejected by the finetune runner."""
    ckpt, prep, val = _setup(tmp_path)
    # Tamper with the manifest to claim mode=pretrain
    m_data = json.loads(prep.read_text())
    m_data["mode"] = "pretrain"
    prep.write_text(json.dumps(m_data))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 1
    assert any("mode=" in e or "expected 'finetune'" in e for e in m["errors"])


def test_rejects_failed_prepare_manifest(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path)
    m_data = json.loads(prep.read_text())
    m_data["ok"] = False
    m_data["errors"] = ["clean_smiles failed"]
    prep.write_text(json.dumps(m_data))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val), "--out", str(tmp_path / "run"),
        "--dataset-type", "regression", "--dry-run",
    )
    assert code == 1
    assert any("ok=False" in e for e in m["errors"])

# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/run_pretrain_local.py.

Exercises the argv builder + manifest writer via --dry-run. Synthetic ckpts +
prepare_data manifests + cached validator JSON keep test runtime under a few
seconds without burning GPU time on actual pretrain epochs.

Run in-container:
    KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \
        "python -m pytest agent/tests/test_run_pretrain_local.py -v \\
            --no-header -p no:cacheprovider"
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
import torch


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "agent" / "scripts" / "run_pretrain_local.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_synthetic_ckpt(
    tmp_path: Path,
    model_type: str,
    *,
    with_resume_state: bool = False,
    saved_schedule: dict | None = None,
) -> Path:
    """Build a minimal save_model_for_restart-format dict with the state_dict
    key prefixes that signal the requested model_type.

    When ``with_resume_state=True``, the ckpt also carries the top-level
    keys pretrain_ddp.py expects to restore mid-run (``optimizer``,
    ``scheduler_step``, ``epoch``, ``batch_idx``, ``wandb_run_id``) so
    --resume validation passes. ``saved_schedule`` (if given) is merged
    into the ckpt's ``args`` Namespace so the schedule fields are present
    on ``ckpt.args`` — required by --resume's saved_args inheritance.
    """
    sd: dict[str, torch.Tensor] = {}
    # Encoder (kermt.* prefix used by all modern repo ckpts)
    sd["kermt.encoders.layer0.weight"] = torch.zeros(800, 133)

    if model_type == "grover_base":
        sd["vocab_module.atom_vocab_predictor.weight"] = torch.zeros(1000, 800)
        sd["vocab_module.bond_vocab_predictor.weight"] = torch.zeros(500, 800)
    elif model_type == "cmim":
        # cmim: encoder lives inside latent_dist; drop the top-level kermt.* keys.
        sd = {f"latent_dist.{k}": v for k, v in sd.items()}
        sd["latent_dist.fc_mean_logscale.weight"] = torch.zeros(800, 800)
        sd["decoder.embedding.weight"] = torch.zeros(60, 800)
    elif model_type == "hybrid":
        sd["latent_dist.fc_mean_logscale.weight"] = torch.zeros(800, 800)
        sd["decoder.embedding.weight"] = torch.zeros(60, 800)
        sd["vocab_module.atom_vocab_predictor.weight"] = torch.zeros(1000, 800)
        sd["vocab_module.bond_vocab_predictor.weight"] = torch.zeros(500, 800)
    elif model_type == "grover_base_encoder_only":
        # Encoder only, no heads — should be rejected by run_pretrain_local.
        pass
    elif model_type == "finetuned":
        sd["mol_atom_from_atom_ffn.3.weight"] = torch.zeros(4, 800)
        sd["mol_atom_from_bond_ffn.3.weight"] = torch.zeros(4, 800)

    args = Namespace(
        hidden_size=800, depth=6, num_attn_head=4, latent_dim=800,
        activation="PReLU", backbone="gtrans", embedding_output_type="both",
        self_attention=False,
    )
    if saved_schedule:
        for k, v in saved_schedule.items():
            setattr(args, k, v)

    payload: dict = {"args": args, "state_dict": sd}
    if with_resume_state:
        # Synthetic full save_model_for_restart payload. The runner only
        # checks key PRESENCE in --resume mode, not the actual values, so
        # placeholder shapes are fine.
        payload["optimizer"] = {"state": {}, "param_groups": []}
        payload["scheduler_step"] = 5000
        payload["epoch"] = 3
        payload["batch_idx"] = 12
        payload["wandb_run_id"] = "wb-test-run-id"
    p = tmp_path / f"{model_type}.pt"
    torch.save(payload, p)
    return p


def _make_validator_out(
    model_type: str, has_vocab_head: bool | None = None,
    atom_size: int | None = None, bond_size: int | None = None, smiles_size: int | None = None,
) -> dict:
    """Synthetic check_checkpoint.py output, shaped just enough that the
    runner trusts it as-is (skip --ckpt-validator-out absence path).
    vocab_sizes default to plausible values per model_type."""
    if has_vocab_head is None:
        has_vocab_head = model_type in ("grover_base", "hybrid")
    if model_type == "hybrid":
        atom_size = atom_size if atom_size is not None else 311
        bond_size = bond_size if bond_size is not None else 539
        smiles_size = smiles_size if smiles_size is not None else 60
    elif model_type == "grover_base" and has_vocab_head:
        atom_size = atom_size if atom_size is not None else 311
        bond_size = bond_size if bond_size is not None else 539
    elif model_type == "cmim":
        smiles_size = smiles_size if smiles_size is not None else 60
    return {
        "ok": True,
        "model_type": model_type,
        "has_encoder": True,
        "has_vocab_head": has_vocab_head,
        "has_contrast_head": model_type in ("cmim", "hybrid"),
        "has_task_ffn": False,
        "task_output_dims": [],
        "vocab_sizes": {"atom": atom_size, "bond": bond_size, "smiles": smiles_size},
        "arch": {
            "hidden_size": 800, "depth": 6, "num_attn_head": 4, "latent_dim": 800,
            "activation": "PReLU", "backbone": "gtrans", "embedding_output_type": "both",
            "self_attention": False,
        },
        # cMIM/hybrid continue-pretrain reads decoder arch from saved_args
        # (see CMIM_DECODER_FLAGS_FROM_CKPT in run_pretrain_local.py). Synthesize
        # default-shaped values so the runner can build argv; tests that exercise
        # the missing-field error path overwrite this block explicitly.
        "saved_args": (
            {
                "latent_dim": 800,
                "decoder_num_layers": 3,
                "decoder_num_attention_heads": 8,
                "decoder_ffn_hidden_size": 2048,
                "decoder_dropout": 0.1,
                "decoder_max_seq_len": 512,
                "decoder_positional_encoding": "rope",
                "decoder_gate_self_attn": False,
                "decoder_gate_cross_attn": False,
            }
            if model_type in ("cmim", "hybrid")
            else {}
        ),
        "errors": [],
        "warnings": [],
    }


def _make_prepare_manifest(
    out_dir: Path, atom_size: int = 311, bond_size: int = 539, smiles_size: int = 60,
) -> Path:
    """Synthesizes a complete prepare_data.json + the referenced output files
    (vocabs sized to match the validator's vocab_sizes; shard dirs as empty
    placeholders) so the runner can see them and verify vocab sizes."""
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    # Write atom/bond vocabs as JSON with a `stoi` block of the right size.
    for stem, size in (("pretrain_atom_vocab", atom_size), ("pretrain_bond_vocab", bond_size)):
        stoi = {f"tok_{i}": i for i in range(size)}
        (data_dir / f"{stem}.json").write_text(json.dumps({"stoi": stoi}))
    # Smiles vocab — pickle a plain dict; _count_vocab_entries falls through
    # to the raw-pickle path when MolVocab/SMILESVocab loaders reject it.
    import pickle
    smiles_stoi = {f"smi_{i}": i for i in range(smiles_size)}
    (data_dir / "pretrain_smiles_vocab.pkl").write_bytes(pickle.dumps(smiles_stoi))
    for split in ("train", "val"):
        d = data_dir / split
        (d / "graph").mkdir(parents=True, exist_ok=True)
        (d / "feature").mkdir(parents=True, exist_ok=True)
        (d / "summary.txt").write_text("n_files:1\nn_samples:0\nsample_per_file:0\n")
    manifest = {
        "ok": True,
        "mode": "pretrain",
        "input_csv": str(out_dir / "in.csv"),
        "val_csv": None,
        "output_dir": str(data_dir),
        "split_method": "random",
        "split_seed": 0,
        "split_fractions": {"train": 0.9, "val": 0.1},
        "steps": [],
        "outputs": {
            "clean_train_csv": str(data_dir / "clean_train.csv"),
            "clean_val_csv":   str(data_dir / "clean_val.csv"),
            "atom_vocab":      str(data_dir / "pretrain_atom_vocab.json"),
            "bond_vocab":      str(data_dir / "pretrain_bond_vocab.json"),
            "smiles_vocab":    str(data_dir / "pretrain_smiles_vocab.pkl"),
            "train_dir":       str(data_dir / "train"),
            "val_dir":         str(data_dir / "val"),
        },
        "errors": [],
        "warnings": [],
    }
    mpath = data_dir / "prepare_data.json"
    mpath.write_text(json.dumps(manifest, indent=2))
    return mpath


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


def _setup(tmp_path: Path, model_type: str, **manifest_overrides) -> tuple[Path, Path, Path]:
    """Builds (ckpt, prepare_manifest, validator_out_json). Returns paths."""
    ckpt = _make_synthetic_ckpt(tmp_path, model_type)
    prep = _make_prepare_manifest(tmp_path)
    val = _make_validator_out(model_type, **manifest_overrides)
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val, indent=2))
    return ckpt, prep, val_path


# ---------------------------------------------------------------------------
# Dispatch tests — argv shape per model_type
# ---------------------------------------------------------------------------

def test_dispatch_grover_base_vocab_only(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "grover_base")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["model_type"] == "grover_base"
    assert manifest["pretrain_mode"] == "vocab"
    argv = manifest["argv"]
    assert "--pretrain_mode" in argv and argv[argv.index("--pretrain_mode") + 1] == "vocab"
    assert "--smiles_vocab_path" not in argv  # vocab-only doesn't need smiles vocab
    assert "--vocab_loss_weight" not in argv
    assert "--latent_dim" not in argv


def test_dispatch_cmim(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "cmim")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["model_type"] == "cmim"
    assert manifest["pretrain_mode"] == "cmim"
    argv = manifest["argv"]
    assert argv[argv.index("--pretrain_mode") + 1] == "cmim"
    assert "--smiles_vocab_path" in argv
    assert "--latent_dim" in argv
    assert "--contrastive_temperature" in argv
    assert "--vocab_loss_weight" not in argv  # cmim has no vocab loss


def test_dispatch_hybrid(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["model_type"] == "hybrid"
    assert manifest["pretrain_mode"] == "hybrid"
    argv = manifest["argv"]
    assert argv[argv.index("--pretrain_mode") + 1] == "hybrid"
    assert "--smiles_vocab_path" in argv
    assert "--latent_dim" in argv
    assert "--contrastive_temperature" in argv
    assert "--vocab_loss_weight" in argv


def test_wandb_flags_forwarded_when_set(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "grover_base")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
        "--wandb-project", "myproj", "--wandb-run-name", "myrun",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert argv[argv.index("--wandb_project") + 1] == "myproj"
    assert argv[argv.index("--wandb_run_name") + 1] == "myrun"


def test_wandb_flags_absent_by_default(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "grover_base")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    argv = m["manifest"]["argv"]
    assert "--wandb_project" not in argv
    assert "--wandb_run_name" not in argv


def test_dispatch_rejects_finetuned(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "finetuned")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1
    assert any("model_type" in e for e in m["errors"])


def test_dispatch_rejects_encoder_only_grover_base(tmp_path: Path) -> None:
    """grover_base WITHOUT vocab heads is encoder-only; should suggest upgrade_to_hybrid."""
    ckpt, prep, val = _setup(tmp_path, "grover_base_encoder_only", has_vocab_head=False)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    # The synthetic validator above still says model_type=grover_base_encoder_only,
    # which isn't in MODEL_TYPE_TO_PRETRAIN_MODE — so it errors at the model-type
    # dispatch step. That's the right behavior.
    assert code == 1
    assert any("model_type" in e for e in m["errors"])


def test_grover_base_no_vocab_head_rejected(tmp_path: Path) -> None:
    """Even when the validator labels the ckpt 'grover_base', if it has no vocab head
    (legacy encoder-only ckpts like the original-grover grover_base.pt) the runner
    must reject because there's nothing to continue."""
    ckpt, prep, val = _setup(tmp_path, "grover_base", has_vocab_head=False)
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1
    assert any("upgrade_to_hybrid" in e for e in m["errors"])


# ---------------------------------------------------------------------------
# Hardware / GPU-count tests
# ---------------------------------------------------------------------------

def test_single_gpu_fallback_defaults(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["world_size"] == 1
    assert manifest["cuda_visible_devices"] == "0"
    # Single-GPU fallback: batch_size 32, save_interval 500.
    assert manifest["args_applied"]["batch_size"]["value"] == 32
    assert manifest["args_applied"]["batch_size"]["source"] == "auto-1gpu"
    assert manifest["args_applied"]["save_interval"]["value"] == 500
    assert manifest["args_applied"]["save_interval"]["source"] == "auto-1gpu"


def test_multi_gpu_keeps_defaults_batch_size(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0,1,2,3", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["world_size"] == 4
    # batch_size in defaults_pretrain.json is 256; multi-GPU keeps it.
    assert manifest["args_applied"]["batch_size"]["value"] == 256
    assert manifest["args_applied"]["batch_size"]["source"] == "default-config"


def test_user_override_recorded_as_source_user(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0,1", "--dry-run",
        "--epochs", "5", "--init-lr", "2e-5",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["args_applied"]["epochs"] == {"value": 5, "source": "user"}
    assert manifest["args_applied"]["init_lr"] == {"value": 2e-5, "source": "user"}


# ---------------------------------------------------------------------------
# Arch + ckpt symlink tests
# ---------------------------------------------------------------------------

def test_arch_pulled_from_validator(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["arch"]["hidden_size"] == 800
    assert manifest["arch"]["depth"] == 6
    argv = manifest["argv"]
    assert argv[argv.index("--hidden_size") + 1] == "800"
    assert argv[argv.index("--depth") + 1] == "6"
    assert argv[argv.index("--backbone") + 1] == "gtrans"


def test_ckpt_materialized_into_save_dir_default_mode(tmp_path: Path) -> None:
    """Default (fresh-schedule) mode writes a REAL FILE at
    <save_dir>/last_checkpoint.pt — a state-cleaned copy of the user ckpt,
    NOT a symlink. This is the new behavior since --resume vs default-mode
    dispatch was introduced; previously every continue-pretrain run
    symlinked, but that conflated the two modes."""
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    out = tmp_path / "run"
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(out), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    target = out / "ckpt" / "last_checkpoint.pt"
    assert target.is_file(), "materialized ckpt missing"
    assert not target.is_symlink(), "fresh-schedule mode should materialize, not symlink"
    # Manifest reflects the mode + the materialized path.
    assert m["manifest"]["mode"] == "continue_pretrain_fresh_schedule"
    assert m["manifest"]["ckpt_symlink"] == str(target)


def test_ckpt_symlinked_into_save_dir_resume_mode(tmp_path: Path) -> None:
    """--resume keeps the symlink approach: <save_dir>/last_checkpoint.pt
    is a symlink to the user-supplied ckpt, so pretrain_ddp.py's auto-resume
    sees the original (unmodified) ckpt and restores everything from it."""
    ckpt = _make_synthetic_ckpt(tmp_path, "hybrid", with_resume_state=True,
                                saved_schedule={"epochs": 100, "warmup_epochs": 20,
                                                "init_lr": 1e-5, "max_lr": 1.5e-4,
                                                "final_lr": 1e-5})
    prep = _make_prepare_manifest(tmp_path)
    val_out = _make_validator_out("hybrid")
    val_out["saved_args"] = {
        **val_out.get("saved_args", {}),
        "epochs": 100, "warmup_epochs": 20, "init_lr": 1e-5,
        "max_lr": 1.5e-4, "final_lr": 1e-5,
    }
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val_out, indent=2))
    out = tmp_path / "run"
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val_path),
        "--out", str(out), "--gpus", "0",
        "--resume", "--dry-run",
    )
    assert code == 0, m
    link = out / "ckpt" / "last_checkpoint.pt"
    assert link.is_symlink(), "--resume should symlink, not materialize"
    assert link.resolve() == ckpt.resolve()


# ---------------------------------------------------------------------------
# Run.json manifest fields
# ---------------------------------------------------------------------------

def test_run_manifest_has_r8_r9_fields(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    for k in ("workflow", "started_at", "container", "repo", "inputs", "model_type",
              "pretrain_mode", "world_size", "args_applied", "arch",
              "save_dir", "logs_dir", "argv", "cmd_replay", "ok_to_replay"):
        assert k in manifest, f"missing top-level field: {k}"
    assert "image_tag" in manifest["container"]
    assert "commit" in manifest["repo"]
    assert isinstance(manifest["repo"]["dirty"], bool)
    assert manifest["cmd_replay"].startswith("CUDA_VISIBLE_DEVICES=") or "WORLD_SIZE=" in manifest["cmd_replay"]


def test_run_json_persisted_to_disk(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    out = tmp_path / "run"
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(out), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    persisted = json.loads((out / "run.json").read_text())
    assert persisted["workflow"] == "continue-pretrain"
    assert persisted["dry_run"] is True


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_missing_prepare_manifest_is_clean_error(tmp_path: Path) -> None:
    ckpt, _, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(tmp_path / "missing.json"),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1
    assert any("not found" in e for e in m["errors"])


def test_wrong_prepare_mode_rejected(tmp_path: Path) -> None:
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    # Mutate the prepare manifest to mode=finetune
    pm = json.loads(prep.read_text())
    pm["mode"] = "finetune"
    prep.write_text(json.dumps(pm))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1
    assert any("mode='finetune'" in e or "expected 'pretrain'" in e for e in m["errors"])


def test_validator_rejection_propagates(tmp_path: Path) -> None:
    ckpt, prep, _ = _setup(tmp_path, "hybrid")
    bad_validator = tmp_path / "bad_validator.json"
    bad_validator.write_text(json.dumps({
        "ok": False, "model_type": "unknown",
        "errors": ["synthetic rejection for the test"],
        "arch": {}, "has_encoder": False, "has_vocab_head": False,
        "has_contrast_head": False, "has_task_ffn": False, "task_output_dims": [],
        "warnings": [],
    }))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(bad_validator),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1
    assert any("rejected" in e for e in m["errors"])


def test_no_gpus_visible_is_clean_error(tmp_path: Path) -> None:
    """--gpus '' (empty) → world_size 0 → reject."""
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "", "--dry-run",
    )
    # With --gpus "" (empty string), the runner falls back to torch.cuda.device_count().
    # On the test host (L4, 1 GPU) that's >0, so the test will pass.
    # If running on a CPU-only host, this would error — that's the intended behavior.
    if code == 1:
        assert any("No GPUs detected" in e for e in m["errors"])
    else:
        assert m["manifest"]["world_size"] >= 1


# ---------------------------------------------------------------------------
# Vocab-size verification (continue-pretrain hardening)
# ---------------------------------------------------------------------------

def test_vocab_size_mismatch_aborts(tmp_path: Path) -> None:
    """ckpt's atom-head expects N entries; the prepare manifest's atom vocab
    has M ≠ N. Runner refuses to launch and points the user at the fix."""
    ckpt, _, _ = _setup(tmp_path, "hybrid")
    # Build a manifest whose atom vocab is sized DIFFERENTLY from the ckpt.
    prep = _make_prepare_manifest(tmp_path, atom_size=100, bond_size=539, smiles_size=60)
    val = _make_validator_out("hybrid", atom_size=311, bond_size=539, smiles_size=60)
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val))
    code, out = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val_path),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1, out
    assert any("vocab size mismatch" in e for e in out["errors"])
    assert any("--vocab-dir" in e for e in out["errors"])


def test_vocab_check_block_present_on_success(tmp_path: Path) -> None:
    """When vocab sizes line up, the run.json gets a `vocab_check` block
    documenting what was compared."""
    ckpt, prep, val = _setup(tmp_path, "hybrid")  # default sizes match (311/539/60)
    code, out = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, out
    m = out["manifest"]
    vc = m["vocab_check"]
    assert vc is not None
    assert vc["atom"]["ckpt_size"] == 311 and vc["atom"]["manifest_size"] == 311
    assert vc["bond"]["ckpt_size"] == 539 and vc["bond"]["manifest_size"] == 539
    assert vc["smiles"]["ckpt_size"] == 60 and vc["smiles"]["manifest_size"] == 60


def test_vocab_check_skips_heads_absent_from_ckpt(tmp_path: Path) -> None:
    """cmim has no atom/bond heads (vocab_sizes.atom = None); runner doesn't
    require atom/bond vocab files in the manifest for that case."""
    ckpt, prep, val = _setup(tmp_path, "cmim")
    code, out = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, out
    vc = out["manifest"]["vocab_check"]
    assert vc["atom"]["ckpt_size"] is None and vc["atom"]["manifest_size"] is None
    assert vc["smiles"]["ckpt_size"] == 60 and vc["smiles"]["manifest_size"] == 60


# ---------------------------------------------------------------------------
# Pretrain-from-scratch
# ---------------------------------------------------------------------------

def test_from_scratch_requires_pretrain_target_mode(tmp_path: Path) -> None:
    prep = _make_prepare_manifest(tmp_path)
    code, out = _run(
        "--from-scratch",
        "--prepare-manifest", str(prep),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1, out
    assert any("--pretrain-target-mode" in e for e in out["errors"])


def test_from_scratch_rejects_ckpt_argument(tmp_path: Path) -> None:
    """--from-scratch + --ckpt is contradictory; reject with a clear error."""
    ckpt, prep, _ = _setup(tmp_path, "hybrid")
    code, out = _run(
        "--from-scratch", "--pretrain-target-mode", "hybrid",
        "--ckpt", str(ckpt),
        "--prepare-manifest", str(prep),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1, out
    assert any("--from-scratch" in e and "--ckpt" in e for e in out["errors"])


def test_from_scratch_vocab_mode_argv(tmp_path: Path) -> None:
    """From-scratch + vocab → workflow=pretrain-scratch, model_type=grover_base,
    --pretrain_mode vocab, no --smiles_vocab_path, no ckpt symlink, arch from
    defaults_pretrain.json."""
    prep = _make_prepare_manifest(tmp_path)
    code, out = _run(
        "--from-scratch", "--pretrain-target-mode", "vocab",
        "--prepare-manifest", str(prep),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, out
    m = out["manifest"]
    assert m["workflow"] == "pretrain-scratch"
    assert m["from_scratch"] is True
    assert m["model_type"] == "grover_base"
    assert m["pretrain_mode"] == "vocab"
    assert m["ckpt_symlink"] is None
    assert m["inputs"]["ckpt"] is None
    assert m["vocab_check"] is None  # not verified for from-scratch
    argv = m["argv"]
    assert argv[argv.index("--pretrain_mode") + 1] == "vocab"
    assert "--smiles_vocab_path" not in argv
    # Arch from defaults_pretrain.json's arch group
    assert m["arch"]["hidden_size"] == 800
    assert m["arch"]["depth"] == 6


def test_from_scratch_hybrid_argv(tmp_path: Path) -> None:
    prep = _make_prepare_manifest(tmp_path)
    code, out = _run(
        "--from-scratch", "--pretrain-target-mode", "hybrid",
        "--prepare-manifest", str(prep),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, out
    m = out["manifest"]
    assert m["model_type"] == "hybrid"
    assert m["pretrain_mode"] == "hybrid"
    argv = m["argv"]
    assert "--smiles_vocab_path" in argv
    assert "--latent_dim" in argv
    assert "--vocab_loss_weight" in argv


def test_continue_pretrain_requires_ckpt(tmp_path: Path) -> None:
    """No --from-scratch + no --ckpt → clean error pointing the user at both options."""
    prep = _make_prepare_manifest(tmp_path)
    code, out = _run(
        "--prepare-manifest", str(prep),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 1, out
    assert any("--ckpt" in e for e in out["errors"])


# ---------------------------------------------------------------------------
# Continue-pretrain mode dispatch: default (fresh-schedule) vs --resume.
# ---------------------------------------------------------------------------

def test_default_mode_is_fresh_schedule(tmp_path: Path) -> None:
    """No --resume + no --from-scratch → continue_pretrain_fresh_schedule. The
    manifest carries the mode field; args_applied for schedule fields comes
    from CLI/default-config, NOT ckpt_saved_args."""
    ckpt, prep, val = _setup(tmp_path, "hybrid")
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val),
        "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["mode"] == "continue_pretrain_fresh_schedule"
    assert manifest["resume_state"] is None
    # Schedule fields come from defaults_pretrain.json, never from ckpt
    for f in ("epochs", "warmup_epochs", "init_lr", "max_lr", "final_lr"):
        if f in manifest["args_applied"]:
            assert manifest["args_applied"][f]["source"] != "ckpt_saved_args"


def test_resume_mode_inherits_schedule_from_saved_args(tmp_path: Path) -> None:
    """--resume sources schedule fields from ckpt.saved_args, marked source
    `ckpt_saved_args` in args_applied. CLI/default values are ignored."""
    saved_sched = {"epochs": 100, "warmup_epochs": 20, "init_lr": 1e-5,
                   "max_lr": 1.5e-4, "final_lr": 1e-5}
    ckpt = _make_synthetic_ckpt(tmp_path, "hybrid",
                                with_resume_state=True,
                                saved_schedule=saved_sched)
    prep = _make_prepare_manifest(tmp_path)
    val_out = _make_validator_out("hybrid")
    # The real validator surfaces saved_args; mirror that in the cached JSON
    # so the runner's overlay finds the schedule values.
    val_out["saved_args"] = {**val_out.get("saved_args", {}), **saved_sched}
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val_out, indent=2))
    code, m = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val_path),
        "--out", str(tmp_path / "run"), "--gpus", "0",
        "--resume", "--dry-run",
    )
    assert code == 0, m
    manifest = m["manifest"]
    assert manifest["mode"] == "continue_pretrain_resume"
    applied = manifest["args_applied"]
    for f, v in saved_sched.items():
        assert applied[f]["source"] == "ckpt_saved_args", f"{f} source wrong"
        assert applied[f]["value"] == v, f"{f} value wrong"
    # resume_state block surfaces what's being restored.
    rs = manifest["resume_state"]
    assert rs["scheduler_step"] == 5000
    assert rs["epoch"] == 3
    assert rs["batch_idx"] == 12
    assert rs["wandb_run_id"] == "wb-test-run-id"


def test_resume_rejects_cli_schedule_override(tmp_path: Path) -> None:
    """--resume + any schedule-arg CLI override → hard error. Pure resume
    means pure resume."""
    ckpt = _make_synthetic_ckpt(tmp_path, "hybrid", with_resume_state=True,
                                saved_schedule={"epochs": 100, "warmup_epochs": 20,
                                                "init_lr": 1e-5, "max_lr": 1.5e-4,
                                                "final_lr": 1e-5})
    prep = _make_prepare_manifest(tmp_path)
    val = _make_validator_out("hybrid")
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val, indent=2))
    code, out = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val_path),
        "--out", str(tmp_path / "run"), "--gpus", "0",
        "--resume", "--epochs", "30", "--dry-run",
    )
    assert code == 1, out
    blob = " ".join(out["errors"])
    assert "--resume" in blob and "schedule" in blob.lower()
    assert "epochs" in blob


def test_resume_requires_ckpt(tmp_path: Path) -> None:
    """--resume without --ckpt → error."""
    prep = _make_prepare_manifest(tmp_path)
    code, out = _run(
        "--prepare-manifest", str(prep),
        "--out", str(tmp_path / "run"), "--gpus", "0",
        "--resume", "--dry-run",
    )
    assert code == 1
    assert any("--resume requires --ckpt" in e for e in out["errors"])


def test_resume_incompatible_with_from_scratch(tmp_path: Path) -> None:
    """--resume + --from-scratch → error (no ckpt to resume from in the
    from-scratch path)."""
    prep = _make_prepare_manifest(tmp_path)
    code, out = _run(
        "--prepare-manifest", str(prep),
        "--out", str(tmp_path / "run"), "--gpus", "0",
        "--from-scratch", "--pretrain-target-mode", "hybrid",
        "--resume", "--dry-run",
    )
    assert code == 1
    assert any("incompatible" in e.lower() and "from-scratch" in e for e in out["errors"])


def test_resume_rejects_ckpt_without_full_state(tmp_path: Path) -> None:
    """A ckpt saved without optimizer / scheduler_step / epoch / batch_idx
    can't be pure-resumed; --resume must fail clearly."""
    ckpt = _make_synthetic_ckpt(tmp_path, "hybrid", with_resume_state=False)
    prep = _make_prepare_manifest(tmp_path)
    val = _make_validator_out("hybrid")
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val, indent=2))
    code, out = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val_path),
        "--out", str(tmp_path / "run"), "--gpus", "0",
        "--resume", "--dry-run",
    )
    assert code == 1, out
    blob = " ".join(out["errors"])
    assert "missing" in blob.lower() or "save_model_for_restart" in blob


def test_resume_rejects_ckpt_without_saved_schedule(tmp_path: Path) -> None:
    """A ckpt that has resume-state but ckpt.args is missing schedule fields
    → --resume can't inherit, so fails cleanly. (Belt-and-suspenders;
    real ckpts always carry these.)"""
    # No saved_schedule passed → ckpt.args lacks epochs / init_lr / etc.
    ckpt = _make_synthetic_ckpt(tmp_path, "hybrid", with_resume_state=True)
    prep = _make_prepare_manifest(tmp_path)
    val = _make_validator_out("hybrid")
    # The validator's saved_args is otherwise-populated but lacks our 5
    # schedule fields. Mirror that here.
    val["saved_args"] = {"hidden_size": 800, "depth": 6}
    val_path = tmp_path / "validator.json"
    val_path.write_text(json.dumps(val, indent=2))
    code, out = _run(
        "--ckpt", str(ckpt), "--prepare-manifest", str(prep),
        "--ckpt-validator-out", str(val_path),
        "--out", str(tmp_path / "run"), "--gpus", "0",
        "--resume", "--dry-run",
    )
    assert code == 1, out
    blob = " ".join(out["errors"])
    assert "saved_args" in blob and "schedule" in blob.lower()


def test_materialize_ckpt_zeroes_resume_counters(tmp_path: Path) -> None:
    """Unit test for _materialize_ckpt_for_fresh_schedule: writes a clean
    copy of the input ckpt with scheduler_step / epoch / batch_idx /
    wandb_run_id reset to 0/None. Model state_dict + optimizer state pass
    through unchanged. Tests the helper directly — the runner's --dry-run
    path skips materialization, so we exercise the helper without launching
    pretrain_ddp.py."""
    # Use the agent/scripts dir + import the helper directly.
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "run_pretrain_local", REPO_ROOT / "agent" / "scripts" / "run_pretrain_local.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_pretrain_local"] = mod
    spec.loader.exec_module(mod)

    src = _make_synthetic_ckpt(tmp_path, "hybrid", with_resume_state=True,
                                saved_schedule={"epochs": 100, "warmup_epochs": 20,
                                                "init_lr": 1e-5, "max_lr": 1.5e-4,
                                                "final_lr": 1e-5})
    src_md5_before = hashlib.md5(src.read_bytes()).hexdigest() if src.exists() else None

    out_save_dir = tmp_path / "out_save"
    target = mod._materialize_ckpt_for_fresh_schedule(src, out_save_dir)

    # Source ckpt unchanged.
    assert hashlib.md5(src.read_bytes()).hexdigest() == src_md5_before

    # Target is a real file (not a symlink), under the requested save_dir.
    assert target == out_save_dir / "last_checkpoint.pt"
    assert target.is_file() and not target.is_symlink()

    # Reload and assert the cleaning.
    cleaned = torch.load(target, map_location="cpu", weights_only=False)
    assert cleaned["scheduler_step"] == 0
    assert cleaned["epoch"] == 0
    assert cleaned["batch_idx"] == 0
    assert cleaned["wandb_run_id"] is None
    # Model + optimizer pass through.
    assert "state_dict" in cleaned
    assert set(cleaned["state_dict"].keys()) == set(torch.load(
        src, map_location="cpu", weights_only=False
    )["state_dict"].keys())
    assert "optimizer" in cleaned
    # Schedule args inside ckpt.args also pass through unchanged (only the
    # top-level resume-counter keys are touched).
    assert cleaned["args"].epochs == 100
    assert cleaned["args"].init_lr == 1e-5


# ---------------------------------------------------------------------------
# End-to-end slow integration test — actually launches pretrain_ddp.py.
# ---------------------------------------------------------------------------
# Skipped by default. To run:
#   KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \
#     "python -m pytest agent/tests/test_run_pretrain_local.py::test_end_to_end_continue_pretrain_default_mode -v --run-slow"
#
# Builds a fake grover_base ckpt whose vocab heads match tests/data/pretrain's
# atom + bond vocab files, then runs run_pretrain_local.py for one full epoch
# on the tiny train_9k / val_1k shards. Verifies:
#   - exit_code == 0, status == "ok"
#   - a new last_checkpoint.pt was written (different from the input fake ckpt)
#   - the user's input ckpt is unchanged (symlink-replacement semantics)
# Runtime: ~5 minutes on a single NVIDIA L4.

def _e2e_prepare_manifest(tmp_path: Path) -> Path:
    """Shared scaffolding for the slow e2e tests: synthesize a prepare_data.json
    pointing at the existing tests/data/pretrain fixture shards. The runner
    sees this as a valid mode=pretrain manifest."""
    fixture_dir = REPO_ROOT / "tests" / "data" / "pretrain"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "ok": True, "mode": "pretrain",
        "output_dir": str(data_dir),
        "split_method": "user_provided",
        "steps": [],
        "outputs": {
            "atom_vocab": str(fixture_dir / "pretrain_atom_vocab.json"),
            "bond_vocab": str(fixture_dir / "pretrain_bond_vocab.json"),
            "train_dir":  str(fixture_dir / "train_9k"),
            "val_dir":    str(fixture_dir / "val_1k"),
        },
        "errors": [], "warnings": [],
    }
    manifest_path = data_dir / "prepare_data.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def _build_fake_grover_base_ckpt(tmp_path: Path, **extra_args: object) -> Path:
    """Invoke _build_fake_ckpt.py to produce a synthetic vocab-only ckpt
    whose vocab heads match the tests/data/pretrain fixture's vocabs.
    extra_args are forwarded as kebab-case CLI flags (e.g.
    `scheduler_step=100` -> `--scheduler-step 100`)."""
    fixture_dir = REPO_ROOT / "tests" / "data" / "pretrain"
    builder = REPO_ROOT / "agent" / "tests" / "_build_fake_ckpt.py"
    fake_ckpt = tmp_path / "fake.pt"
    cli = [
        sys.executable, str(builder),
        "--atom-vocab", str(fixture_dir / "pretrain_atom_vocab.json"),
        "--bond-vocab", str(fixture_dir / "pretrain_bond_vocab.json"),
        "--out", str(fake_ckpt),
    ]
    for k, v in extra_args.items():
        cli += [f"--{k.replace('_', '-')}", str(v)]
    r = subprocess.run(cli, capture_output=True, text=True)
    assert r.returncode == 0, f"builder failed: {r.stderr}\n{r.stdout}"
    assert fake_ckpt.is_file()
    return fake_ckpt


@pytest.mark.slow
def test_end_to_end_continue_pretrain_default_mode(tmp_path: Path) -> None:
    """Default-mode (fresh-schedule) continue-pretrain e2e: load model +
    optimizer from the input ckpt, but discard scheduler_step / epoch /
    batch_idx so a fresh NoamLR is used."""
    fake_ckpt = _build_fake_grover_base_ckpt(tmp_path)
    user_ckpt_md5_before = hashlib.md5(fake_ckpt.read_bytes()).hexdigest()
    manifest_path = _e2e_prepare_manifest(tmp_path)

    code, out = _run(
        "--ckpt", str(fake_ckpt),
        "--prepare-manifest", str(manifest_path),
        "--out", str(tmp_path / "run"),
        "--gpus", "0",
        "--epochs", "1", "--save-interval", "100", "--warmup-epochs", "0",
        "--batch-size", "32",
    )
    assert code == 0, f"runner exited {code} with: {out}"
    run_manifest = out["manifest"]
    assert run_manifest["status"] == "ok", run_manifest
    assert run_manifest["exit_code"] == 0
    # New: manifest carries the mode field; default mode is fresh-schedule.
    assert run_manifest["mode"] == "continue_pretrain_fresh_schedule"
    assert run_manifest["resume_state"] is None
    # Schedule args came from CLI/defaults, NOT ckpt.saved_args.
    for f in ("epochs", "warmup_epochs", "init_lr", "max_lr", "final_lr"):
        if f in run_manifest["args_applied"]:
            assert run_manifest["args_applied"][f]["source"] != "ckpt_saved_args"

    # The final ckpt at <save_dir>/last_checkpoint.pt is a real file (written by
    # pretrain_ddp.py's save_checkpoint).
    final_ckpt = tmp_path / "run" / "ckpt" / "last_checkpoint.pt"
    assert final_ckpt.is_file() and not final_ckpt.is_symlink()
    assert final_ckpt.stat().st_size > fake_ckpt.stat().st_size

    # User's input ckpt was NOT modified.
    assert hashlib.md5(fake_ckpt.read_bytes()).hexdigest() == user_ckpt_md5_before

    # Verify the materialized starting point had zeroed counters (the runner
    # writes this before pretrain_ddp.py runs; pretrain_ddp.py then overwrites
    # it with the saved state at first save_interval). We can detect by
    # checking the log shows "Loading checkpoint from ..." followed by
    # "epoch=0, scheduler_step=0, prev_batch_idx=0".
    log_path = tmp_path / "run" / "logs" / "pretrain_ddp.log"
    log_text = log_path.read_text()
    assert "epoch=0, scheduler_step=0, prev_batch_idx=0" in log_text, (
        "fresh-schedule mode should restore from a zeroed-counter ckpt, "
        f"got log:\n{log_text[:2000]}"
    )


@pytest.mark.slow
def test_end_to_end_from_scratch_vocab_only(tmp_path: Path) -> None:
    """From-scratch e2e: no input ckpt, fresh model built from defaults_pretrain
    arch + the corpus-side vocab. Verifies the from-scratch path still works
    after the mode-dispatch changes."""
    manifest_path = _e2e_prepare_manifest(tmp_path)

    code, out = _run(
        # No --ckpt; --from-scratch.
        "--from-scratch", "--pretrain-target-mode", "vocab",
        "--prepare-manifest", str(manifest_path),
        "--out", str(tmp_path / "run"),
        "--gpus", "0",
        "--epochs", "1", "--save-interval", "100", "--warmup-epochs", "0",
        "--batch-size", "32",
    )
    assert code == 0, f"runner exited {code} with: {out}"
    run_manifest = out["manifest"]
    assert run_manifest["status"] == "ok", run_manifest
    assert run_manifest["exit_code"] == 0
    assert run_manifest["mode"] == "pretrain_from_scratch"
    assert run_manifest["resume_state"] is None
    assert run_manifest["workflow"] == "pretrain-scratch"
    # The runner's manifest records no input ckpt for from-scratch.
    assert run_manifest["inputs"]["ckpt"] is None
    assert run_manifest["ckpt_symlink"] is None

    # pretrain_ddp.py wrote a fresh ckpt (no auto-resume since no
    # last_checkpoint.pt existed at start).
    final_ckpt = tmp_path / "run" / "ckpt" / "last_checkpoint.pt"
    assert final_ckpt.is_file()
    log_path = tmp_path / "run" / "logs" / "pretrain_ddp.log"
    log_text = log_path.read_text()
    # In from-scratch, pretrain_ddp.py should NOT print "Loading checkpoint".
    assert "Loading checkpoint from" not in log_text, (
        "from-scratch should not auto-resume, but log shows resume:\n"
        f"{log_text[:2000]}"
    )


@pytest.mark.slow
def test_end_to_end_resume_picks_up_mid_run(tmp_path: Path) -> None:
    """--resume e2e: build a ckpt with nonzero scheduler_step + batch_idx,
    pretend training was interrupted mid-epoch, --resume should restore those
    counters and pretrain_ddp.py's log should show the loaded mid-run state."""
    # Bake mid-run state into the fake ckpt. Schedule args (epochs=1,
    # warmup_epochs=0, etc.) live in ckpt.args so --resume's saved_args
    # inheritance works.
    fake_ckpt = _build_fake_grover_base_ckpt(
        tmp_path,
        epochs=1, warmup_epochs=0,
        init_lr=1e-5, max_lr=1e-4, final_lr=1e-5,
        scheduler_step=100, batch_idx=100,
    )
    manifest_path = _e2e_prepare_manifest(tmp_path)

    code, out = _run(
        "--ckpt", str(fake_ckpt),
        "--prepare-manifest", str(manifest_path),
        "--out", str(tmp_path / "run"),
        "--gpus", "0",
        "--batch-size", "32",
        "--save-interval", "100",
        # NO --epochs / --warmup-epochs / etc. — --resume mode forbids those.
        # Schedule args inherited from the ckpt's saved_args.
        "--resume",
    )
    assert code == 0, f"runner exited {code} with: {out}"
    run_manifest = out["manifest"]
    assert run_manifest["status"] == "ok", run_manifest
    assert run_manifest["exit_code"] == 0
    assert run_manifest["mode"] == "continue_pretrain_resume"

    # Schedule args came from ckpt.saved_args (set by the builder above).
    for f in ("epochs", "warmup_epochs", "init_lr", "max_lr", "final_lr"):
        assert run_manifest["args_applied"][f]["source"] == "ckpt_saved_args", (
            f"--resume should source {f} from ckpt.saved_args, got "
            f"{run_manifest['args_applied'].get(f)}"
        )
    assert run_manifest["args_applied"]["epochs"]["value"] == 1
    assert run_manifest["args_applied"]["warmup_epochs"]["value"] == 0.0

    # resume_state reflects what was baked into the ckpt.
    rs = run_manifest["resume_state"]
    assert rs["scheduler_step"] == 100, rs
    assert rs["batch_idx"] == 100, rs
    assert rs["epoch"] == 0, rs

    # The symlink approach is used in --resume mode. Note that pretrain_ddp.py's
    # save_checkpoint uses os.replace to overwrite, so the final
    # last_checkpoint.pt may be a real file (not symlink) after training
    # writes its own save. We check the log instead for proof of resume.
    log_path = tmp_path / "run" / "logs" / "pretrain_ddp.log"
    log_text = log_path.read_text()
    # pretrain_ddp.py's loader prints this exact line at line ~715.
    assert "epoch=0, scheduler_step=100, prev_batch_idx=100" in log_text, (
        "--resume should preserve scheduler_step/batch_idx from ckpt, "
        f"got log:\n{log_text[:2000]}"
    )
    # The runner's mid-epoch-resume info line should also fire.
    assert "Resuming mid-epoch: skipping first 100 batches" in log_text, (
        "expected sampler-skip log line for mid-epoch resume, "
        f"got log:\n{log_text[:2000]}"
    )

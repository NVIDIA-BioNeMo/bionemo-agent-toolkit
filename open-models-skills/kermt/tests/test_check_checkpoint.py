# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/check_checkpoint.py.

Builds synthetic minimal checkpoint dicts that mirror the save_model_for_restart
format (a dict containing 'args' Namespace + 'state_dict' with the conventional
key prefixes). Each test exercises one classification path + one mode contract,
or one arch-derivation branch.

Run from the kermt repo root:
    pytest agent/tests/test_check_checkpoint.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
import torch


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_checkpoint.py"


# ---------------------------------------------------------------------------
# Fixtures: minimal state_dicts for each classification.
# ---------------------------------------------------------------------------

def _encoder_keys(prefix: str = "kermt") -> dict[str, torch.Tensor]:
    """A handful of plausible encoder weights, sized to expose hidden_size=800."""
    return {
        f"{prefix}.encoder.linear_0.weight": torch.zeros(800, 133),
        f"{prefix}.encoder.linear_0.bias": torch.zeros(800),
        f"{prefix}.encoder.attention.weight": torch.zeros(800, 800),
    }


def _vocab_module_keys(atom_size: int = 311, bond_size: int = 539) -> dict[str, torch.Tensor]:
    """Mirror the real vocab-head naming from kermt/model/models.py:
    av_task_atom + av_task_bond predict atom-vocab labels (output dim = atom_size);
    bv_task_atom + bv_task_bond predict bond-vocab labels (output dim = bond_size)."""
    return {
        "vocab_module.av_task_atom.0.weight": torch.zeros(atom_size, 800),
        "vocab_module.av_task_atom.0.bias": torch.zeros(atom_size),
        "vocab_module.av_task_bond.0.weight": torch.zeros(atom_size, 800),
        "vocab_module.av_task_bond.0.bias": torch.zeros(atom_size),
        "vocab_module.bv_task_atom.0.weight": torch.zeros(bond_size, 800),
        "vocab_module.bv_task_atom.0.bias": torch.zeros(bond_size),
        "vocab_module.bv_task_bond.0.weight": torch.zeros(bond_size, 800),
        "vocab_module.bv_task_bond.0.bias": torch.zeros(bond_size),
    }


def _latent_decoder_keys(smiles_size: int = 60) -> dict[str, torch.Tensor]:
    return {
        "latent_dist.mean_layer.weight": torch.zeros(800, 800),
        "latent_dist.mean_layer.bias": torch.zeros(800),
        "latent_dist.logvar_layer.weight": torch.zeros(800, 800),
        "decoder.embedding.weight": torch.zeros(smiles_size, 800),
        "decoder.output_projection.weight": torch.zeros(smiles_size, 800),
        "decoder.transformer.0.weight": torch.zeros(800, 800),
    }


def _finetune_ffn_keys(num_tasks: int = 4) -> dict[str, torch.Tensor]:
    """FFN heads sized so final-Linear out-dim = num_tasks."""
    return {
        "readout.attn.0.weight": torch.zeros(4, 800),
        "mol_atom_from_atom_ffn.0.weight": torch.zeros(700, 800),
        "mol_atom_from_atom_ffn.0.bias": torch.zeros(700),
        "mol_atom_from_atom_ffn.3.weight": torch.zeros(num_tasks, 700),
        "mol_atom_from_atom_ffn.3.bias": torch.zeros(num_tasks),
        "mol_atom_from_bond_ffn.0.weight": torch.zeros(700, 800),
        "mol_atom_from_bond_ffn.3.weight": torch.zeros(num_tasks, 700),
    }


def _make_args(**overrides) -> Namespace:
    """Reasonable defaults matching agent/config/defaults_pretrain.json."""
    defaults = {
        "hidden_size": 800,
        "depth": 6,
        "num_attn_head": 4,
        "latent_dim": 800,
        "activation": "PReLU",
        "backbone": "gtrans",
        "embedding_output_type": "both",
        "self_attention": True,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def _write_ckpt(tmp_path: Path, state_dict: dict, args=None, name: str = "ckpt.pt") -> Path:
    path = tmp_path / name
    torch.save({"args": args, "state_dict": state_dict}, path)
    return path


def _run(ckpt_path: Path, mode: str) -> tuple[int, dict]:
    """Invoke the validator via subprocess (the way the skill would). Returns (exit_code, parsed_json)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", mode, "--ckpt", str(ckpt_path)],
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc.returncode, payload


# ---------------------------------------------------------------------------
# Classification tests — one per model_type.
# ---------------------------------------------------------------------------

def test_grover_base_classification(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_vocab_module_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0, out
    assert out["ok"] is True
    assert out["model_type"] == "grover_base"
    assert out["has_encoder"] and out["has_vocab_head"]
    assert not out["has_contrast_head"] and not out["has_task_ffn"]


def test_legacy_grover_prefix_recognized_as_encoder(tmp_path: Path) -> None:
    """Pre-cMIM grover_base ckpts use the `grover.*` prefix, not `kermt.*`.
    The validator must accept both as encoder weights AND classify the ckpt as
    'grover_base' (the model_type the user expects, not 'unknown')."""
    sd = _encoder_keys(prefix="grover")
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args(backbone="dualtrans"))
    code, out = _run(ckpt, "upgrade_to_hybrid")  # encoder-only ckpt is the canonical input
    assert code == 0, out
    assert out["has_encoder"] is True
    assert out["model_type"] == "grover_base"
    assert out["has_vocab_head"] is False
    assert out["arch"]["hidden_size"] == 800


def test_encoder_only_modern_prefix_classified_as_grover_base(tmp_path: Path) -> None:
    """A modern (kermt.*-prefixed) ckpt with encoder weights but no heads still
    classifies as grover_base — same as a legacy grover.*-prefixed one. The
    has_vocab_head flag distinguishes the sub-case from a 'with-vocab' grover_base."""
    sd = _encoder_keys(prefix="kermt")
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "upgrade_to_hybrid")
    assert code == 0, out
    assert out["model_type"] == "grover_base"
    assert out["has_vocab_head"] is False


def test_cmim_classification(tmp_path: Path) -> None:
    # cmim: encoder lives inside latent_dist
    sd = {**_encoder_keys(prefix="latent_dist.kermt"), **_latent_decoder_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0, out
    assert out["model_type"] == "cmim"
    assert out["has_encoder"] and out["has_contrast_head"]
    assert not out["has_vocab_head"]


def test_hybrid_classification(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_vocab_module_keys(), **_latent_decoder_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0, out
    assert out["model_type"] == "hybrid"
    assert out["has_encoder"] and out["has_vocab_head"] and out["has_contrast_head"]


def test_finetuned_classification(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_finetune_ffn_keys(num_tasks=4)}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "inference")
    assert code == 0, out
    assert out["model_type"] == "finetuned"
    assert out["has_encoder"] and out["has_task_ffn"]
    assert out["task_output_dims"] == [4, 4]  # one per FFN head


def test_finetuned_mtl_task_output_dims_excludes_shared_ffn(tmp_path: Path) -> None:
    """When task-specific FFN heads exist, task_output_dims must report ONLY the
    task-specific head out-dims — the shared FFN is intermediate, not model output.
    Mirrors the Biogen MTL config (4 tasks x 2 readouts x 1-dim regression out)."""
    sd = {**_encoder_keys(), **_finetune_ffn_keys(num_tasks=4)}
    # Add MTL task-specific heads: 4 tasks x 2 readouts, each ending in Linear(700, 1).
    for readout in ("mol_atom_from_atom_ffn_task_specific", "mol_atom_from_bond_ffn_task_specific"):
        for task_idx in range(4):
            sd[f"{readout}.{task_idx}.5.weight"] = torch.zeros(1, 700)
            sd[f"{readout}.{task_idx}.5.bias"] = torch.zeros(1)
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "inference")
    assert code == 0, out
    assert out["has_task_ffn"]
    # 4 tasks x 2 readouts = 8 task-specific heads, each with out-dim 1.
    assert out["task_output_dims"] == [1] * 8, out["task_output_dims"]


# ---------------------------------------------------------------------------
# Mode-contract tests — wrong ckpt type for the asked mode must error.
# ---------------------------------------------------------------------------

def test_continue_pretrain_rejects_encoder_only_ckpt(tmp_path: Path) -> None:
    """encoder-only ckpt (no pretrain heads) should fail continue_pretrain and
    suggest upgrade_to_hybrid."""
    sd = _encoder_keys()
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 1
    assert out["ok"] is False
    assert any("upgrade_to_hybrid" in e for e in out["errors"])


def test_continue_pretrain_rejects_finetuned_ckpt(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_finetune_ffn_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 1
    assert any("task FFN" in e or "finetuned" in e for e in out["errors"])


def test_upgrade_to_hybrid_rejects_already_hybrid(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_vocab_module_keys(), **_latent_decoder_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "upgrade_to_hybrid")
    assert code == 1
    assert any("continue_pretrain" in e for e in out["errors"])


def test_upgrade_to_hybrid_accepts_grover_base(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_vocab_module_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "upgrade_to_hybrid")
    assert code == 0, out
    assert out["ok"] is True


def test_inference_rejects_pretrain_ckpt(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_vocab_module_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "inference")
    assert code == 1
    assert any("task FFN" in e or "finetune" in e for e in out["errors"])


def test_embed_accepts_any_encoder_bearing_ckpt(tmp_path: Path) -> None:
    """embed mode is the most permissive — encoder alone is enough."""
    sd = _encoder_keys()
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "embed")
    assert code == 0, out
    assert out["ok"] is True


def test_finetune_init_accepts_pretrain_ckpt(tmp_path: Path) -> None:
    """A pretrain ckpt is the canonical input to finetune."""
    sd = {**_encoder_keys(), **_vocab_module_keys(), **_latent_decoder_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "finetune_init")
    assert code == 0, out
    assert out["ok"] is True


def test_finetune_init_rejects_finetuned_ckpt(tmp_path: Path) -> None:
    """An already-finetuned ckpt (task FFN heads present) is rejected by
    finetune_init: finetune-on-finetune via the agent skill isn't supported
    because saved-task identity can't be machine-verified against the
    new training data. The error message points at the manual escape hatch."""
    sd = {**_encoder_keys(), **_finetune_ffn_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "finetune_init")
    assert code == 1
    err_blob = " ".join(out["errors"])
    assert "finetune_init requires a pretrain ckpt" in err_blob
    assert "finetuned" in err_blob
    # The error must point users at the manual escape hatch.
    assert "main.py finetune" in err_blob


# ---------------------------------------------------------------------------
# Arch-derivation tests — args-primary path and shape-fallback path.
# ---------------------------------------------------------------------------

def test_arch_from_args(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_vocab_module_keys()}
    args = _make_args(hidden_size=512, depth=8, latent_dim=256)
    ckpt = _write_ckpt(tmp_path, sd, args=args)
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0
    assert out["arch"]["hidden_size"] == 512
    assert out["arch"]["depth"] == 8
    assert out["arch"]["latent_dim"] == 256
    assert out["arch"]["activation"] == "PReLU"


def test_arch_shape_fallback_when_args_missing(tmp_path: Path) -> None:
    """When args is None, hidden_size + latent_dim should still be inferred from shapes;
    activation/backbone/etc. should be None with warnings."""
    sd = {**_encoder_keys(), **_vocab_module_keys(), **_latent_decoder_keys()}
    ckpt = _write_ckpt(tmp_path, sd, args=None)
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0, out
    assert out["arch"]["hidden_size"] == 800   # inferred from encoder weight
    assert out["arch"]["latent_dim"] == 800    # inferred from latent_dist.mean_layer
    assert out["arch"]["activation"] is None   # not inferable from shapes
    assert out["arch"]["backbone"] is None
    assert any("activation" in w for w in out["warnings"])


def test_ddp_module_prefix_is_stripped(tmp_path: Path) -> None:
    """A DDP-wrapped save has every key prefixed with 'module.' — must still classify correctly."""
    base = {**_encoder_keys(), **_vocab_module_keys()}
    wrapped = {f"module.{k}": v for k, v in base.items()}
    ckpt = _write_ckpt(tmp_path, wrapped, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0, out
    assert out["model_type"] == "grover_base"


# ---------------------------------------------------------------------------
# Error-path tests — bad inputs surface clean JSON, not Python tracebacks.
# ---------------------------------------------------------------------------

def test_missing_file_emits_clean_error_json(tmp_path: Path) -> None:
    code, out = _run(tmp_path / "does_not_exist.pt", "continue_pretrain")
    assert code == 1
    assert out["ok"] is False
    assert any("not found" in e for e in out["errors"])


def test_wrong_format_ckpt_emits_clean_error(tmp_path: Path) -> None:
    """A torch.save'd tensor (not a save_model_for_restart dict) should be rejected cleanly."""
    bogus = tmp_path / "bogus.pt"
    torch.save(torch.zeros(3, 3), bogus)
    code, out = _run(bogus, "continue_pretrain")
    assert code == 1
    assert any("expected" in e.lower() or "state_dict" in e for e in out["errors"])


def test_unknown_mode_via_subparser_rejected() -> None:
    """The argparse layer should reject an unknown mode before validate() runs."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", "bogus", "--ckpt", "/tmp/nope.pt"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "invalid choice" in proc.stderr.lower()


# ---------------------------------------------------------------------------
# vocab_sizes extraction (vocab pass-through alignment)
# ---------------------------------------------------------------------------

def test_vocab_sizes_grover_base(tmp_path: Path) -> None:
    sd = {**_encoder_keys(), **_vocab_module_keys(atom_size=311, bond_size=539)}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0
    assert out["vocab_sizes"] == {"atom": 311, "bond": 539, "smiles": None}


def test_vocab_sizes_hybrid(tmp_path: Path) -> None:
    sd = {
        **_encoder_keys(),
        **_vocab_module_keys(atom_size=400, bond_size=600),
        **_latent_decoder_keys(smiles_size=70),
    }
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0
    assert out["vocab_sizes"] == {"atom": 400, "bond": 600, "smiles": 70}


def test_vocab_sizes_cmim_has_smiles_only(tmp_path: Path) -> None:
    """cmim has no atom/bond vocab heads, only the smiles decoder."""
    sd = {**_encoder_keys(prefix="latent_dist.kermt"), **_latent_decoder_keys(smiles_size=80)}
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "continue_pretrain")
    assert code == 0
    assert out["vocab_sizes"]["atom"] is None
    assert out["vocab_sizes"]["bond"] is None
    assert out["vocab_sizes"]["smiles"] == 80


def test_vocab_sizes_encoder_only_grover_all_none(tmp_path: Path) -> None:
    """Legacy encoder-only grover_base has no heads at all."""
    sd = _encoder_keys(prefix="grover")
    ckpt = _write_ckpt(tmp_path, sd, args=_make_args())
    code, out = _run(ckpt, "upgrade_to_hybrid")
    assert code == 0
    assert out["vocab_sizes"] == {"atom": None, "bond": None, "smiles": None}

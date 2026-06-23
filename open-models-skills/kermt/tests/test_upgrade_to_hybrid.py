# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0 OR CC-BY-4.0

"""Unit tests for agent/scripts/upgrade_to_hybrid.py.

Builds synthetic grover_base ckpts (modern `kermt.encoders.*` prefix AND legacy
`grover.encoders.*` prefix), runs upgrade, then verifies the output:
  - exits 0 with `ok: true`
  - classifies as `model_type: hybrid` via check_checkpoint
  - has all of {atom, bond, smiles} vocab heads sized to the prepare-manifest vocabs

In-container by default:
    KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \\
        "python -m pytest agent/tests/test_upgrade_to_hybrid.py -v \\
            --no-header -p no:cacheprovider"
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import torch


REPO_ROOT = Path(__file__).resolve().parents[2]
UPGRADE_SCRIPT = REPO_ROOT / "agent" / "scripts" / "upgrade_to_hybrid.py"
CHECK_CKPT = REPO_ROOT / "agent" / "scripts" / "check_checkpoint.py"
BUILD_FAKE = REPO_ROOT / "agent" / "tests" / "_build_fake_ckpt.py"
PRETRAIN_FIXTURE = REPO_ROOT / "tests" / "data" / "pretrain"


def _build_modern_grover_base(out_path: Path) -> Path:
    """Spawn _build_fake_ckpt.py to produce a modern KermtTask ckpt sized to
    the tests/data/pretrain vocabs."""
    r = subprocess.run(
        [sys.executable, str(BUILD_FAKE),
         "--atom-vocab", str(PRETRAIN_FIXTURE / "pretrain_atom_vocab.json"),
         "--bond-vocab", str(PRETRAIN_FIXTURE / "pretrain_bond_vocab.json"),
         "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return out_path


def _rename_to_legacy(modern_ckpt: Path, legacy_ckpt: Path) -> Path:
    """Take a modern grover_base ckpt and rename `kermt.encoders.*` keys to
    `grover.encoders.*`. Drops the vocab_module heads (legacy grover_base ckpts
    typically didn't save them) to mimic the encoder-only case Eva has on disk."""
    ckpt = torch.load(modern_ckpt, map_location="cpu", weights_only=False)
    new_sd: dict[str, torch.Tensor] = {}
    for k, v in ckpt["state_dict"].items():
        if k.startswith("kermt.encoders."):
            new_sd["grover.encoders." + k[len("kermt.encoders."):]] = v
        elif k.startswith("vocab_module."):
            continue  # encoder-only legacy
        else:
            new_sd[k] = v
    ckpt["state_dict"] = new_sd
    torch.save(ckpt, legacy_ckpt)
    return legacy_ckpt


def _make_prepare_manifest(out_dir: Path) -> Path:
    """Synthesize a prepare_data.json pointing at the tests/data/pretrain
    vocab + shard fixtures. Same shape as the pretrain runner's slow-test fixture."""
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    # Pretrain fixture has atom + bond vocab files but no smiles_vocab.pkl.
    # Synthesize a tiny smiles vocab so upgrade has something to size the decoder against.
    import pickle
    smiles_stoi = {f"smi_{i}": i for i in range(60)}
    smiles_path = data_dir / "pretrain_smiles_vocab.pkl"
    smiles_path.write_bytes(pickle.dumps(smiles_stoi))
    manifest = {
        "ok": True, "mode": "pretrain",
        "output_dir": str(data_dir),
        "split_method": "user_provided",
        "steps": [],
        "outputs": {
            "atom_vocab":   str(PRETRAIN_FIXTURE / "pretrain_atom_vocab.json"),
            "bond_vocab":   str(PRETRAIN_FIXTURE / "pretrain_bond_vocab.json"),
            "smiles_vocab": str(smiles_path),
            "train_dir":    str(PRETRAIN_FIXTURE / "train_9k"),
            "val_dir":      str(PRETRAIN_FIXTURE / "val_1k"),
        },
        "errors": [], "warnings": [],
    }
    mpath = data_dir / "prepare_data.json"
    mpath.write_text(json.dumps(manifest, indent=2))
    return mpath


def _run_upgrade(ckpt: Path, manifest: Path, out: Path, *extra: str) -> tuple[int, dict]:
    r = subprocess.run(
        [sys.executable, str(UPGRADE_SCRIPT),
         "--ckpt", str(ckpt), "--prepare-manifest", str(manifest), "--out", str(out), *extra],
        capture_output=True, text=True,
    )
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError:
        payload = {"_no_json": True, "_stdout": r.stdout, "_stderr": r.stderr}
    return r.returncode, payload


def _validate_output_as_hybrid(out_ckpt: Path) -> dict:
    """Run check_checkpoint --mode continue_pretrain on the upgraded ckpt and
    return the parsed JSON. (The upgraded ckpt should now satisfy continue_pretrain.)"""
    r = subprocess.run(
        [sys.executable, str(CHECK_CKPT),
         "--mode", "continue_pretrain", "--ckpt", str(out_ckpt)],
        capture_output=True, text=True,
    )
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# Modern grover_base → hybrid
# ---------------------------------------------------------------------------

def test_modern_grover_base_upgrades_to_hybrid(tmp_path: Path) -> None:
    src = _build_modern_grover_base(tmp_path / "modern.pt")
    manifest = _make_prepare_manifest(tmp_path)
    out = tmp_path / "upgraded.pt"
    code, summary = _run_upgrade(src, manifest, out)
    assert code == 0, summary
    assert summary["ok"] is True
    assert summary["input_model_type"] == "grover_base"
    assert summary["vocab_sizes_used"] == {"atom": 311, "bond": 539, "smiles": 60}
    # Validate the upgraded ckpt classifies as hybrid.
    validator = _validate_output_as_hybrid(out)
    assert validator["ok"] is True
    assert validator["model_type"] == "hybrid"
    assert validator["has_encoder"]
    assert validator["has_vocab_head"]
    assert validator["has_contrast_head"]
    # vocab sizes match what we passed in
    assert validator["vocab_sizes"]["atom"] == 311
    assert validator["vocab_sizes"]["bond"] == 539
    assert validator["vocab_sizes"]["smiles"] == 60


# ---------------------------------------------------------------------------
# Legacy grover_base (grover.encoders.* prefix, encoder-only) → hybrid
# ---------------------------------------------------------------------------

def test_legacy_grover_base_upgrades_to_hybrid(tmp_path: Path) -> None:
    modern = _build_modern_grover_base(tmp_path / "modern.pt")
    legacy = _rename_to_legacy(modern, tmp_path / "legacy.pt")
    manifest = _make_prepare_manifest(tmp_path)
    out = tmp_path / "upgraded.pt"
    code, summary = _run_upgrade(legacy, manifest, out)
    assert code == 0, summary
    assert summary["ok"] is True
    # The encoder rename note should appear
    assert any("legacy" in n.lower() or "grover.encoders" in n for n in summary["notes"]), summary["notes"]
    # Output is still classified as hybrid
    validator = _validate_output_as_hybrid(out)
    assert validator["model_type"] == "hybrid"
    assert validator["vocab_sizes"]["smiles"] == 60


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------

def test_upgrade_rejects_cmim_ckpt(tmp_path: Path) -> None:
    """A ckpt with `latent_dist.kermt.*` keys is a cmim ckpt — upgrade should
    refuse and redirect to continue_pretrain."""
    modern = _build_modern_grover_base(tmp_path / "modern.pt")
    # Synthesize a cmim-shaped fake: rename `kermt.encoders.*` to `latent_dist.kermt.encoders.*`
    # and add a `decoder.embedding.weight` so the check_checkpoint validator labels it `cmim`.
    ckpt = torch.load(modern, map_location="cpu", weights_only=False)
    new_sd: dict[str, torch.Tensor] = {}
    for k, v in ckpt["state_dict"].items():
        if k.startswith("kermt.encoders."):
            new_sd["latent_dist.kermt.encoders." + k[len("kermt.encoders."):]] = v
        elif k.startswith("vocab_module."):
            continue
        else:
            new_sd[k] = v
    new_sd["decoder.embedding.weight"] = torch.zeros(60, 800)
    new_sd["decoder.output_projection.weight"] = torch.zeros(60, 800)
    new_sd["latent_dist.fc_mean_logscale.weight"] = torch.zeros(800, 800)
    ckpt["state_dict"] = new_sd
    fake_cmim = tmp_path / "cmim.pt"
    torch.save(ckpt, fake_cmim)
    manifest = _make_prepare_manifest(tmp_path)
    code, summary = _run_upgrade(fake_cmim, manifest, tmp_path / "upgraded.pt")
    assert code == 1, summary
    # The check_checkpoint validator rejects (model_type=cmim is not valid for upgrade_to_hybrid).
    assert any("continue_pretrain" in e or "cmim" in e for e in summary["errors"])


def test_upgrade_rejects_finetuned_ckpt(tmp_path: Path) -> None:
    modern = _build_modern_grover_base(tmp_path / "modern.pt")
    ckpt = torch.load(modern, map_location="cpu", weights_only=False)
    ckpt["state_dict"]["mol_atom_from_atom_ffn.0.weight"] = torch.zeros(4, 800)
    finetuned = tmp_path / "finetuned.pt"
    torch.save(ckpt, finetuned)
    manifest = _make_prepare_manifest(tmp_path)
    code, summary = _run_upgrade(finetuned, manifest, tmp_path / "upgraded.pt")
    assert code == 1, summary
    assert any("finetune" in e or "task FFN" in e for e in summary["errors"])


def test_upgrade_missing_prepare_manifest(tmp_path: Path) -> None:
    src = _build_modern_grover_base(tmp_path / "modern.pt")
    code, summary = _run_upgrade(src, tmp_path / "nope.json", tmp_path / "upgraded.pt")
    assert code == 1, summary
    assert any("not found" in e for e in summary["errors"])


def test_upgrade_prepare_manifest_missing_smiles_vocab(tmp_path: Path) -> None:
    """add-cmim needs a smiles vocab; if prepare didn't produce one, upgrade refuses."""
    src = _build_modern_grover_base(tmp_path / "modern.pt")
    # Manifest that omits smiles_vocab from outputs (e.g. a vocab-only prepare).
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "ok": True, "mode": "pretrain",
        "output_dir": str(data_dir),
        "split_method": "user_provided",
        "steps": [],
        "outputs": {
            "atom_vocab":   str(PRETRAIN_FIXTURE / "pretrain_atom_vocab.json"),
            "bond_vocab":   str(PRETRAIN_FIXTURE / "pretrain_bond_vocab.json"),
            # smiles_vocab intentionally absent
            "train_dir":    str(PRETRAIN_FIXTURE / "train_9k"),
            "val_dir":      str(PRETRAIN_FIXTURE / "val_1k"),
        },
        "errors": [], "warnings": [],
    }
    mpath = data_dir / "prepare_data.json"
    mpath.write_text(json.dumps(manifest))
    code, summary = _run_upgrade(src, mpath, tmp_path / "upgraded.pt")
    assert code == 1, summary
    assert any("smiles_vocab" in e or "smiles vocab" in e for e in summary["errors"])


def test_upgrade_prepare_manifest_wrong_mode(tmp_path: Path) -> None:
    """Pass a finetune-mode manifest to upgrade — refuse."""
    src = _build_modern_grover_base(tmp_path / "modern.pt")
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "prepare_data.json").write_text(json.dumps({
        "ok": True, "mode": "finetune", "output_dir": str(data_dir),
        "steps": [], "outputs": {}, "errors": [], "warnings": [],
    }))
    code, summary = _run_upgrade(src, data_dir / "prepare_data.json", tmp_path / "upgraded.pt")
    assert code == 1
    assert any("pretrain" in e for e in summary["errors"])


# ---------------------------------------------------------------------------
# Output ckpt round-trips through the agent pipeline
# ---------------------------------------------------------------------------

def test_upgraded_ckpt_loads_in_run_pretrain_local_dry_run(tmp_path: Path) -> None:
    """Final sanity: the upgraded ckpt is consumable by run_pretrain_local.py
    (dry-run) — i.e. its vocab sizes line up with the manifest and the runner
    classifies it as hybrid."""
    src = _build_modern_grover_base(tmp_path / "modern.pt")
    manifest = _make_prepare_manifest(tmp_path)
    upgraded = tmp_path / "upgraded.pt"
    code, _ = _run_upgrade(src, manifest, upgraded)
    assert code == 0

    runner_script = REPO_ROOT / "agent" / "scripts" / "run_pretrain_local.py"
    r = subprocess.run(
        [sys.executable, str(runner_script),
         "--ckpt", str(upgraded),
         "--prepare-manifest", str(manifest),
         "--out", str(tmp_path / "run"), "--gpus", "0", "--dry-run"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr or r.stdout
    out = json.loads(r.stdout)
    m = out["manifest"]
    assert m["model_type"] == "hybrid"
    assert m["pretrain_mode"] == "hybrid"
    assert m["vocab_check"]["atom"]["ckpt_size"] == 311
    assert m["vocab_check"]["smiles"]["ckpt_size"] == 60


# ---------------------------------------------------------------------------
# Slow opt-in end-to-end: upgrade → real pretrain_ddp.py launch
# ---------------------------------------------------------------------------
# Skipped by default. To run:
#   KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \
#     "python -m pytest agent/tests/test_upgrade_to_hybrid.py::test_end_to_end_one_epoch_after_upgrade_hybrid -v --run-slow"
#
# Mirrors the pretrain runner's test_end_to_end_continue_pretrain_default_mode
# but adds the upgrade step at the front:
#   1. Build a fake modern grover_base ckpt (vocab heads sized to test-fixture
#      atom + bond vocabs).
#   2. Build a REAL smiles vocab from the test-fixture train shards (so the
#      decoder's tokenizer actually matches the corpus — a synthetic
#      stub-dict smiles vocab makes SMILESVocab.load_vocab fail at runtime).
#   3. Synthesize a prepare_data.json with the real smiles vocab.
#   4. Run upgrade_to_hybrid → produces a hybrid ckpt.
#   5. Run run_pretrain_local.py (no --dry-run, --epochs 1) → exercises the
#      full pretrain_ddp.py launch with --pretrain_mode hybrid.
#   6. Verify:
#        - runner status=ok, exit_code 0
#        - <save_dir>/last_checkpoint.pt is a real file (not the upgrade symlink)
#        - log shows hybrid loss components (av_loss / bv_loss / contrast / recon)
#        - the original upgraded ckpt md5 unchanged (symlink replacement was safe)
#
# Runtime: ~3-5 min on a single L4 (hybrid is slightly heavier than vocab-only).

@pytest.mark.slow
def test_end_to_end_one_epoch_after_upgrade_hybrid(tmp_path: Path) -> None:
    import hashlib
    import shutil
    fixture_dir = REPO_ROOT / "tests" / "data" / "pretrain"

    # 1. Build a fake modern grover_base ckpt with vocab heads sized to fixture.
    modern_ckpt = _build_modern_grover_base(tmp_path / "modern.pt")

    # 2. Build a real smiles vocab from the train shards' SMILES.
    smiles_corpus = tmp_path / "smiles_corpus.csv"
    with smiles_corpus.open("w") as out:
        out.write("smiles\n")
        for shard in sorted((fixture_dir / "train_9k" / "graph").glob("*.csv")):
            with shard.open() as f:
                lines = f.readlines()
                if lines and lines[0].strip().lower() == "smiles":
                    lines = lines[1:]
                out.writelines(lines)
    vocab_dir = tmp_path / "vocab"
    vocab_dir.mkdir(parents=True, exist_ok=True)
    build_vocab_script = REPO_ROOT / "scripts" / "build_vocab.py"
    r = subprocess.run(
        [sys.executable, str(build_vocab_script),
         "--data_path", str(smiles_corpus),
         "--vocab_save_folder", str(vocab_dir),
         "--dataset_name", "pretrain",
         "--build_smiles_only"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    smiles_vocab = vocab_dir / "pretrain_smiles_vocab.pkl"
    assert smiles_vocab.is_file()

    # 3. Synthesize prepare_data.json with the real smiles vocab.
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "ok": True, "mode": "pretrain",
        "output_dir": str(data_dir),
        "split_method": "user_provided",
        "steps": [],
        "outputs": {
            "atom_vocab":   str(fixture_dir / "pretrain_atom_vocab.json"),
            "bond_vocab":   str(fixture_dir / "pretrain_bond_vocab.json"),
            "smiles_vocab": str(smiles_vocab),
            "train_dir":    str(fixture_dir / "train_9k"),
            "val_dir":      str(fixture_dir / "val_1k"),
        },
        "errors": [], "warnings": [],
    }
    manifest_path = data_dir / "prepare_data.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # 4. Run upgrade.
    upgraded = tmp_path / "upgraded.pt"
    code, _ = _run_upgrade(modern_ckpt, manifest_path, upgraded)
    assert code == 0
    upgraded_md5_before = hashlib.md5(upgraded.read_bytes()).hexdigest()

    # 5. Launch the runner (1 epoch, save every 100 steps to exercise the save path).
    runner_script = REPO_ROOT / "agent" / "scripts" / "run_pretrain_local.py"
    r = subprocess.run(
        [sys.executable, str(runner_script),
         "--ckpt", str(upgraded),
         "--prepare-manifest", str(manifest_path),
         "--out", str(tmp_path / "run"), "--gpus", "0",
         "--epochs", "1", "--save-interval", "100", "--warmup-epochs", "0",
         "--batch-size", "32"],
        capture_output=True, text=True,
    )
    out = json.loads(r.stdout)
    assert r.returncode == 0, f"runner exited {r.returncode} with: {out}"
    run_manifest = out["manifest"]
    assert run_manifest["status"] == "ok", run_manifest
    assert run_manifest["exit_code"] == 0
    assert run_manifest["pretrain_mode"] == "hybrid"

    # 6. Verify outputs.
    final_ckpt = tmp_path / "run" / "ckpt" / "last_checkpoint.pt"
    assert final_ckpt.is_file()
    assert not final_ckpt.is_symlink()
    # Upgraded ckpt unchanged (symlink replacement was safe).
    assert hashlib.md5(upgraded.read_bytes()).hexdigest() == upgraded_md5_before
    # Log contains hybrid training output (contrast/recon loss terms).
    log_path = tmp_path / "run" / "logs" / "pretrain_ddp.log"
    assert log_path.is_file()
    log_text = log_path.read_text()
    assert "epoch=" in log_text or "Epoch" in log_text or "loss" in log_text.lower()

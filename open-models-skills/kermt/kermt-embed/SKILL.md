---
name: kermt-embed
description: Extract per-molecule embeddings from any encoder-bearing KERMT checkpoint (grover_base / cmim / hybrid / finetuned). Writes one .npy per readout type (atom_from_atom, bond_from_atom, atom_from_bond, bond_from_bond) plus canonical_smiles.npy and validity.npy. Calls task/extract_embeddings.py (which featurizes SMILES on the fly — no pre-computed features needed).
license: Apache-2.0
compatibility: Requires docker, nvidia-container-toolkit, and a CUDA-capable NVIDIA GPU. Designed for Claude Code, Codex, and Nemotron.
metadata:
  owner: evax@nvidia.com
  classification: workflow-skill
  risk_tier: skill
# Line/token budget: targets ~150 lines / ~1800 tokens — within the
# 500-line / 5000-token cap for skill files.
---

# kermt-embed

Extract per-molecule embeddings from any encoder-bearing KERMT checkpoint.
The skill is the workflow orchestrator: validate ckpt, validate CSV, clean
SMILES, launch the runner blocking, return the per-readout `.npy` files.

## Hardware requirements

- **GPUs**: 1 (single-GPU).
- **VRAM**: ≥ 4 GB for the default `batch_size 64`.
- **Disk**: depends on output size — roughly a few MB per 1k molecules at
  `hidden 800` per readout, so ~10–20 MB per 1k molecules across the 4
  readouts. Plus a small `canonical_smiles.npy` + `validity.npy` per run.
- **Driver / CUDA**: any host supporting CUDA 12.6.

## Inputs

Required:

- `--csv <path>` — SMILES CSV. First column is `smiles`; other columns
  are ignored (no targets needed).

Checkpoint (optional — defaults to the released model if omitted):

- `--ckpt <path>` — any encoder-bearing checkpoint. Grover_base, cmim,
  hybrid, and finetuned ckpts are all accepted. The validator only refuses
  ckpts with no encoder. **If omitted**, the skill offers to download the
  released pretrained hybrid model **nvidia/NV-KERMT-70M-v2** and embed with
  it — see "Resolve & validate the checkpoint" (workflow step 3).
- `--pretrained-release` — explicit opt-in to use the released model without
  the interactive prompt (for non-interactive / agent runs). Mutually
  exclusive with `--ckpt`.
- `--model-dir <dir>` — where to save the downloaded bundle (default
  `$KERMT_REPO/models/NV-KERMT-70M-v2/`). An already-complete bundle there is
  reused, not re-downloaded.

Optional:

- `--batch-size N` — override the configured default (64).
- `--gpus 0` — single GPU id (default 0).
- `--from-prepare <dir>` — skip the prepare step and reuse an existing
  `prepare_data.json` in `<dir>`.

## Workflow

Let `$KERMT_REPO` be the path to your kermt repo checkout.

1. **Pre-flight: container + system probe.**
   ```
   $KERMT_REPO/agent/scripts/kermt_container.sh check_system
   ```

2. **Compute run directory.**
   ```
   RUN_DIR=$KERMT_REPO/runs/embed_$(date -u +%Y-%m-%dT%H-%M-%SZ)
   ```

3. **Resolve & validate the checkpoint.**

   **Resolve — only if `--ckpt` was omitted.** Default to the released
   pretrained hybrid model **nvidia/NV-KERMT-70M-v2**:
   - **Consent gate.** Unless `--pretrained-release` was passed, ask the user:
     "No checkpoint given — download the released model nvidia/NV-KERMT-70M-v2
     (NVIDIA Open Model License, https://huggingface.co/nvidia/NV-KERMT-70M-v2)
     and embed with it? [y/N]". **Never download without an explicit yes** (or
     `--pretrained-release`). If both `--ckpt` and `--pretrained-release` are
     given, abort — they conflict.
   - **Save location.** Default `$KERMT_REPO/models/NV-KERMT-70M-v2/`; honor
     `--model-dir <dir>` if given. An already-complete bundle is reused.
   - **Download** (foreground; ~282 MB on first fetch):
     ```
     $KERMT_REPO/agent/scripts/kermt_container.sh run --model-dir <save-dir> -- \
         "python agent/scripts/fetch_released_model.py --out /model"
     ```
     Parse the JSON; abort on `ok: false` (surface `errors`). On success set
     `<user-ckpt> = <save-dir>/kermt_contrastive_v2.0.pt`.

   **Validate** the resolved (or user-provided) ckpt:
   ```
   $KERMT_REPO/agent/scripts/kermt_container.sh run --ckpt <user-ckpt> -- \
       "python agent/scripts/check_checkpoint.py --mode embed --ckpt /ckpt"
   ```
   Parse JSON. Abort on `ok: false`. The validator only refuses encoder-less
   ckpts (rare).

4. **Validate the data.**
   ```
   $KERMT_REPO/agent/scripts/kermt_container.sh run --data <user-csv> -- \
       "python agent/scripts/check_data.py --mode embed --csv /data/<basename>"
   ```

5. **Prepare the data** (clean-only — no features step).
   ```
   $KERMT_REPO/agent/scripts/kermt_container.sh run --data <user-csv> --run-dir $RUN_DIR -- \
       "python agent/scripts/prepare_data.py --mode embed \\
            --csv /data/<basename> --out /runs/data"
   ```
   Outputs land at `$RUN_DIR/data/prepare_data.json` with a single `clean_csv`
   path. `task/extract_embeddings.py` featurizes from SMILES on the fly.

6. **Launch the runner (blocking).**
   ```
   $KERMT_REPO/agent/scripts/kermt_container.sh run \\
       --ckpt <user-ckpt> --run-dir $RUN_DIR -- \\
       "python agent/scripts/run_extract_embeddings.py \\
            --ckpt /ckpt \\
            --prepare-manifest /runs/data/prepare_data.json \\
            --out /runs \\
            [--gpus 0 --batch-size N]"
   ```

7. **Report to the user.**
   - Embeddings directory: `$RUN_DIR/out/`
     - `atom_from_atom.npy`, `bond_from_atom.npy`,
       `atom_from_bond.npy`, `bond_from_bond.npy` (the 4 standard readouts;
       each shape `(N_rows, hidden_size)`)
     - `metadata.pkl` — pickle of a dict containing `canonical_smiles`
       (RDKit-canonicalized SMILES per row), `valid` (boolean per-row: did
       RDKit parse it), plus other run metadata.
   - Manifest: `$RUN_DIR/run.json`
   - Log: `$RUN_DIR/logs/embed.log`

## Hard rules

- **Never download the released model without consent.** When `--ckpt` is
  omitted, download `nvidia/NV-KERMT-70M-v2` only after an explicit user "yes"
  or an explicit `--pretrained-release` flag. `--ckpt` and
  `--pretrained-release` are mutually exclusive.
- **Never modify the user's ckpt.** The runner reads-only via
  `task/extract_embeddings.py`'s `--checkpoint <path>` flag.
- **Arch comes from the ckpt.** No `--hidden-size` flag etc. on this runner;
  `task/extract_embeddings.py` reads arch from the ckpt's saved_args.

## Common errors

- `prepare_data manifest is missing required output 'clean_csv'` → prepare
  ran with `--skip-clean` but no source CSV given. Re-run prepare without it.
- `--gpus '0,1' is single-GPU only` → pass a single id.

## Replayability

```bash
$(jq -r .cmd_replay $RUN_DIR/run.json)
```

If `ok_to_replay: false` (dirty kermt repo worktree at launch time), pin
the commit via `repo.commit` and `git checkout` it first.

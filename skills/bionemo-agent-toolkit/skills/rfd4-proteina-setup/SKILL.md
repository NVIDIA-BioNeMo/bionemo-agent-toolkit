---
name: rfd4-proteina-setup
description: >
  Prepare a machine to run RFD4-Proteina (RFD4-Proteina) — the Baker Lab x NVIDIA
  flow-matching protein design model. Reach for this skill for "set up
  rfproteina", "install rfproteina", "environment for rfproteina", "download the
  rfproteina checkpoints", "DATA_PATH not found", "atomworks not found", "which
  checkpoint do I use", "run rfproteina on a cluster",
  or before any generate/evaluate/search run. It installs the native Python environment and AtomWorks, wires DATA_PATH and runtime settings, downloads the model
  weights, and preflights GPU + checkpoints so downstream runs do not fail
  mid-job. Hand off to rfd4-proteina-generate once preflight is green.
license: See the RFD4-Proteina repository (Baker Lab x NVIDIA collaboration)
---

# RFD4-Proteina Setup

Get a host ready to run RFD4-Proteina inference: environment, model weights, and a
green preflight. The two failure modes this skill exists to prevent are (1)
importing the model before its environment and AtomWorks are installed, and (2)
launching an hours-long run only to have it die because `DATA_PATH` or a
checkpoint is missing. Preflight both up front.

Run everything from the repository root (the directory containing `.project-root`).

## Step 1 — Install the runtime

From the repository root:

```bash
make setup
source .venv/bin/activate
```

Native setup creates `.venv` with the CUDA 13 model dependencies and installs
the public AtomWorks version pinned in `pyproject.toml`. It creates `.env.local`
only if neither `.env.local` nor `.env` exists, preserves existing files, and does
not edit shell startup files.

## Step 2 — Check data paths and optional refolding

Setup downloads the configured native checkpoint pair to `DATA_PATH`, or caches
an enabled Hugging Face bundle under `HF_HOME`. `DATA_PATH` defaults to `./data_path`.
Exported shell settings take precedence over the environment file. Use
`bash setup.sh --skip-weights` for an environment-only installation.

`configs/inference.yaml` selects native checkpoints or a pinned model repository.
Use `HF_TOKEN` or `hf auth login` while private; public downloads use the same code.
To add OpenFold3 on a host with Apptainer:

```bash
./scripts/download_assets.sh ./data_path
```

Pass your configured `DATA_PATH` instead if it differs from `./data_path`.
Set the printed oracle paths in `.env.local` and use `metrics/refolding_oracles=of3`.
See `docs/installation.rst` for the separate host oracle.

## Step 3 — Preflight

```bash
bash skills/rfd4-proteina-setup/scripts/preflight.sh
```

This uses the same runtime dispatcher as model entry points and checks imports,
CUDA visibility, and cached model files. Resolve failures before sampling.

## Step 4 — Smoke test

```bash
rfd4-generate inputs=data/benchmarks/monomer \
    subset_to_examples=monomer-short num_replicates=1 out_dir=./runs/smoke ~metrics compile_lengths=null
```

A generated CIF under `runs/smoke/inference_samples/` confirms the inference path.
Hand off to **rfd4-proteina-generate** for real designs.

## Optional host tools

Setup always creates `.venv` for SLURM configuration resolution.
`bash setup.sh --venv` adds notebooks and development dependencies. Use the installed
`rfd4-*` commands from the activated environment.

## Troubleshooting

- Import failures: rerun setup or the pip installation in your selected environment.
- Missing model files: check `HF_HOME` and rerun setup. Optional data uses `DATA_PATH`.
- Missing GPU: verify the NVIDIA driver and the selected runtime's GPU support.
- Refolding failures: check the separate oracle image, weights, cache, and host Apptainer.
- SLURM host tooling missing: rerun setup, then configure `scripts/.user_info_local`.

For checkpoint details, see [checkpoints](references/checkpoints.md).

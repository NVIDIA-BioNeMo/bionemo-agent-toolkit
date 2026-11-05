---
name: rfd4-proteina-setup
description: Use when installing or troubleshooting the RFD4-Proteina runtime, checkpoints, data paths, or GPU preflight.
license: CC-BY-4.0 AND BSD-3-Clause
allowed-tools: Bash, Read, Write, Env
metadata:
  author: Ohad Mosafi <omosafi@nvidia.com>
  tags: [protein-design, rfd4, setup]
---

# RFD4-Proteína Setup

## Purpose

Install the RFD4-Proteína model runtime and configured weights, then prove
readiness with preflight and one generated monomer. Use this for native model
setup and troubleshooting; an already-running NIM has a different deployment
workflow.

## Prerequisites

The RFD4-Proteína model checkout, its documented host/GPU platform, and storage
for the environment and checkpoints. The skill catalog contains instructions
and helpers, not the model source. A skill being installed does not imply that
the model or a GPU is installed.

## Inputs

Use the supplied model checkout at `RFPROTEINA_ROOT`, or the supplied source URL
and revision when a clone is needed. Reuse known paths and access information.
Optional inputs are `DATA_PATH`, `RFPROTEINA_PYTHON` for an existing model
interpreter, and oracle or scheduler settings. Exported values take precedence
over configuration-file defaults.

## Instructions

For a Studio request, start with **Studio runtime** in step 2. That installer
already identifies and stages the pinned public source; a pre-existing model
checkout is not required. Steps 1 and 3–5 describe standalone upstream setup.

### 1. Locate the model and preserve the workspace

- Resolve the loaded skill directory to an absolute path and keep it in
  `RFD4_SETUP_SKILL` before changing directory. Its helpers belong to the skill
  installation; `setup.sh`, configs, and benchmark inputs belong to the model.
- Inspect the supplied `RFPROTEINA_ROOT`, or the current project if no path was
  supplied. A model checkout has `.project-root`, `pyproject.toml`, and
  `configs/inference.yaml`. Read its installation manual and setup entry point.
  A missing `scripts/rfproteina_exec.sh` alone does not mean the model is absent:
  native installations can use `.venv/bin/python` directly.
- If the source is missing, use an already-supplied repository URL and revision
  to clone into a new, unused directory. Otherwise request that missing source
  information. Do not guess a similarly named Proteina repository or substitute
  the NIM for this model. A 404 can mean unavailable or private source.
- Preserve existing files, Git metadata, environments, and data. Never clear or
  reset a workspace to make a clone fit. If the destination exists, inspect it
  and reuse a valid checkout or select an unused destination. A failed clone
  does not authorize deleting its destination or unrelated files.

Set `RFPROTEINA_ROOT` to the verified absolute model path and execute RFProteína
commands there. Use the absolute skill path for its helpers. For revision-specific setup
and safe environment-file handling, read [environment](references/environment.md).

### 2. Check the host, then install

#### Studio runtime

For a request from **RFD4 Studio**, use the installed plugin's
`atomworks-studio/scripts/runtime_setup.py`, rather than ordinary upstream setup.
The Studio integration requires its exact Python/dependency profile and a local
checksum-verified bundle with a revision receipt. Locate that directory in the
plugin, copy its scripts, JSON profiles and lock together to the selected host
outside the model checkout, and set `RFD4_STUDIO_DIR` to the integration directory
on that host. Run:

```bash
python3 "$RFD4_STUDIO_DIR/scripts/runtime_setup.py" \
    --runtime-root /absolute/runtime-root --output-root /absolute/output-root
```

The roots must match the Studio target. Setup refuses incompatible hosts,
different or modified source revisions, and active execution under that output
root. It stages the pinned public source under `runtime-root/model`, installs
the hashed dependency lock, downloads the public bundle to
`runtime-root/model-bundle`, then requires all nine Studio checks and a real
short-monomer CIF smoke result. It preserves previous smoke results. It installs
no OS packages and makes no driver changes. Repeat Studio's `check_named_target`
on the same host before submission. `--check` runs the same readiness probe
without installation or sampling; it does not establish successful inference.
Follow the remaining steps below for standalone upstream setup only.

#### Standalone upstream runtime

Check the selected execution host's GPU visibility (for example `nvidia-smi -L`),
storage, and required platform against its installation manual. On a cluster,
inspect the requested GPU allocation rather than treating a login node as the
inference host. Distinguish a missing driver utility from a failed CUDA check.
If GPU access is unavailable, report that inference is blocked; perform an
explicitly requested environment-only installation without claiming readiness.

From the verified model checkout, use its maintained installation recipe:

```bash
cd "$RFPROTEINA_ROOT"
bash setup.sh --native --skip-search-envs
source .venv/bin/activate
```

If the user selected an existing model environment, reuse it and install only
missing dependencies. Run the later `rfd4-generate` command from the same
environment that preflight checks.

The documented native setup creates `.venv` and installs AtomWorks at the
version pinned in `pyproject.toml`. It preserves existing environment files
and does not edit shell startup files. Inspect the chosen revision's manual
before adapting these commands. Diagnose installation failures from their logs;
do not disable TLS verification, substitute import stubs, or patch model code
to manufacture a successful preflight.

### 3. Resolve data paths and checkpoints

The current public setup downloads `config.json` and `model.safetensors` for
`hf_ckpt_path` at `hf_ckpt_revision` into the Hugging Face cache. This portable
bundle includes the model and autoencoder; it does not create the legacy
`flow_checkpoints` / `ae_checkpoints` pair. Set `HF_HOME` before setup to choose
the cache location. `DATA_PATH` (default `./data_path`) holds ancillary data and
legacy checkpoints. `bash setup.sh --skip-weights --skip-search-envs` installs
only the environment.
A missing checkpoint is a download/configuration problem, not evidence that
the checkout is absent.

Read the checkpoint names from `configs/inference.yaml` and check the selected
data directory. Exported `DATA_PATH` takes precedence over `.env.local`, with
`.env` used only when `.env.local` is absent. Treat these files as data, never
shell-source them or print credentials. See [checkpoints](references/checkpoints.md)
for the release files and downloader. Keep optional refolding setup separate;
plain monomer generation needs no oracle.

For native preflight, export the actual data directory selected during setup,
or pass it explicitly with `--data-path`. The checker uses this supplied path;
it does not load credential files. Preserve the existing configuration rather
than replacing it with a guessed default.

### 4. Run preflight in that model's runtime

```bash
bash "$RFD4_SETUP_SKILL/scripts/preflight.sh" --repo-root "$RFPROTEINA_ROOT"
```

The helper uses explicit `RFPROTEINA_PYTHON` when supplied, otherwise the
checkout's executable dispatcher if present, otherwise its native
`.venv/bin/python`. It checks imports, CUDA, and the configured weights: a local
or already cached Hugging Face bundle when `hf_ckpt_path` is set, otherwise the
legacy checkpoint pair. It performs no downloads. For bundles, absent `DATA_PATH`
defaults to the checkout's `data_path`; legacy checkpoints require an explicit
data setting. `--data-path` overrides exported `DATA_PATH`; relative paths resolve
against the model root. A nonzero exit blocks the
smoke test. Report the actual failed check and remedy instead of replacing the
checkout or calling setup complete.

### 5. Generate and verify one smoke result

After preflight exits 0 with `PREFLIGHT PASSED`, run:

```bash
rfd4-generate inputs=data/benchmarks/monomer \
    subset_to_examples=monomer-short num_replicates=1 out_dir=./runs/smoke
```

Use an unused output directory; preserve earlier runs if `runs/smoke` already
contains results. Confirm command success and a nonempty annotated CIF under
the actual output directory's `inference_samples/`. Report the checkout,
interpreter, bundle revision or checkpoint pair, preflight result, and resulting CIF path. A
passing preflight alone does not establish successful generation. Hand off to
**rfd4-proteina-generate** for larger design requests.

## Troubleshooting

- Skill present but model source unavailable: report which candidate paths were
  checked and request the approved checkout or source URL/revision. Stop source
  guessing after an access failure; preserve the workspace.
- Checkout found but runtime missing: run its installer or select its existing
  interpreter with `RFPROTEINA_PYTHON`.
- Missing data/checkpoints: check the selected `DATA_PATH` and repeat the
  documented download for that directory; preserve existing settings.
- No usable CUDA device: fix the requested host/allocation before generation.
- Refolding failures: check the separate oracle image, weights, cache, and
  host runtime. Do not add refolding to this plain generation smoke test.

## Limitations

A checkout, GPU, and checkpoint access must exist in the execution environment.
Preflight
checks dependencies, CUDA, and release files; it does not validate every design
task, checkpoint checksum, custom checkpoint override, or optional oracle.

## Examples

For a separately installed skill and model, set `RFD4_SETUP_SKILL` to the loaded
skill directory and `RFPROTEINA_ROOT` to the model checkout, then follow steps
2–5. On a host without a GPU, a useful result is an accurate blocker diagnosis;
it is not a completed inference installation.

## Available Scripts

| Script | Purpose | Arguments |
| --- | --- | --- |
| `scripts/preflight.sh` | Check the selected model runtime | `--repo-root PATH` or `RFPROTEINA_ROOT`; `--data-path PATH` or `DATA_PATH`; optional `RFPROTEINA_PYTHON` |
| `scripts/preflight.py` | Run checks directly in an installed model interpreter | `--repo-root PATH` or `RFPROTEINA_ROOT`; `--data-path PATH` or `DATA_PATH` |

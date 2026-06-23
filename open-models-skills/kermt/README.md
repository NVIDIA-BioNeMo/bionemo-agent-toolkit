# KERMT agent workflows

This directory provides agent-ready skills and the scripts they call for running
KERMT workflows locally. The skills are tool-agnostic Markdown files; the
scripts are deterministic kernels that can also be invoked directly without an
agent.

## Audience: who should read what

This README serves both human users and the agents that drive the skills.

- **If you are a user:** you do not need to read this file end-to-end to use
  the skills. Skip to [Installing the skills](#installing-the-skills), install
  once, then ask your agent (Claude Code, Codex, Nemotron, etc.) to run a
  workflow by name — for example, *"use kermt-finetune to fine-tune this
  checkpoint on this CSV."* The agent will read the relevant `SKILL.md` files
  and drive the rest. Skim the [Skills](#skills) table below if you want a
  one-line summary of each workflow, but the deeper sections are reference
  material for the agent, not required reading for you.
- **If you are an agent:** the sections below — Skills, Released models,
  Convention: runs/..., Running a workflow — describe the orchestration
  patterns and conventions you need to invoke the skills correctly. Read the
  relevant `skills/<skill-name>/SKILL.md` for the specific workflow the user
  asked for, plus the bind-mount and `KERMT_REPO` notes in
  [Running a workflow](#running-a-workflow).

## Container-first

Every workflow runs inside the `kermt:latest` docker image, built locally from
the [`Dockerfile`](../Dockerfile) at the repo root. The first time you run any
skill, the bootstrap helper will build the image (~10–20 min on a typical
workstation). All subsequent invocations reuse the built image.

Requirements on the host: Docker with the NVIDIA Container Toolkit installed
and a CUDA-capable NVIDIA GPU. The skills have been developed and tested on
Linux only; Mac and Windows are not currently tested and may need adjustments
(especially around GPU passthrough — Docker Desktop on Mac does not support
`--gpus all`).

## Skills

The seven KERMT skills split into two categories.

**Workflow skills** — the ones users invoke by name. Each composes a
check_checkpoint → check_data → prepare_data → run_\<workflow\> pipeline.

| Skill | Workflow | User provides |
|---|---|---|
| `kermt-continue-pretrain` | Continue pretraining from an existing KERMT checkpoint. Verifies the ckpt's vocab head sizes match the supplied vocab files; refuses to proceed on mismatch. | Checkpoint + its bundled vocab files (see [Released models](#released-models)), pretrain CSV, hyperparameters (optional) |
| `kermt-pretrain-scratch` | Pretrain a fresh KERMT model from scratch on a user corpus. Builds a new vocab from the corpus and initializes the model architecture from `config/defaults_pretrain.json`. Days-scale; warns the user before launching. | Pretrain CSV, `--pretrain-target-mode {vocab\|cmim\|hybrid}` (required), hyperparameters (optional) |
| `kermt-add-cmim-pretrain` | Take a Grover-base-style checkpoint (no cMIM decoder), add a randomly-initialized decoder, then continue pretraining as Hybrid (vocab + contrast). | Encoder-only checkpoint, pretrain CSV, hyperparameters |
| `kermt-finetune` | Finetune a pretrained checkpoint on a labeled task. | Pretrained checkpoint, labeled CSV, target column names |
| `kermt-infer` | Run predictions with a finetuned checkpoint. | Finetuned checkpoint, CSV with SMILES |
| `kermt-embed` | Extract molecular embeddings from any encoder-bearing checkpoint. | Checkpoint, CSV with SMILES |

**Companion skills** — auto-invoked by the workflow skills above; not
intended for direct user invocation, though they can be invoked standalone
when needed (e.g. forcing an image rebuild, debugging a detached run).

| Skill | Workflow | User provides |
|---|---|---|
| `kermt-setup` | Build/verify the `kermt:latest` docker image. The first workflow skill you run triggers this automatically; only invoke directly to force a rebuild or debug the image. | — |
| `kermt-monitor` | Tail logs and report progress for a detached pretrain (or any long-running) run. Suggested at the end of each detached-launch skill's output; you can also invoke it directly if you want a one-shot status check. | A `runs/<workflow>_<timestamp>/` directory from a prior detached launch |

Pretraining is long-running (hours to days). The `kermt-continue-pretrain` and
`kermt-add-cmim-pretrain` skills launch detached and return a run directory
plus a TensorBoard URL; the agent typically invokes `kermt-monitor` next.

All seven skills are markdown + scripts, a passive instruction set —
they call deterministic Python kernels but make no autonomous decisions
and expose no network APIs.

## Hardware requirements per workflow

Each workflow declares its hardware needs explicitly. `kermt-setup` validates
GPU presence + driver/CUDA version before any other skill is invoked.

| Workflow | GPUs | VRAM per GPU | Disk | Typical wall time |
|---|---|---|---|---|
| `kermt-setup` | 1+ | — (validation only) | ~50 GB (kermt image; see kermt-setup hardware notes) | ~10–20 min first build |
| `kermt-continue-pretrain` | 1–N (auto-detected, DDP-aware) | ≥ 16 GB for batch_size 256, depth 6, hidden 800; falls back to batch_size 32 on 1 GPU | run dir ~tens of GB depending on corpus + epochs | hours to days |
| `kermt-pretrain-scratch` | 1–N | same as continue-pretrain | same as continue-pretrain | **days even on multi-GPU** (no warm start) |
| `kermt-add-cmim-pretrain` | 1–N | same as continue-pretrain | same | hours to days |
| `kermt-finetune` | 1 (default; multi-GPU not yet supported by this skill) | ≥ 8 GB | few GB |
| `kermt-infer` | 1 | ≥ 4 GB | small |
| `kermt-embed` | 1 | ≥ 4 GB | depends on output size (one .npy per readout type, ~MB per 1k mols at hidden 800) |
| `kermt-monitor` | 0 | — (no compute) | — |

Driver / CUDA version: every workflow runs inside `kermt:latest`, which is
built on `nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04`. The host driver must
support CUDA 12.6 or newer. `kermt-setup` checks this; if it fails, the skill
surfaces the gap and stops.

**Local execution.** All workflows assume a local CUDA-capable host. Users on
machines without a GPU need to arrange a GPU host before invoking the skills.

## Released models

Each released KERMT checkpoint is distributed as a **directory bundle**
containing the ckpt itself plus its vocab files:

```
<released_model>/
├── last_checkpoint.pt
├── pretrain_atom_vocab.{json,pkl}    # either extension; pkl in current releases
├── pretrain_bond_vocab.{json,pkl}    # either extension; pkl in current releases
└── pretrain_smiles_vocab.pkl         # only for cmim / hybrid ckpts (pickle-only)
```

If you're upgrading a grover_base ckpt to hybrid with
[`kermt-add-cmim-pretrain`](skills/kermt-add-cmim-pretrain/SKILL.md), the
upgrade step builds a fresh `pretrain_smiles_vocab.pkl` from your
pretrain corpus — released bundles only ship the smiles vocab for
already-cmim / already-hybrid ckpts.

The vocab files are an inseparable part of the released model — the ckpt's
vocab head dimensions are fixed at training time and only match these specific
vocab files. `kermt-continue-pretrain` treats the released ckpt's vocab as
authoritative: new corpora are tokenized through it rather than producing a
new vocab that would mismatch the ckpt's heads.

The skill auto-detects the three vocab files in the ckpt's parent directory
and passes them through `prepare_data.py --vocab-dir`. If the bundle is
incomplete (or the user has the ckpt alone), the skill asks for the
`--vocab-dir` path; if the user can't provide one, the skill refuses to
proceed and suggests `kermt-pretrain-scratch` instead.

To train a model on a corpus the released vocab can't cover, use
`kermt-pretrain-scratch` — the new vocab is built from the corpus and the
model is initialized fresh (no warm start; days-scale to converge).

## Token-efficient design

The skill files (`.md`) are intentionally thin — they orchestrate, prompt for
missing args, and parse JSON. The deterministic work happens in the Python
scripts under [`scripts/`](scripts/), each of which emits a structured JSON
document the calling skill consumes. This pattern follows the
`bionemo-nim-skills` precedent (50–75% token reduction vs raw-prompt
equivalents): every skill body stays well under the 500-line / 5000-token
budget recommended for skill files, with detailed schemas and long examples
left in the Python kernels' docstrings rather than in the skill file.

## Convention: `runs/<workflow>_<UTC-timestamp>/`

Every workflow writes its artifacts into a fresh
`runs/<workflow>_<UTC-timestamp>/` directory with subfolders:

```
runs/<workflow>_<UTC-timestamp>/
├── data/      # Prepared data (vocab files, features, splits)
├── ckpt/      # Saved checkpoints
├── logs/      # Training logs, tensorboard event files
├── out/       # Predictions, embeddings, anything user-facing
└── run.json   # Manifest: workflow name, input args, defaults applied, container ID, timestamps
```

The `run.json` manifest is what you hand to the next skill (e.g.
`kermt-continue-pretrain --from-run runs/continue-pretrain_2026-05-13T15-30Z/`).

## Defaults

Hyperparameter defaults live in [`config/`](config/). The skills echo applied
defaults back to you on every invocation; override any value with the
corresponding `--<name>` flag.

- [`config/defaults_pretrain.json`](config/defaults_pretrain.json)
- [`config/defaults_finetune.json`](config/defaults_finetune.json)

## Installing the skills

The skills follow the [agentskills.io](https://agentskills.io) spec: each
skill is a directory under [`skills/`](skills/) containing a `SKILL.md` file.
The primary target agents are **Claude Code**, **Codex**, and **Nemotron**.
Other agentskills.io-compatible agents should also work; see the
[client showcase](https://agentskills.io) for the up-to-date list.

### Claude Code

Claude Code expects skills at `~/.claude/skills/<skill-name>/SKILL.md`. From
a clone of the kermt repo:

```bash
for d in agent/skills/kermt-*/; do
  name=$(basename "$d")
  ln -sfn "$(realpath "$d")" ~/.claude/skills/"$name"
done
```

Restart Claude Code once after the first install so it picks up the new
`~/.claude/skills/` entries. The symlinked form means future `git pull` updates
to the skill content take effect without re-installing. If you ever rename a
skill on disk (e.g. `kermt-foo` → `kermt-bar`), clean the stale entry first:
`rm -rf ~/.claude/skills/kermt-foo` before re-running the snippet above.

### Codex

Codex follows the same agentskills.io layout. Point Codex at
`agent/skills/` (or symlink each `kermt-*/` directory into its skills
discovery path — refer to the
[Codex skills docs](https://developers.openai.com/codex/skills/) for the
exact location).

### Nemotron and other agentskills.io-compatible agents

Most other agents (Nemotron, Cursor, Gemini CLI, etc.) follow the same
spec — pass `agent/skills/` directly as a skills directory or attach the
relevant `<skill-name>/SKILL.md` into context, and invoke by name (e.g.
"run kermt-finetune on …").

### No agent

Every workflow is also runnable directly by humans — the skills are just
orchestration. Each `SKILL.md` lists the exact `python` commands it would
run, and all scripts have `--help` output. Start by reading
[`skills/kermt-setup/SKILL.md`](skills/kermt-setup/SKILL.md) for the container bootstrap,
then the skill for the workflow you want.

## Running a workflow

The notes in this section apply to every workflow regardless of which agent
(or human) is driving — they describe how the shared
[`scripts/kermt_container.sh`](scripts/kermt_container.sh) helper that every
SKILL.md invokes maps host paths into the container.

### `KERMT_REPO` environment variable

Every workflow step in every SKILL.md uses
`$KERMT_REPO/agent/scripts/kermt_container.sh …` to bind-mount the repo at
`/workspace` inside the docker container. The helper auto-derives
`KERMT_REPO` from its own script path, so the default works for invocations
made from inside the repo. **If you're running from an arbitrary directory,
export it once** so every helper call picks it up:

```bash
export KERMT_REPO=/path/to/your/kermt
```

### Host-path → container-path bind-mount pattern

All workflow commands use the same two-layer pattern:

1. Pass the **host** path to `kermt_container.sh` via one of its mount flags:
   - `--data <path>` (file or dir) → mounted at `/data` (file's parent if
     `<path>` is a file)
   - `--ckpt <path>` → mounted at `/ckpt` (path mounted as-is)
   - `--vocab-dir <dir>` → mounted at `/vocab`
   - `--run-dir <dir>` → mounted at `/runs` (read-write; created if absent)
2. Reference the **container** mount path (`/data`, `/ckpt`, `/vocab`,
   `/runs`) in the inner command passed after `--`.

Mixing the two layers (e.g. passing the host path to the inner command,
or omitting the helper flag entirely) will silently fail at file-not-found
inside the container. When a file you need is already inside one of the
mounted directories (e.g. an upgraded ckpt written to `$RUN_DIR/upgraded.pt`
by a prior step), the `--run-dir` mount already exposes it as
`/runs/upgraded.pt` — no separate `--ckpt` mount needed.

### Single-GPU contention

On a single-GPU host, launching two detached pretrain or finetune containers
concurrently will serialize them via CUDA's per-process initialization
(the second blocks on `cudaInit` until the first releases the device). Run
them sequentially — kick off the second after `docker wait <first-name>` —
or pass `--gpus` to assign them to distinct devices on a multi-GPU host.

### Surface `warnings[]` from validators

Both `check_checkpoint.py` and `check_data.py` emit a `warnings[]` array
alongside `errors[]` and the boolean `ok`. The workflow SKILL.md steps
tell the orchestrator to "abort on `ok: false`" — that handles `errors[]`.
**Also pass `warnings[]` through to the user before proceeding** —
warnings are non-blocking but often flag downstream failures (e.g. a
CSV's SMILES column not being named `smiles` and being at a non-zero
index; `prepare_data.py` auto-detects the index by header but the
warning is still worth surfacing so the user can rename the column for
clarity).

## Scripts (kernels)

Deterministic logic lives under [`scripts/`](scripts/):

| Script | Purpose |
|---|---|
| `kermt_container.sh` | Bootstrap: ensure docker image, wrap commands for execution inside the container |
| `check_checkpoint.py` | Validate a checkpoint for a given workflow (mode-dispatched, JSON output) |
| `check_data.py` | Validate an input CSV for a given workflow (mode-dispatched) |
| `prepare_data.py` | Compose clean → vocab → features → split into one call |
| `upgrade_to_hybrid.py` | Add cMIM decoder to a Grover-base checkpoint |
| `run_pretrain_local.py` | Workstation pretrain runner (auto-detects GPUs, DDP-aware) |
| `run_finetune_local.py` | Workstation finetune runner |
| `run_inference.py` | Run predictions with a finetuned checkpoint |
| `run_extract_embeddings.py` | Extract molecular embeddings |

Tests for these scripts are under [`tests/`](tests/) and use the existing
fixture data in [`../tests/data/pretrain/`](../tests/data/pretrain/) and
[`../tests/data/finetune/`](../tests/data/finetune/).

## Running the tests

The agent test suite should be run **inside the `kermt:latest` container** — that's
the same environment the skills exercise at runtime, so test results are
faithful to the production path. `pytest` is included in the kermt conda env.

After [`kermt-setup`](skills/kermt-setup/SKILL.md) has built the image, from a
kermt repo checkout:

```bash
# Run the full agent test suite in-container.
agent/scripts/kermt_container.sh run -- \
  "python -m pytest agent/tests/ -v --no-header -p no:cacheprovider"
```

Override the image tag if you're testing against a non-default build:

```bash
KERMT_IMAGE=kermt:rebuild-test agent/scripts/kermt_container.sh run -- \
  "python -m pytest agent/tests/test_check_checkpoint.py -v"
```

For quick local-dev iteration on a single test, you can also run the suite on
the host inside any conda env that has `torch`, `rdkit`, `pandas`, and
`pytest` installed:

```bash
conda activate <your-env>
python -m pytest agent/tests/test_check_data.py -v
```

But the final sign-off for any change in `agent/scripts/` is the in-container
run — that's what the skills will actually invoke.

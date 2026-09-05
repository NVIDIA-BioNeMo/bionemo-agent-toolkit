---
name: complexa-setup
description: >
  First-time setup, environment configuration, and model-weight installation for
  Proteina-Complexa. Reach for this skill whenever the user says "set up complexa",
  "install complexa", "configure my .env", "first-time setup", "what models do I
  have installed", "what's in my .env", "download model weights", "download
  Complexa / AF2 / RF3 / ProteinMPNN / LigandMPNN / ESM2 / ESMFold checkpoints",
  "preflight my GPU", "verify environment", "complexa init", "complexa download",
  "complexa download --status", "complexa validate env", or any time a fresh
  checkout needs to be made runnable. This is the first skill to run on a new
  clone — it drives `complexa init`, `complexa download`, and `complexa validate
  env` end-to-end, edits the required `.env` keys, picks the right runtime (UV
  vs Docker), and emits a replayable setup artifact.
compatibility: "complexa CLI installed (pip install -e .); bash 4+; nvidia-smi optional"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Complexa Setup Skill

Drive the three steps a fresh Proteina-Complexa checkout needs before any
design run: create `.env`, fetch model weights, and sanity-check the env.
Probe the host for GPU / disk / tool binaries first so the user does not
discover a missing dependency mid-pipeline. End with a JSON setup artifact the
user (or a future agent) can re-read instead of re-deriving state.

## CLI vs direct file-edit — pick the cheapest path per step

| Step | Preferred path | Why |
|---|---|---|
| `.env` creation (Step 2) | **File edit** (`cp .env_example .env` + 3 line swaps) or `complexa init` | `complexa init` is a thin wrapper around `cp + 3 regex swaps` (`_swap_runtime_in_env` in `cli_runner.py`). Either path works; pick CLI for new humans, direct edit for agents. |
| `.env` value edits (Step 3) | **File edit** (StrReplace `LOCAL_CODE_PATH=…` etc.) | No CLI for this — the values are user-specific paths. |
| Download model weights (Step 4) | **CLI** (`complexa download --…`) | Dispatches to `env/download_startup.sh` (~1000 lines of bash with NGC URLs, retries, checksum-style skip-if-present). Don't try to replicate. |
| Validate env (Step 5) | **CLI** (`complexa validate env`) or `test -f .env && test -d $DATA_PATH` | CLI prints a nicer report; the manual check is one-liner-safe. |
| Validate full design config (after picking a pipeline) | **CLI** (`complexa validate design CONFIG`) | Non-trivial Hydra defaults traversal + ckpt + env-var checks; not worth replicating. |

## What this skill enables

- A correctly-shaped `.env` for either UV or Docker runtime.
- Model checkpoints (Complexa protein/ligand/AME plus community models) downloaded to known paths.
- A `preflight.json` snapshot of the host (GPU, disk, .env, ckpts, tool binaries).
- A `run_manifest.json` capturing exactly which `complexa init` + `complexa download` invocations were used (replay-friendly).
- A pass/fail report from `complexa validate env` with clear next-step hints.

## Step 1: Pre-flight check

Always run the shared preflight before touching the environment. It does not
require `.env` to exist — it falls back to defaults — and it tells you whether
the host can run Complexa at all.

```bash
bash .claude/skills/_shared/scripts/preflight.sh
```

The script writes `./complexa_setup/preflight.json`. Read it and surface:

- `gpu.available` — if `false`, design / evaluate steps will fail; warn the user.
- `gpu.vram_gb` — Complexa needs ≥40 GB (A100/H100/L40S).
- `disk.free_gb` at `CKPT_PATH` — minimum ~50 GB for the full Complexa + community model set.
- `env.missing_required` — anything listed here must be edited in `.env` before validation passes.
- `tools.{foldseek,mmseqs,dssp,hbplus,sc}.exists` — missing tools degrade evaluation but do not block generation.

## Step 1b: Build the Python environment (only if `.venv/` is missing)

The `complexa` CLI is installed inside the project's Python environment, not on
the system path by default. On a **fresh clone**, the `.venv/` directory does
not yet exist and `complexa init` will fail with `command not found`. Build the
UV venv before anything else:

```bash
test -d .venv || ./env/build_uv_env.sh   # first-time UV build
source .venv/bin/activate
which complexa                            # sanity check: should point inside .venv
```

Skip this step if `which complexa` already resolves — that means a previous
build is still good. The Docker runtime skips it entirely; the venv lives
inside the container image instead. If the user said "I just cloned" or you
see no `.venv/` next to `pyproject.toml`, run the build script — `complexa init`
without a venv produces a confusing `command not found` rather than an obvious
"build the venv first" error.

## Step 2: Create `.env`

Pick the runtime. UV is the default and faster to start; Docker is required on
Ubuntu 20.04 or systems with GLIBC mismatches.

Use AskUserQuestion if it is not obvious from context:

> "Which runtime do you want to configure? `uv` (recommended, faster) or `docker` (use if you do not have a UV venv built locally)?"

### Path A: file edit (preferred for agents)

`complexa init` only does three things — copy `.env_example` → `.env` and
swap the `COMPLEXA_RUNTIME=` line plus the `UV_*` ↔ `DOCKER_*` prefixes on the
tool/data/cache path block. You can do the same with `cp` + StrReplace and skip
the CLI:

```bash
cp .env_example .env
# Then StrReplace these lines in .env:
#   COMPLEXA_RUNTIME=uv          → COMPLEXA_RUNTIME=<runtime>
#   FOLDSEEK_EXEC=${UV_FOLDSEEK_EXEC}  → FOLDSEEK_EXEC=${DOCKER_FOLDSEEK_EXEC}   (and same for RF3_EXEC_PATH, SC_EXEC, HBPLUS_EXEC, MMSEQS_EXEC, DSSP_EXEC, TMOL_PATH)
#   DATA_PATH=${LOCAL_DATA_PATH} → DATA_PATH=${DOCKER_DATA_PATH}                  (and same for CACHE_DIR, CKPT_PATH)
```

Skip the prefix swap entirely if you're staying on UV (the `.env_example`
already targets UV).

### Path B: CLI

```bash
complexa init                    # UV runtime (default)
complexa init --runtime docker   # Docker runtime
complexa init --force            # Recreate .env from .env_example (drops any edits)
```

If `.env` already exists and `--force` is not passed, only the runtime-dependent
lines are swapped — user edits in Step 3 are preserved across runtime flips.

### Verify either way

```bash
test -f .env && echo "OK: .env present" || echo "MISSING"
grep -E '^COMPLEXA_RUNTIME=' .env
```

## Step 3: Edit .env

No CLI for this — Step 2 only set the runtime; you still need to write your
machine-specific paths into `.env` by hand (StrReplace or your editor). The two
absolutely-required edits are:

```bash
LOCAL_CODE_PATH=/absolute/path/to/protein-foundation-models
LOCAL_DATA_PATH=/absolute/path/to/PFM_data
```

Everything else (cache, ckpts, community-model dirs, tool binaries) is derived
from `LOCAL_CODE_PATH` by default and only needs editing if you have a
non-standard layout. For the full table — every key, what it controls, what
fails if it is missing — see [reference/env_keys.md](reference/env_keys.md).

Quick decision table for the four edits most users make:

| Key | Default | Set this if |
|-----|---------|-------------|
| `LOCAL_CODE_PATH` | placeholder | Always — required |
| `LOCAL_DATA_PATH` | `/path/to/PFM_data` | Always — required, points at target PDBs |
| `HF_TOKEN` | placeholder | You need ESMFold or gated HF models |
| `WANDB_API_KEY` | placeholder | You want training runs logged to W&B |

## Step 4: Download checkpoints

**Always use the CLI here.** `complexa download` dispatches to
`env/download_startup.sh` (~1000 lines of bash with NGC URLs, retries, and
skip-if-present logic across ~6 community-model families). Rolling your own
wget loop is a recipe for partial downloads and wrong destination paths.

Ask which models the user actually needs — downloading everything is ~100+ GB.
Pick from the three Complexa variants and the community-model set. Each
Complexa variant unlocks exactly one `complexa design` pipeline; AF2 / RF3
inside the community-model set are what `evaluate` (and reward-guided search)
need at run time.

| Flag | What it downloads | Unlocks pipeline | Destination | Approx size |
|------|-------------------|------------------|-------------|-------------|
| `--complexa` | Complexa protein-binder model + AE (`complexa.ckpt`, `complexa_ae.ckpt`) | **Protein binder** (default) — `configs/search_binder_local_pipeline.yaml` | `./ckpts/` | ~3 GB |
| `--complexa-ligand` | Ligand-binder model + AE (`complexa_ligand.ckpt`, `complexa_ligand_ae.ckpt`) | Ligand binder — `configs/search_ligand_binder_local_pipeline.yaml` | `./ckpts/` | ~3 GB |
| `--complexa-ame` | AME motif-scaffolding model + AE (`complexa_ame.ckpt`, `complexa_ame_ae.ckpt`) | AME (enzyme) — `configs/search_ame_local_pipeline.yaml` | `./ckpts/` | ~3 GB |
| `--complexa-all` | All three Complexa variants | All three pipelines | `./ckpts/` | ~9 GB |
| `--all` | All community models (ProteinMPNN + LigandMPNN + AF2 + ESM2 + ESMFold + RF3) | Needed by **evaluate / reward**: AF2 (protein binder), RF3 (ligand binder + AME), MPNNs (inverse folding for every pipeline). | `./community_models/` | ~50 GB |
| `--everything` | Complexa + community + optional (Boltz2 / Protenix) | Everything plus alternative refold backends | both | ~100+ GB |
| `--status` | Show install state — does not download | (none) | (none) | n/a |

**Minimum download per pipeline:**

- Protein binder (default): `complexa download --complexa --all`
- Ligand binder: `complexa download --complexa-ligand --all`
- AME / enzyme: `complexa download --complexa-ame --all`
- All three: `complexa download --everything`

For the full per-model destination breakdown and per-flag NGC sources, see
[reference/downloads.md](reference/downloads.md).

Pick the smallest invocation that covers the user's goal, then run:

```bash
complexa download --complexa            # protein binder only
complexa download --complexa-all        # all three Complexa variants
complexa download --all                 # community models only
complexa download --everything          # everything
```

Without arguments, `complexa download` launches an interactive wizard — prefer
explicit flags in agent mode.

Verify what landed:

```bash
complexa download --status
```

The status output groups by family (Complexa / community / optional) and prints
"Installed" or "Missing" per ckpt. Re-run the specific flag if a ckpt is
flagged missing.

## Step 5: Validate

Final check that `.env` is loadable and the required paths resolve:

```bash
complexa validate env
```

`validate env` checks: (1) `.env` exists, (2) `DATA_PATH` is set and points at
an existing directory. It does not check ckpt files — those are checked by
`complexa validate design <config>` once you have a pipeline config picked.

Common failures and fixes:

| Symptom | Cause | Fix |
|---------|-------|-----|
| `.env file: No .env file found` | `complexa init` not run | Run `complexa init` first |
| `DATA_PATH: Not set in .env` | Placeholder not edited | Edit `LOCAL_DATA_PATH` in `.env` |
| `DATA_PATH: Directory not found` | Path edited but does not exist on disk | `mkdir -p $LOCAL_DATA_PATH` or copy target data there |
| Hydra error `InterpolationKeyError: AF2_DIR` | Reward/eval config wants AF2 but `.env` does not define it | Download AF2 weights or remove AF2 from the config |

## Step 6: Emit setup artifact

Drop a JSON manifest in `./complexa_setup/` so the user has a single file
describing the resulting state. The shared helper writes it for you:

```bash
mkdir -p ./complexa_setup
python .claude/skills/_shared/scripts/write_manifest.py \
    --kind setup \
    --runtime "$(grep -E '^COMPLEXA_RUNTIME=' .env | cut -d= -f2)" \
    --preflight ./complexa_setup/preflight.json \
    --out ./complexa_setup/run_manifest.json
```

Surface the resulting files to the user:

```bash
ls -la ./complexa_setup/
```

Expected contents:

```
complexa_setup/
├── preflight.json      # GPU / disk / .env / ckpt / tool snapshot
└── run_manifest.json   # init + download invocations + git SHA + runtime
```

## Hardware requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| GPU | 1× CUDA GPU, ≥24 GB VRAM | A100 / H100 / L40S, 40–80 GB VRAM |
| CUDA | 12.0 | 12.4+ |
| Disk (CKPT_PATH) | 50 GB | 150 GB (covers `--everything`) |
| RAM | 16 GB | 64 GB+ |
| OS | Ubuntu 22.04+ (UV) | Ubuntu 22.04+ or Docker on any host |

Ubuntu 20.04 throws GLIBC errors with the UV runtime — use `complexa init
--runtime docker` on those hosts. See `.claude/skills/_shared/reference/hardware.md`
for per-pipeline (binder vs ligand vs AME) requirements.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `complexa: command not found` | Package not installed in active env | `source .venv/bin/activate` then `pip install -e .` |
| `complexa init` says `.env_example not found` | Running outside repo root | `cd` to the project root (where `.env_example` lives) |
| `.env_example not found. Cannot initialize .env.` | Not in project root | `cd` into `protein-foundation-models/` and retry |
| `complexa download` fails on NGC URL | Behind firewall / no internet | Configure a proxy for the download script, or download the model `.ckpt`s manually from the NGC pages linked in the main `README.md` and drop them into `./ckpts/` |
| `complexa download --status` shows ckpts present but `validate` fails | `.env` `CKPT_PATH` points elsewhere | Either move ckpts or edit `LOCAL_CHECKPOINT_PATH` in `.env` |
| GLIBC error on import | Ubuntu 20.04 with UV runtime | Re-run `complexa init --runtime docker` and use `./env/docker-ops.sh run` |

---

For the full `.env` reference (every key, defaults, failure modes), see
[reference/env_keys.md](reference/env_keys.md).

For the full download flag matrix, NGC URLs, and destination layout, see
[reference/downloads.md](reference/downloads.md).

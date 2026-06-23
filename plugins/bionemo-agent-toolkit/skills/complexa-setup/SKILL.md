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
| `.env` creation (Step 2) | **CLI** (`complexa init <runtime>`) | `complexa init` copies `.env_example` → `.env` and swaps the runtime lines (`_swap_runtime_in_env` in `cli_runner.py`). Use the CLI: it is the supported entry point and guarantees the `.env` the rest of the toolchain expects. A bare `cp .env_example .env` is a fragile re-implementation — prefer `complexa init`. |
| `.env` value edits (Step 3) | **File edit** (StrReplace `LOCAL_CODE_PATH=…` etc.) | No CLI for this — the values are user-specific paths. |
| Download model weights (Step 4) | **CLI** (`complexa download --…`) | Dispatches to `env/download_startup.sh` (~1000 lines of bash with NGC URLs, retries, checksum-style skip-if-present). Don't try to replicate. |
| Validate env (Step 5) | **CLI** (`complexa validate env`) or `test -f .env && test -d $DATA_PATH` | They check the same thing — `.env` exists + `DATA_PATH` is an existing dir. Shallow smoke test only; for real readiness use `preflight.sh`. |
| Validate full design config (after picking a pipeline) | **CLI** (`complexa validate design CONFIG`) | Hydra defaults traversal + ckpt + reward/eval-weight checks worth not replicating. Caveat: reads the config YAML as-is — it rejects `++` overrides and does not validate overridden values. |

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
not yet exist and `complexa init` will fail with `command not found`.

**First, probe for the system (OS-level) build dependencies.** `env/build_uv_env.sh`
is silent about these — on a bare cloud VM (e.g. a fresh Brev / Lambda image)
they are usually missing, and the build dies deep inside a wheel compile
(`cpdb-protein` fails without `cc`/`make`; later `atomworks → openbabel → pybel`
fails to `import` without `libxrender1`). The errors at that depth are
confusing, so check up front and install before building:

```bash
# C toolchain (build-essential = cc + make + headers) and the libXrender shared
# library that OpenBabel/pybel dlopen at import time.
missing=()
command -v cc   >/dev/null 2>&1 || missing+=(build-essential)
command -v make >/dev/null 2>&1 || missing+=(build-essential)
ldconfig -p 2>/dev/null | grep -q libXrender || missing+=(libxrender1)
if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing system packages: ${missing[*]}"
    echo "Install with: sudo apt-get update && sudo apt-get install -y $(printf '%s ' "${missing[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' ')"
    # On Debian/Ubuntu:
    #   sudo apt-get update && sudo apt-get install -y build-essential libxrender1
fi
```

Install anything flagged (`sudo apt-get install -y build-essential libxrender1`),
then build the UV venv:

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

### Run `complexa init` (recommended — do not hand-roll this)

```bash
complexa init                    # UV runtime (default)
complexa init --runtime docker   # Docker runtime
complexa init --force            # Recreate .env from .env_example (drops any edits)
```

Always create `.env` with `complexa init`. Downstream commands (`complexa
design`, `complexa target add`, …) refuse to run until `.env` exists, and
`complexa init` is the only path guaranteed to produce the `.env` they expect.
Do **not** substitute a bare `cp .env_example .env` — that is a fragile
re-implementation that has caused "env not initialized" failures on fresh VMs.

If `.env` already exists and `--force` is not passed, only the runtime-dependent
lines are swapped — user edits in Step 3 are preserved across runtime flips.

`complexa init` copies `.env_example` → `.env`, swaps the `COMPLEXA_RUNTIME=`
line plus the `UV_*` ↔ `DOCKER_*` prefixes on the tool/data/cache path block,
and prepares the runtime activation that downstream commands expect — a bare
`cp` does not, which is why `complexa design` / `complexa target add` then abort
with "environment not initialized". You will still hand-edit the
machine-specific values in Step 3 — `init` sets the runtime, not your paths.

### Verify

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
| `LOCAL_DATA_PATH` | `/nvda/data/PFM_data` | Always — required, points at target PDBs |
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

For the full per-model destination breakdown and the ORD rsync fallback, see
[reference/downloads.md](reference/downloads.md).

Pick the smallest invocation that covers the user's goal, then run:

```bash
# A runnable protein-binder pipeline needs BOTH the Complexa weights AND the
# community models — AF2 is used as the generation-time reward (not just the
# eval refold), so '--complexa' alone crashes at sample 0.
complexa download --complexa --all      # protein binder (Complexa + community)
complexa download --complexa-ligand --all   # ligand binder
complexa download --complexa-ame --all      # AME / enzyme
complexa download --everything          # all three Complexa variants + community + optional
```

> **Do not download `--complexa` on its own and expect the protein-binder
> pipeline to run.** It fetches only the Complexa model; generation then fails
> immediately because the AF2 reward weights (part of `--all`) are missing.
> `--all` (community models) is required for every pipeline.

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

Smoke-check that `.env` is loadable:

```bash
complexa validate env
```

**Treat `validate env` as a shallow smoke test, not a guarantee.** It checks
exactly two things: (1) `.env` exists, and (2) `DATA_PATH` is set and points at
*some* directory that exists. That is all — it does **not** verify the directory
is the correct `PFM_data` (`DATA_PATH=/tmp` passes), does **not** check ckpt
files, tool binaries, AF2/RF3 weights, or GPU. A green `validate env` does not
mean a design run will succeed.

For the checks that actually predict whether a run works, use:

- `bash .claude/skills/_shared/scripts/preflight.sh` — GPU, disk, ckpt presence, tool binaries (Step 1).
- `complexa validate design <config>` — ckpts + reward/eval weights for a specific pipeline (see `complexa-design` Step 4). Note its limits there too: it reads the config YAML as-is and does not apply `++` overrides.

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
python3 .claude/skills/_shared/scripts/write_manifest.py \
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
| `complexa download` fails on NGC URL | Behind firewall / no internet | Use the ORD rsync fallback — see `reference/downloads.md` |
| `complexa download --status` shows ckpts present but `validate` fails | `.env` `CKPT_PATH` points elsewhere | Either move ckpts or edit `LOCAL_CHECKPOINT_PATH` in `.env` |
| GLIBC error on import | Ubuntu 20.04 with UV runtime | Re-run `complexa init --runtime docker` and use `./env/docker-ops.sh run` |

---

For the full `.env` reference (every key, defaults, failure modes), see
[reference/env_keys.md](reference/env_keys.md).

For the full download flag matrix, NGC URLs, destination layout, and the ORD
rsync fallback, see [reference/downloads.md](reference/downloads.md).

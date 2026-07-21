# Setup — standalone (open `complexa` CLI, no NIM)

This skill drives the **open Proteina-Complexa release** directly via its `complexa`
CLI on a GPU host. There is **no NIM / HTTP service** involved. Do this once per host.

## 0. Hardware & OS

- An NVIDIA GPU with working CUDA (validated on A100 80GB; A6000/H100/etc. fine).
  Keep **binder + target ≤ ~500 residues** (the AF2-reward path preallocates a large
  GPU slice). Ubuntu 22.04+ (the upstream UV env needs a recent glibc; use Docker on
  older systems).
- Python ≥ 3.10 for the skill's own scripts.

## 1. Install Proteina-Complexa + download weights

```bash
git clone https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa
cd Proteina-Complexa

# (a) UV env (recommended, no Docker):
./env/build_uv_env.sh                # FULL install — required (see note)
source .venv/bin/activate
# (b) OR the upstream image:  docker run --gpus all -it proteina-complexa

complexa init            # writes .env (Phase 1) — re-run `complexa init uv|docker` to emit env.sh
complexa download --complexa-all   # model + autoencoder checkpoints from NGC
export COMPLEXA_REPO=$PWD           # the skill reads this
```

Weights land in `ckpts/` (`complexa.ckpt`, `complexa_ae.ckpt`). The Complexa weights
download from **public NGC URLs — no NGC key required** (`complexa download --complexa`
for just the protein binder model, `--complexa-all` for all three). Verify:
`complexa validate design configs/search_binder_local_pipeline.yaml` shows both
checkpoints **Found**.

> **Use the FULL build — not `--minimal`.** The generation code path imports the
> colabdesign / JAX / dm-haiku stack **unconditionally** (via `proteinfoundation.search`),
> so generation fails on a `--minimal` env with `ModuleNotFoundError: jax` / `haiku`
> even when you use `single-pass` + the AF2 bypass. `./env/build_uv_env.sh` (full,
> default) installs these. On Python 3.12 the upstream `tmol` install may warn/fail —
> that's non-fatal for generation. (Validated clean on a fresh 2×H100 Linux host.)

## 2. Skill Python dependencies

The skill's Stage-1 tooling needs a few packages **in the same environment** that
runs the scripts (the Proteina-Complexa `.venv` is convenient):

```bash
# in the Proteina-Complexa venv (uv) or any py>=3.10 env:
uv pip install numpy gemmi pyyaml        # or: pip install numpy gemmi pyyaml
bash scripts/fetch_ipsae.sh              # vendors the MIT ipSAE script into vendor/ipsae/
```

> `gemmi` + `pyyaml` are required for Stage 1 (structure parsing, crop, target
> registration). `numpy` for validation scoring. ipSAE is fetched, not bundled.

## 3. AF2 reward — configure it OR bypass it (pick one)

Complexa's reward-guided search + its `full`-pipeline pre-gate use an **AF2-Multimer**
reward. It is **optional**:

- **Configure AF2** (enables reward-guided search + the AF2 pre-gate) — one command:
  ```bash
  bash scripts/setup_af2_params.sh            # downloads AF2 (public, no auth) + creates the params/ layout
  export AF2_DIR=$COMPLEXA_REPO/community_models/ckpts/AF2
  ```
  This handles the **`params/` symlink quirk**: colabdesign enumerates
  `$AF2_DIR/params/`, but the public AF2 tar extracts `params_model_*.npz` flat — the
  script creates the `params/` symlinks so model loading works. Requires **GPU JAX**
  (the full build installs `jax==0.4.x` with CUDA — verify `python -c "import jax;
  print(jax.devices())"` shows `cuda`). Then `best-of-n` / `beam-search` / `fk-steering`
  / `mcts` and the i_pTM>0.70 & pLDDT>0.70 pre-gate work.
- **Bypass AF2** (no AF2 params needed): use `single-pass` generation **and** drop the
  reward with the Hydra override `~generation.reward_model.reward_models.af2folding`.
  Selection then falls entirely to the **independent Boltz2 gate** (Stage 3). The
  helper does this for you: `complexa_design.py --af2-bypass`.

> If a run fails with `AssertionError: No model parameters found` /
> `model_*_multimer_v3 not found`, AF2 params aren't configured — run
> `setup_af2_params.sh` (configure) or use `--af2-bypass`. (Validated live: bypass →
> co-designed binder in ~30 s; best-of-n + AF2 → a binder passing the full gate.)

## 4. Optional analysis tools (full `complexa design` only)

The **analyze/diversity** stage of `complexa design` uses external binaries; they are
**not needed** for `complexa generate` + this skill's independent Boltz2 validation:

- `foldseek`, `mmseqs` (diversity), `dssp`, `sc` (shape complementarity).
- Pre-built `dssp`/`sc` are available from FreeBindCraft; set `FOLDSEEK_EXEC`,
  `MMSEQS_EXEC`, `DSSP_EXEC`, `SC_EXEC` in `.env`. If you only run generation +
  independent validation, you can ignore these (a config warning is expected).

## 5. Validation endpoint (Stage 3)

Independent refold uses a **Boltz2** (default) or **OpenFold3** NIM — a *different*
model family than Complexa's reward/evaluate:

- **Hosted:** `https://health.api.nvidia.com/v1/biology/mit/boltz2/predict` +
  `export NVIDIA_API_KEY=nvapi-...` → `--endpoint hosted`.
- **Local NIM:** `http://localhost:8000/...` (no auth) → `--endpoint local`. To stand one
  up yourself:

  ```bash
  docker login nvcr.io -u '$oauthtoken' -p "$NGC_API_KEY"      # once
  mkdir -p ~/nimcache_boltz2 && chmod 700 ~/nimcache_boltz2
  docker run -d --name boltz2 --gpus device=0 --shm-size=8g \
      -e NGC_API_KEY -v ~/nimcache_boltz2:/opt/nim/.cache -p 8000:8000 \
      nvcr.io/nim/mit/boltz2:latest                            # OpenFold3 NIM analogously
  curl -fsS http://localhost:8000/v1/health/ready && echo READY
  export BOLTZ2_URL=http://localhost:8000/biology/mit/boltz2/predict   # validator reads this
  ```

  **Profile note:** if the NIM exits with `NIMProfileIDNotFound` / "0 profiles" (some GPUs
  have no bundled profile), run `docker run --rm --gpus device=0 -e NGC_API_KEY
  nvcr.io/nim/mit/boltz2:latest list-model-profiles` and pin the profile matching **your**
  GPU's compute capability via `-e NIM_MODEL_PROFILE=<profile_id>` — pick it for the
  hardware you're on, don't reuse an id from another machine. (Fuller multi-NIM launch
  guide: the sibling `protein-binder-design/references/local-nim-setup.md`.)

`scripts/boltz2_refold.py` does the **holo** refolds (and chains `validate_binders.py`
for apo + gate). Both have **retry/backoff** for the hosted endpoint's rate limit
(HTTP 429); for large batches keep `--throttle` (default 5 s between holo calls) or use
a local Boltz2 NIM.

## 6. Environment variables (summary)

| Var | Purpose |
|---|---|
| `COMPLEXA_REPO` | path to the Proteina-Complexa checkout (required for generation) |
| `COMPLEXA_BIN` | `complexa` binary (default `complexa`; e.g. `<repo>/.venv/bin/complexa`) |
| `COMPLEXA_CONFIG` | pipeline YAML (default `configs/search_binder_local_pipeline.yaml`) |
| `COMPLEXA_OUTPUTS` | skill run-dir root (default `outputs`) |
| `COMPLEXA_TIMEOUT_S` | per-`complexa design` subprocess timeout (default 21600) |
| `NVIDIA_API_KEY` / `NGC_API_KEY` | hosted Boltz2/OF3 auth + NGC weight download |
| `AF2_DIR` | AF2-Multimer params (only if NOT bypassing AF2) |
| `RF3_CKPT_PATH`, `RF3_EXEC_PATH` | RoseTTAFold3 reward/eval (optional) |
| `FOLDSEEK_EXEC`, `MMSEQS_EXEC`, `DSSP_EXEC`, `SC_EXEC` | analyze-stage tools (optional) |

## 7. Verify the environment

```bash
bash scripts/check_setup.sh                       # one-shot readiness checklist
python scripts/preflight_design.py <target>       # Stage 1 end-to-end (no GPU)
```

## 8. End-to-end quickstart (no NIM)

```bash
export COMPLEXA_REPO=/path/to/Proteina-Complexa
export COMPLEXA_BIN=$COMPLEXA_REPO/.venv/bin/complexa   # if not on PATH

# Stage 1 — plan target + hotspots (no GPU)
python scripts/preflight_design.py <target>           # name, UniProt accession, or PDB

# Stage 2 — generate (lean: complexa generate + best-of-n; NOT full `complexa design`).
# Reward-guided (best, needs AF2 set up in step 3):
python scripts/complexa_design.py run --task-name <task-name> --run-name <run> \
    --algorithm best-of-n --num-samples 8 --seed 0 --out outputs/<run>
#   ...or AF2-free quick path:  add --af2-bypass --algorithm single-pass

# Stage 3 — independent Boltz2 HOLO refold (+ apo + ipSAE + gate + rank) in one step.
# Point --pdbs at the generated complexes (under $COMPLEXA_REPO/inference/...):
python scripts/boltz2_refold.py --run-dir outputs/<run> \
    --pdbs outputs/<run>/inference/*.pdb \
    --endpoint hosted --validate scripts/validate_binders.py
# -> outputs/<run>/ranked_binders.json (+ .csv): every design with pass/fail + metrics
```

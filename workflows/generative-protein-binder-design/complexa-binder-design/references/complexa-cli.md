# Driving Proteina-Complexa (the `complexa` CLI)

Generation runs through the open Proteina-Complexa release and its `complexa` Hydra
CLI. This page is the operational summary; the repo's own docs are authoritative:
`README.md`, `docs/INFERENCE.md`, `docs/CONFIGURATION_GUIDE.md`,
`docs/EVALUATION_METRICS.md` in <https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa>.

## One-time setup

```bash
git clone https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa
cd Proteina-Complexa
./env/build_uv_env.sh && source .venv/bin/activate   # or: docker build -f env/docker/Dockerfile .
complexa init                 # writes .env
complexa download --complexa-all   # model + autoencoder checkpoints from NGC
```

Set `COMPLEXA_REPO=/path/to/Proteina-Complexa` so the helper script and the agent
know where to run. Checkpoints are configured in the pipeline YAML (`ckpt_path`,
`ckpt_name`, `autoencoder_ckpt_path`) or overridden on the CLI (below).

## Pipelines (config + model)

| Pipeline | Config | NGC model |
|---|---|---|
| **Protein binder** (this skill) | `configs/search_binder_local_pipeline.yaml` | `proteina_complexa` |
| Ligand binder | `configs/search_ligand_binder_local_pipeline.yaml` | `proteina_complexa_ligand` |
| AME (motif + ligand) | `configs/search_ame_local_pipeline.yaml` | `proteina_complexa_ame` |

Each pipeline runs four stages: **generate → filter → evaluate → analyze**
(`complexa design` runs all four; `complexa generate|filter|evaluate|analyze` run them
individually).

## CLI verbs

| Command | Use |
|---|---|
| `complexa validate design <config>` | resolve the config (catches missing ckpt/env vars before GPU time) |
| `complexa design <config> ++…` | full pipeline: generate → filter → evaluate → analyze |
| `complexa generate <config> ++…` | generation only (skip evaluate/analyze) |
| `complexa target add/list/show` | register / inspect design targets |
| `complexa status <config>` | check outputs of a run |

## Key Hydra overrides (`++key=value`)

| Override | Meaning |
|---|---|
| `++run_name=<str>` | run label (appears in output paths) |
| `++generation.task_name=<name>` | which registered target to design against |
| `++generation.search.algorithm=<algo>` | `single-pass` · `best-of-n` · `beam-search` · `fk-steering` · `mcts` |
| `++generation.dataloader.dataset.nres.nsamples=<int>` | number of candidates to sample |
| `++seed=<int>` | reproducibility |
| `++gen_njobs=<int>` / `++eval_njobs=<int>` | GPU parallelism (one GPU per job) |
| `++ckpt_path=<dir>` `++ckpt_name=complexa.ckpt` `++autoencoder_ckpt_path=<file>` | checkpoint locations |

> Hotspots and binder length are **target-dict-driven** (set per target via
> `complexa target add` / `configs/targets/targets_dict.yaml`), not scalar CLI
> overrides. Register the target first, then select it with `generation.task_name`.

## Reward-guided search & rewards

`best-of-n`/`beam-search`/`fk-steering`/`mcts` steer denoising by a reward built from
structure-prediction confidence and interface H-bond energies. Reward weights live in
`configs/pipeline/binder/binder_generate.yaml` and resolve weights from `.env`:

```
AF2_DIR=/path/to/AF2            # AlphaFold2 params (af2folding reward + AF2 evaluate)
RF3_CKPT_PATH=/path/to/rf3.ckpt # RoseTTAFold3 reward / evaluate
RF3_EXEC_PATH=/path/to/bin/rf3
```

If a reward model's weights are absent, drop it (e.g. disable `af2folding`) and use
`single-pass`, or comment the reward out — then rely on this skill's independent
Boltz2 gate for selection.

## Example: design binders for a registered target

```bash
cd "$COMPLEXA_REPO"
complexa design configs/search_binder_local_pipeline.yaml \
    ++run_name=<run> \
    ++generation.task_name=<task-name> \
    ++generation.search.algorithm=best-of-n \
    ++generation.dataloader.dataset.nres.nsamples=8 \
    ++seed=0 ++gen_njobs=1 ++eval_njobs=1
complexa status configs/search_binder_local_pipeline.yaml
```

`<task-name>` is a registered target. The repo ships example targets (run
`complexa target list` in your checkout to see them); for your own target, register it
first (`complexa target add <task-name> --pdb target.pdb --chain A --span <lo-hi>
--hotspots <res,res> --binder-length <lo-hi>`) and pass
`++generation.task_name=<task-name>`. See `scripts/complexa_design.py` for a thin
driver that assembles this command and discovers outputs.

## Outputs

- `./inference/…` — generated **complex PDBs** (target chain + binder chain; the
  binder chain carries the co-designed sequence — read it directly).
- `./evaluation_results/…` — Complexa's own per-sample CSVs (AF2/RF3/ESMFold metrics).
- `./logs/…` — Hydra run logs.

This skill consumes the `./inference` complex PDBs and re-validates them
independently (Boltz2/OpenFold3) — see `validation.md`.

## GPU / memory notes

- **Keep binder + target ≤ ~500 residues.** Complexa builds an O(n²) pair-feature
  map; crop large targets to a window around the epitope (preserve numbering).
- The AF2-Multimer reward (JAX) preallocates a large share of an 80 GB GPU. If you
  hit OOM with rewards enabled, set `XLA_PYTHON_CLIENT_PREALLOCATE=false` (and a
  `MEM_FRACTION`) so PyTorch and the AF2 reward coexist, or reduce the pool size.
- Increase `gen_njobs`/`eval_njobs` to your GPU count to parallelize.

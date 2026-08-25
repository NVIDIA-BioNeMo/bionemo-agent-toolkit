---
name: complexa-design
description: >
  End-to-end Proteina-Complexa design pipeline driver. Use when the user wants to
  "design a binder", "design binders for X", "run complexa design", "de novo
  binder", "PDL1 binder", "TrkA binder", "design proteins for target", "protein
  binder design", "ligand binder", "design a small-molecule binder", "ATP-binding
  protein", "AME motif scaffolding", "scaffold a motif near a ligand", "motif +
  ligand design", "enzyme scaffolding", "flow matching protein design",
  "beam-search binder", "FK steering", "MCTS protein design", or "refold with AF2
  / RF3 / ESMFold", or wants success rates, interface pAE, scRMSD, or FoldSeek
  diversity from one command. Drives the complexa design pipeline from target
  picking to manifest emission and reports how many designs passed.
compatibility: "complexa CLI installed (pip install -e .); environment file populated; 1x CUDA GPU >=40GB VRAM (A100/H100/L40S); 24 CPUs; ~50GB disk"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Complexa Design Skill

Drive the full four-stage `complexa design` pipeline: generate (flow matching +
search) -> filter (top-N by reward) -> evaluate (refold with AF2/RF3) ->
analyze (success rate, FoldSeek/MMseqs diversity). Pick the right pipeline
config for the design intent, validate the run upfront so the user does not
discover a missing ckpt mid-folding, run it, and emit a replayable manifest +
per-design success CSV.

## What this skill enables

- Protein binder design for protein targets (AF2 reward + ColabDesign refold).
- Ligand binder design for small-molecule targets (RF3 reward + RF3 refold).
- AME motif scaffolding with ligand context (motif + ligand features, RF3).
- Search-based optimization: single-pass, best-of-n, beam-search, fk-steering, mcts.
- Refold backends: ColabDesign (AF2), RF3, Boltz2, ESMFold (fast iteration).
- Pass-rate + diversity analysis with per-`result_type` thresholds.

## Step 1: Pre-flight

Always run the shared preflight before launching a design — generation needs the
GPU and the right checkpoint, evaluation needs AF2/RF3 weights and tool
binaries. Bail early if the host cannot run the chosen pipeline.

```bash
bash .claude/skills/_shared/scripts/preflight.sh
```

Read `./complexa_setup/preflight.json` and bail if any of these are missing for
the chosen pipeline:

- `gpu.available: false` -> all pipelines fail.
- `gpu.vram_gb < 40` -> generation OOMs at default `batch_size: 16`; lower to 8.
- `ckpts.complexa[.ckpt]` -> required for protein binder.
- `ckpts.complexa_ligand[.ckpt]` -> required for ligand binder.
- `ckpts.complexa_ame[.ckpt]` -> required for AME.
- `env.AF2_DIR` missing -> protein binder default eval (`colabdesign`) fails.
- `env.RF3_CKPT_PATH` or `env.RF3_EXEC_PATH` missing -> ligand binder / AME default eval (`rf3_latest`) fails.

If a ckpt is missing, point at `complexa-setup` and have the user run
`complexa download --complexa-<variant>` first.

## Step 2: Pick the pipeline

Complexa has **one default pipeline (protein binder) and two extensions**
(ligand binder, AME / enzyme). The pipeline is selected entirely
by the `configs/search_*_pipeline.yaml` you pass to `complexa design` — each
YAML pins its own model checkpoint, autoencoder, targets dict, default reward,
and default refold backend. Switching pipelines is just "swap the config path
and the target name comes from a different dict".

### Default — protein binder

```bash
complexa design configs/search_binder_local_pipeline.yaml \
    ++run_name=pdl1_v1 ++generation.task_name=02_PDL1
```

Use this when the user says "design a binder for X", "PDL1 binder",
"de novo binder", "design proteins for a target", etc. — i.e. the target is
a protein surface. The config pins `complexa.ckpt` + `complexa_ae.ckpt`, reads
targets from `configs/targets/targets_dict.yaml`, rewards with AF2
(`af2folding`), inverse-folds with SolubleMPNN, and evaluates with
ColabDesign / AF2. **If the user did not specify, this is what they want.**

### Extension A — ligand binder (small-molecule pocket)

```bash
complexa design configs/search_ligand_binder_local_pipeline.yaml \
    ++run_name=v11_v1 ++generation.task_name=39_7V11_LIGAND \
    ++metric.binder_folding_method=rf3_latest
```

Switch to this when the user says "ligand binder", "small-molecule pocket",
"SMILES target", "ATP-binding protein", or names a target ending in
`_LIGAND` / from the FAD / SAM / OQO / 7V11 / etc. families. The config
**also activates LoRA** (`r=32`, `lora_alpha=64`) which is required for the
released ligand checkpoint — leave the `lora:` block alone.

### Extension B — AME / motif + ligand (enzyme scaffolding)

```bash
complexa design configs/search_ame_local_pipeline.yaml \
    ++run_name=ame_chm ++generation.task_name=M0096_1chm
```

Switch to this when the user says "scaffold a motif near a ligand",
"active-site design", "enzyme scaffolding", "AME", or names a target like
`M0024_1nzy`, `M0096_1chm` (the `M####_<pdb>` AME task naming). The config sets
`env_vars.USE_V2_COMPLEXA_ARCH=True` (the CLI runner injects it into the
subprocess) and uses both `MotifFeatures` and `LigandFeatures`. Default search
is `single-pass`; switch to `best-of-n` only if you also enable the
`CompositeRewardModel` (commented out in `ame_generate.yaml`).

### Pipeline cheat sheet — what changes when you switch

| Knob | Protein binder (default) | Ligand binder | AME (enzyme) |
|---|---|---|---|
| **Pipeline YAML** | `configs/search_binder_local_pipeline.yaml` | `configs/search_ligand_binder_local_pipeline.yaml` | `configs/search_ame_local_pipeline.yaml` |
| **Model ckpt** | `complexa.ckpt` | `complexa_ligand.ckpt` | `complexa_ame.ckpt` |
| **Autoencoder ckpt** | `complexa_ae.ckpt` | `complexa_ligand_ae.ckpt` | `complexa_ame_ae.ckpt` |
| **Targets dict** | `configs/targets/targets_dict.yaml` | `configs/targets/ligand_targets_dict.yaml` | `configs/design_tasks/ame_dict_v2.yaml` |
| **Task-name pattern** | `<NN>_<NAME>` (e.g. `02_PDL1`, `22_DerF21`) | `<NN>_<PDB>_LIGAND` (e.g. `39_7V11_LIGAND`) | `M####_<pdb>` (e.g. `M0096_1chm`) |
| **`USE_V2_COMPLEXA_ARCH`** | (unset → v1) | (unset → v1) | `"True"` (set in YAML) |
| **LoRA** | (none) | required (`r=32, alpha=64`) | required |
| **Default search algo** | `best-of-n` | `best-of-n` | `single-pass` |
| **Reward model** | AF2 (`af2folding`) | RF3 (`rf3folding`) | `null` (no reward at default) |
| **Inverse folder** | `soluble_mpnn` | `ligand_mpnn` | `ligand_mpnn` |
| **Default refold backend** | `colabdesign` (AF2) | `rf3_latest` | `rf3_latest` |
| **Analysis `result_type`** | `protein_binder` | `ligand_binder` | `motif_ligand_binder` |
| **Required ckpts (`complexa download`)** | `--complexa --all` (AF2 in community) | `--complexa-ligand --all` (RF3 in community) | `--complexa-ame --all` (RF3 in community) |

For the full per-pipeline breakdown (reward weights, success thresholds,
analysis modes), see [reference/pipelines.md](reference/pipelines.md).

## Step 3: Gather parameters

Use AskUserQuestion to fill in the four parameters that vary every run. Default
to sensible production settings if the user has no preference.

- **Target name** — must be a key in the relevant dict (`targets_dict.yaml` for
  protein binder, `ligand_targets_dict.yaml` for ligand, `ame_dict_v2.yaml` for
  AME). If the user names a target that is not in the dict, hand off to
  `complexa-target` to add it first.
- **Run name** — a short identifier appended to the output dir (e.g. `pdl1_v1`).
- **Search algorithm** — default to `beam-search` with `beam_width=8` and
  `n_branch=4` for production. Use `single-pass` for a quick smoke test.
- **Evaluation refold backend** — protein binder defaults to `colabdesign`
  (AF2); ligand/AME default to `rf3_latest`. Use `esmfold` for fast iteration
  (worse but seconds per sample).

## Step 4: Validate

Validate before running. This is cheap (seconds) and catches missing ckpts,
missing env vars, unknown override keys, and missing target entries — all of
which would otherwise abort the pipeline mid-evaluation after hours of
generation.

```bash
complexa validate design configs/search_binder_local_pipeline.yaml \
    ++generation.task_name=02_PDL1 \
    ++metric.binder_folding_method=colabdesign
```

The validator returns non-zero on failure and prints a pass/fail report.
Re-run the command with the suggested overrides until it returns clean.

## Step 5: Run the pipeline

`complexa design` is the right tool for the full 4-stage run — it orchestrates
`generate → filter → evaluate → analyze` as sequential subprocesses with a
shared run name, log dir, and multi-GPU split (see `run_design_pipeline` in
`src/proteinfoundation/cli/cli_runner.py`). Re-implementing that manually
loses the per-stage log routing and progress prints.

Use `++` (forced) Hydra overrides; they apply to all stages. The minimal
production protein-binder invocation:

```bash
complexa design configs/search_binder_local_pipeline.yaml \
    ++run_name=pdl1_v1 \
    ++generation.task_name=02_PDL1 \
    ++generation.search.algorithm=beam-search \
    ++generation.search.beam_search.beam_width=8 \
    ++metric.binder_folding_method=colabdesign
```

For ligand binder / AME, swap the pipeline YAML and target name per Step 2's
cheat sheet — every other override above is pipeline-agnostic and can be
reused as-is.

Add `--verbose` to stream logs to the terminal instead of `./logs/`. The skill
does not poll progress — the user re-invokes if they want a status; point them
at `complexa status` and `./logs/design_pipeline_*/`.

### Direct module invocation (debug fallback)

To debug a single stage without pipeline orchestration, invoke the underlying
Hydra module directly. `complexa generate CONFIG` is just a logged subprocess
wrapper around this:

```bash
python -m proteinfoundation.generate \
    --config-path "$(realpath configs)" \
    --config-name search_binder_local_pipeline \
    ++run_name=debug_pdl1 \
    ++generation.task_name=02_PDL1
```

Same pattern for `proteinfoundation.{filter,evaluate,analyze}`. Use this when
you want to attach `ipdb`, run under `nsys`, or skip the pipeline log dir.
Prefer `complexa generate/filter/evaluate/analyze` for normal one-shot runs
(you get logging and parallel job splitting for free).

**AME-specific gotcha (when running AME with RF3 refold)**: RF3 will try to
complete missing atoms on the ligand based on its CCD code, which produces
shape errors in RMSD calculations and the wrong structure. Before RF3 sees the
PDB, rename the ligand residue to `L:0` so RF3 treats it as a generic ligand
and skips atom completion. If your AME generation outputs already encode the
ligand this way (the canonical Complexa pipeline does), no extra step is
needed; otherwise patch each PDB with `atomworks.io`:

```python
from atomworks.io import load_any, to_pdb_file
atom_array = load_any("my_design.pdb")[0]
ligand_mask = atom_array.chain_id == "A"
atom_array.res_name[ligand_mask] = "L:0"
to_pdb_file(atom_array, "my_design_rf3_ready.pdb")
```

Same applies if you're piping AME outputs into the `complexa-evaluate-pdbs`
skill with an RF3 backend. Skip the rename for AF2/colabdesign refold or for
non-AME pipelines.

Wall-clock at default (`nsteps=400`, `beam_width=8`, `batch_size=16`, 100
designs, colabdesign eval) is ~30–120 minutes on a single A100/H100.

## Step 6: Collect results

Outputs land in two directories. Surface both:

```bash
ls ./inference/${CONFIG_STEM}_${TASK}_*${RUN_NAME}/   # generated PDBs + filter
ls ./evaluation_results/${RUN_NAME}/                  # per-design CSV + analysis
```

Read the combined results CSV and summarize:

```bash
ls ./evaluation_results/*/binder_results_*_combined.csv
ls ./evaluation_results/*/motif_binder_results_*_combined.csv  # AME
ls ./evaluation_results/*/res_filter_*_pass_*.csv              # success rate
ls ./evaluation_results/*/res_div_foldseek_*.csv               # FoldSeek diversity
```

Pull the success rate from `res_filter_binder_pass_*.csv`, the per-design
metrics (interface pAE, pLDDT, scRMSD) from the combined CSV, and FoldSeek
TM-score diversity from `res_div_foldseek_*.csv`. Report top-N designs by
i_pAE (protein binder) or min_ipAE (ligand binder).

## Step 7: Emit manifest

Drop a JSON manifest beside the results so the run is replayable. The shared
helper captures the command, config, git SHA, and pointers to the result CSVs.

```bash
python3 .claude/skills/_shared/scripts/write_manifest.py \
    --output-dir ./evaluation_results/${RUN_NAME} \
    --command "complexa design configs/search_binder_local_pipeline.yaml ++run_name=${RUN_NAME} ++generation.task_name=${TASK}" \
    --skill complexa-design \
    --out ./run_manifest.json
```

Surface the manifest path and the result CSV to the user.

## Most-common overrides

The 10 overrides that cover ~90% of runs. Full reference (every key, type,
default) is in [reference/overrides.md](reference/overrides.md).

| Override | Default | What it controls |
|----------|---------|------------------|
| `++generation.task_name=<name>` | (per config) | Which target / AME task to design for |
| `++run_name=<str>` | (config stem) | Output dir suffix and CSV tag |
| `++generation.search.algorithm=beam-search` | `best-of-n` (binder/ligand), `single-pass` (AME) | Search strategy |
| `++generation.search.beam_search.beam_width=8` | `4` | Beam-search width (more = better designs, slower) |
| `++generation.args.nsteps=200` | `400` | Diffusion steps (fewer = faster, lower quality) |
| `++generation.dataloader.batch_size=8` | `16` (binder/ligand/AME) | Drop to 8 on a 40GB GPU |
| `++generation.filter.filter_samples_limit=500` | `1000` | Top-N samples to keep after filtering |
| `++metric.binder_folding_method=esmfold` | `colabdesign` (binder), `rf3_latest` (ligand/AME) | Evaluation refold backend |
| `++metric.num_redesign_seqs=8` | `2` | ProteinMPNN/LigandMPNN/SolubleMPNN sequences per design |
| `++aggregation.success_thresholds.i_pAE.threshold=10.0` | `7.0` (protein binder) | Loosen / tighten success criteria |

## Hardware requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| GPU | 1x CUDA GPU, 40 GB VRAM | A100 / H100 / L40S, 80 GB VRAM |
| CPUs | 16 | 24 (the `ncpus_` default in every pipeline config) |
| Disk | 50 GB at `./inference/` + `./evaluation_results/` | 200 GB for sweep runs |
| RAM | 32 GB | 64 GB+ |

Typical wall-clock for 100 designs, `beam_width=8`, default `nsteps=400`:

- Protein binder + colabdesign refold: ~60–120 min on 1x A100/H100.
- Ligand binder + RF3 refold: ~90–180 min (RF3 dominates).
- AME + RF3 refold: ~120–240 min.
- Any pipeline + ESMFold refold: ~30–60 min (fast iteration).

Bumping `gen_njobs=2` and `eval_njobs=2` halves wall-clock on a 2-GPU host. See
`.claude/skills/_shared/reference/hardware.md` for per-pipeline VRAM tables.

## Troubleshooting (common cases)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `CUDA out of memory` in generate | `batch_size: 16` too big on 40GB GPU | `++generation.dataloader.batch_size=8` |
| `CUDA out of memory` in evaluate | AF2 / RF3 batched too aggressively | `++eval_njobs=1` and `++metric.num_redesign_seqs=2` |
| `InterpolationKeyError: AF2_DIR` | colabdesign eval but `.env` does not set `AF2_DIR` | Set `AF2_DIR` in `.env` or `++metric.binder_folding_method=esmfold` |
| `InterpolationKeyError: RF3_CKPT_PATH` | RF3 eval but RF3 not installed | `complexa download --all` or switch eval backend |
| `KeyError: 'task_name' not in target_dict_cfg` | Target not in `targets_dict.yaml` / `ligand_targets_dict.yaml` / `ame_dict_v2.yaml` | Use `complexa-target` skill to add it |
| 0 designs pass success thresholds | Defaults too strict for this target | Loosen via `++aggregation.success_thresholds.*` |

For the full list (chain-ID mismatches, hotspot residues, ligand residue
renaming for RF3, missing inverse-folding models, etc.) see
[reference/troubleshooting.md](reference/troubleshooting.md).

---

For per-pipeline details (which model, reward, inverse folding, evaluation
backend, `result_type`, LoRA settings, `USE_V2_COMPLEXA_ARCH` toggle), see
[reference/pipelines.md](reference/pipelines.md).

For the full override reference (every `generation.*`, `metric.*`,
`aggregation.*` key with type, default, example, and effect), see
[reference/overrides.md](reference/overrides.md).

For all troubleshooting cases (cause + fix + source), see
[reference/troubleshooting.md](reference/troubleshooting.md).

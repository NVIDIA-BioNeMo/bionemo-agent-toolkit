---
name: complexa-sweep
description: Use this skill whenever the user wants to run a parameter sweep over a Proteina-Complexa design pipeline — cartesian-product hyperparameter scans, Pareto search over generation/reward/evaluation knobs, or any "compare configurations" workflow. Trigger phrases include "sweep beam width", "sweep nsteps", "hyperparameter sweep", "parameter scan", "scan beam_width and temperature", "compare configurations", "find the best generation params", "what's the optimal nsteps", "Pareto search for binder quality vs wall-clock", "complexa sweep", "tune Complexa", "ablate the reward weights", "configs/sweeps", "--sweeper", "run beam_width.yaml". This is the only skill that owns sweeper YAML authoring, cartesian-product expansion, and per-config result ranking. For cluster submission mechanics see the `complexa-slurm` skill.
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# complexa-sweep

Run cartesian-product parameter sweeps over Proteina-Complexa design pipelines. Pick or author a sweeper YAML in `configs/sweeps/`, launch N runs via the SLURM launcher (the only launch path that accepts `--sweeper`), then aggregate per-config success metrics into a ranked summary CSV plus a manifest.

> **No `complexa` CLI involvement.** Sweeps are driven by `script_utils/generate_inference_configs.py` (Python) and `slurm_utils/launch_*.sh` (Bash) — `complexa design` does **NOT** accept `--sweeper`. To sweep locally without SLURM, generate configs with `generate_inference_configs.py --sweeper ...` and then loop `complexa design` over the resulting `configs/inference_configs/inf_*.yaml` files yourself.

## What this skill enables

- Pick an existing sweeper YAML from `configs/sweeps/` (beam_width, bb_ca_temperature, search_replicas, example).
- Author a new sweeper YAML with arbitrary dot-notation axes (cartesian product).
- Launch the sweep via the SLURM launcher (preferred) or generate configs + loop locally (fallback).
- Walk per-config output directories and parse the analyze-step CSV from each.
- Emit `sweep_summary.csv` (one row per config: axis values + success rate + mean iPAE + diversity) and `sweep_manifest.json`.
- Identify the best config by success rate and the Pareto frontier (wall-clock vs success).

## Step 1: Pre-flight

```bash
bash .claude/skills/_shared/scripts/preflight.sh
```

Read `./complexa_setup/preflight.json`. A sweep multiplies GPU time by the number of configs, and an innocent-looking request can be enormous — "beam width 16, 400 steps, 256 configs, every target in the repo" is thousands of GPU-hours.

**Estimate cost first, then gate on it.** Compute the estimate explicitly before doing anything else:

```
total_runs      = n_configs × n_targets
gpu_hours       ≈ total_runs × per_run_minutes / 60
```

Use `per_run_minutes ≈ 30–90` for `search_binder_pipeline` on one A100 (scales with binder length × `nsteps` × `beam_width`; see `_shared/reference/hardware.md`). Then:

- **Always** show the estimate and require explicit confirmation:
  > "This sweep is N configs × T targets = R runs ≈ H GPU-hours (≈ $C at cloud rates). Proceed? (y / reduce / cancel)"
- **Hard gate** when the estimate is large. If `gpu_hours` exceeds a budget the user has not pre-approved (default threshold: **100 GPU-hours**), do **not** launch — stop and make the user confirm the spend or narrow the sweep (fewer axes/values, fewer targets, smaller `beam_width`/`nsteps`). Never silently submit a 1000+ GPU-hour job.

If `gpu.available=false` and you do not have cluster access via `complexa-slurm`, stop — sweeps are not feasible on CPU.

## Step 2: Pick the pipeline + target

Use the same dialogue as `complexa-design` — do **not** duplicate it here. See `.claude/skills/complexa-design/SKILL.md` Step 2 ("Pick the pipeline") and Step 3 ("Pick the target"). Capture:

- `pipeline_config_name` — e.g. `search_binder_pipeline` (SLURM) or `search_binder_local_pipeline` (local-ish).
- `task_name` — e.g. `22_DerF21`, `02_PDL1`. Will be passed as `--override generation.task_name=<task>`.
- `run_name` — short tag for output dir naming.

> **Every `task_name` must already exist in the target dict before the sweep launches.** A sweep is a non-interactive, scripted caller: the per-config bash glue and `complexa target add` do **not** validate target names or `target_input`, so a typo'd or unregistered target produces N failed runs (or, worse, silently bad inputs) with no agent in the loop to catch it. Confirm each target with `complexa target show <task_name>` first; if any is missing, register it via the `complexa-target` skill **before** generating configs, not mid-sweep.

## Step 3: Pick or author the sweeper YAML

Sweeper YAMLs live in `configs/sweeps/`. Each key is a dot-notation Hydra path; each value is a list. The cartesian product becomes N configs.

### Canned sweepers

| File | Axis | Values | Configs |
|---|---|---|---|
| `configs/sweeps/beam_width.yaml` | `generation.search.beam_search.beam_width` | 1, 2, 4, 8 | 4 |
| `configs/sweeps/bb_ca_temperature.yaml` | `generation.model.bb_ca.simulation_step_params.sc_scale_noise` | 0.1, 0.4 | 2 |
| `configs/sweeps/search_replicas.yaml` | `generation.search.best_of_n.replicas` | 1, 4, 16, 64 | 4 |
| `configs/sweeps/example.yaml` | beam_width × nsteps | (2,4) × (200,400) | 4 |

If one matches the user's intent, use it as-is. Otherwise author a new file.

### Authoring a new sweeper

Minimal multi-axis example (saved to `configs/sweeps/my_sweep.yaml`):

```yaml
# 3 beam widths × 2 nsteps = 6 configs
generation.search.beam_search.beam_width:
  - 2
  - 4
  - 8

generation.args.nsteps:
  - 200
  - 400
```

Rules (from `script_utils/generate_inference_configs.py:load_sweeper_file`):

- Top-level mapping only. Keys are dot-notation Hydra paths.
- Values must be **lists**. A scalar is auto-wrapped into a single-element list (which pins a value without adding a dimension).
- Cartesian product: total configs = product of list lengths. Two 4-value axes = 16 configs; budget accordingly.
- If a key appears in both the sweeper file and an `--override`, the override wins and that axis collapses.

See `reference/sweep_axes.md` for the full catalogue of swept keys (typical ranges, cost multipliers, what improves/regresses).

### Dry-run preview before launching

Always confirm the config count first:

```bash
python3 script_utils/generate_inference_configs.py \
    --config_name search_binder_pipeline \
    --sweeper configs/sweeps/my_sweep.yaml \
    --override generation.task_name=22_DerF21 \
    --run_name my_sweep \
    --dryrun
```

The output lists every axis + value list and prints `DRY RUN — would generate N config pair(s)`.

> **This dry-run is NOT a cold-start "safe evidence" command — it needs the full
> Complexa venv.** Two traps on a fresh VM: (1) Ubuntu cloud images ship only
> `python3`, no `python` symlink, so use `python3` (or activate the venv and use
> its `python`); and (2) `generate_inference_configs.py` imports `hydra`, so it
> only runs *after* `complexa-setup` Step 1b has built/activated `.venv`. On a
> true cold start it will fail with `ModuleNotFoundError: No module named
> 'hydra'`. Run it as a post-setup verification, not before the environment is
> built. (If you only need the config count without the venv, the cartesian
> product is just the product of the sweeper file's list lengths.)

## Step 4: Run the sweep

There are two execution paths. Pick based on whether the user has SLURM access.

### Path A (preferred): SLURM launcher with `--sweeper`

```bash
./slurm_utils/launch_protein_binder_search.sh \
    --sweeper configs/sweeps/my_sweep.yaml \
    --override generation.task_name=22_DerF21
```

This is the only flag-supported entrypoint. The launcher: (1) generates N config pairs via `generate_inference_configs.py`, (2) names the run `{base}-search-{sweeper_basename}-{target}`, (3) rsyncs to the cluster (or runs in place with `--on-cluster`), (4) submits a SLURM array, one task per config. For cluster mechanics — partition selection, monitoring, log retrieval — defer to `.claude/skills/complexa-slurm/SKILL.md`.

### Path B (fallback): local generate + manual loop

If the user does not have SLURM, generate the config pairs locally and loop `complexa design` over them yourself. `complexa design` does **not** parse `--sweeper`; it only accepts a single config file + Hydra overrides.

```bash
# 1. Generate one inf_*.yaml per combination (needs the activated .venv).
python3 script_utils/generate_inference_configs.py \
    --config_name search_binder_local_pipeline \
    --sweeper configs/sweeps/my_sweep.yaml \
    --override generation.task_name=22_DerF21 \
    --run_name my_sweep

# 2. Loop complexa design over each generated config.
for cfg in configs/inference_configs/inf_*_my_sweep.yaml; do
    complexa design "$cfg" || echo "FAILED: $cfg"
done
```

This serialises the sweep on a single GPU — be honest with the user that wall-clock = N × per-run.

## Step 5: Collect results

Each swept config writes to its own `./inference/inf_{idx}_{run_name}/` directory; the analyze step writes `./evaluation_results/eval_{idx}_{run_name}/results_*.csv`. After the sweep finishes:

```bash
ls -d ./inference/inf_*_my_sweep/
ls ./evaluation_results/eval_*_my_sweep/results_*.csv
```

For each config, parse the analyze CSV (one row per generated binder). Standard columns used for ranking: `i_pae`, `i_plddt`, `sc_rmsd`, `binder_seq`, `passes_filter` (bool). If `passes_filter` is missing, derive a success flag with the user's chosen thresholds (defaults: `i_pae < 10`, `i_plddt > 0.7`, `sc_rmsd < 2.0` — confirm with user).

## Step 6: Rank configs

Emit `sweep_summary.csv` to the run directory. One row per config:

| Column | How to compute |
|---|---|
| `config_id` | The `{idx}` from `inf_{idx}_{run_name}` |
| `<axis_1>`, `<axis_2>`, ... | The swept value at this combination (read from the per-config `inf_*.yaml`) |
| `n_samples` | Row count in the analyze CSV |
| `success_rate` | `passes_filter.mean()` |
| `mean_i_pae` | `i_pae.mean()` (lower = better) |
| `mean_i_plddt` | `i_plddt.mean()` (higher = better) |
| `diversity_score` | Unique sequence count / `n_samples` (or use TM-score clustering if available) |
| `wall_clock_min` | From the per-config log timestamps |

Then report:

- **Best config** = argmax of `success_rate`. Tie-break on `mean_i_pae` (lower).
- **Pareto frontier** over (`wall_clock_min`, `success_rate`): a config is on the frontier iff no other config is both faster AND has higher success rate.

Print the best config + the frontier to the terminal. Save the full table to `sweep_summary.csv`.

## Step 7: Emit manifest

Write `sweep_manifest.json` capturing the full sweep state:

```json
{
  "kind": "sweep",
  "run_name": "my_sweep",
  "pipeline_config": "search_binder_pipeline",
  "sweeper_file": "configs/sweeps/my_sweep.yaml",
  "overrides": ["generation.task_name=22_DerF21"],
  "n_configs": 6,
  "configs": [
    {"config_id": 0, "inf_yaml": "configs/inference_configs/inf_0_my_sweep.yaml",
     "axis_values": {"beam_width": 2, "nsteps": 200}, "results_csv": "..."},
    ...
  ],
  "summary_csv": "./sweep_runs/my_sweep/sweep_summary.csv",
  "best_config_id": 4,
  "pareto_frontier": [0, 2, 4]
}
```

Use the shared helper:

```bash
python3 .claude/skills/_shared/scripts/write_manifest.py \
    --kind sweep \
    --run-name my_sweep \
    --sweeper configs/sweeps/my_sweep.yaml \
    --summary-csv ./sweep_runs/my_sweep/sweep_summary.csv \
    --out ./sweep_runs/my_sweep/sweep_manifest.json
```

## Recommended sweep recipes

| Symptom | Sweep this | Why |
|---|---|---|
| Quality not good enough | `beam_width × nsteps` (use `example.yaml` as a starting point) | Both raise compute → quality; find the cheapest combination that lands. |
| Too slow / want speed-up | `nsteps` downward (e.g. `[100, 200, 400]`) with fixed `beam_width=4` | Find the smallest nsteps that retains success rate. |
| Mode collapse / low diversity | `generation.model.bb_ca.simulation_step_params.sc_scale_noise` (use `bb_ca_temperature.yaml`) | Higher noise → more diverse backbones. |
| Reward over-fitting (high reward, bad metrics) | `generation.reward_model.reward_models.af2folding.reward_weights.{i_pae, plddt}` ratio | Re-balance composite reward. |
| Want statistical robustness on one config | `search_replicas.yaml` (`best_of_n.replicas`) | Same config, more samples → tighter success-rate estimate. |
| Algorithm shoot-out | `generation.search.algorithm` over `[single-pass, best-of-n, beam-search, fk-steering]` | Compare search regimes; pin everything else. |

## Hardware

Total GPU-time for a sweep = `N_configs × per_run_GPU_time`. A single `search_binder_pipeline` run on one A100 is roughly 30–90 min (binder length + nsteps dependent). A 4-axis × 4-value sweep = 256 configs × ~60 min = ~256 GPU-hours.

Refer to `.claude/skills/_shared/reference/hardware.md` for the per-run baseline + VRAM minima, and to the `complexa-slurm` skill for partition and array-size limits.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Sweeper file not found` from `generate_inference_configs.py` | Path resolved from wrong CWD | Use a path relative to the repo root; or pass an absolute path. |
| `Sweeper YAML must be a mapping` | Top-level YAML is a list or scalar | Rewrite as `key: [v1, v2]` mapping. |
| `No configs were generated` (launcher dies) | One of the value lists is empty `[]` | Sweeper file has a `key: []` line — add at least one value. |
| `complexa design` rejects `--sweeper` | Confusion between CLI paths | The CLI does not accept `--sweeper`. Use SLURM launcher OR generate + loop (Path B). |
| One config in the array fails, sweep keeps going | SLURM array task isolation | Re-parse the manifest, skip failed `config_id` when ranking, surface failures to the user. |
| Override silently collapses a sweep axis | `--override key=v` shadowed a sweep key | Drop either the override OR the matching key from the sweeper file. |

---

For per-axis reference (typical ranges, cost, what gets better/worse), see [reference/sweep_axes.md](reference/sweep_axes.md).

For cluster submission, partition selection, and SLURM array monitoring, see the `complexa-slurm` skill — sweeps in Path A are submitted through that path.

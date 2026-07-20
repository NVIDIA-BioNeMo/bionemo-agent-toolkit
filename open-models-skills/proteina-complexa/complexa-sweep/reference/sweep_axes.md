# Sweep Axes Reference

Catalogue of swept keys for Proteina-Complexa design pipelines, grouped by pipeline stage. Every key is a Hydra dot-path you can put in a `configs/sweeps/*.yaml` file as a sweep axis (list value) or as an `--override KEY=VAL` pin.

Defaults are read from `configs/pipeline/binder/binder_generate.yaml`, `configs/pipeline/binder/binder_evaluate.yaml`, and `configs/pipeline/model_sampling.yaml`. Verify against your actual base pipeline config before launching — different pipelines (e.g. `search_ligand_binder_local_pipeline`, `search_ame_local_pipeline`) inherit different defaults.

## Generation axes

These live under `generation.*` in the pipeline config (because the base pipeline pulls `binder_generate@generation`).

### Search algorithm + width

| Key | Default | Typical sweep values | Cost multiplier | Effect |
|---|---|---|---|---|
| `generation.search.algorithm` | `best-of-n` | `single-pass`, `best-of-n`, `beam-search`, `fk-steering`, `mcts` | 1× → 8× | Search regime. `single-pass` = baseline. `best-of-n` linear in replicas. `beam-search`/`fk-steering` ~ `n_branch × beam_width` extra forward passes. |
| `generation.search.beam_search.beam_width` | 4 | 1, 2, 4, 8, 16 | linear | More beams = wider search → higher success rate. Diminishing returns past 8 in practice. |
| `generation.search.beam_search.n_branch` | 4 | 2, 4, 8 | linear | Branching factor per beam step. Together with `beam_width` controls total samples per checkpoint. |
| `generation.search.beam_search.keep_lookahead_samples` | `true` | `true`/`false` | minor | Whether to keep intermediate lookahead candidates as outputs. Off = fewer final PDBs. |
| `generation.search.best_of_n.replicas` | 10 | 1, 4, 16, 64 | linear | Best-of-N draws. Increasing tightens success-rate estimate; not search depth. |
| `generation.search.fk_steering.beam_width` | 4 | 1, 2, 4, 8 | linear | FK-steering equivalent of beam_width. |
| `generation.search.fk_steering.n_branch` | 4 | 2, 4, 8 | linear | FK-steering branching factor. |
| `generation.search.fk_steering.temperature` | 0.1 | 0.05, 0.1, 0.2, 0.5 | none | Softmax temperature for FK resampling. Higher = closer to uniform (more exploration). |
| `generation.search.mcts.n_simulations` | 20 | 10, 20, 50 | linear | MCTS rollouts per decision. |
| `generation.search.mcts.exploration_constant` | 1.0 | 0.5, 1.0, 2.0 | none | UCB exploration weight. |
| `generation.search.reward_threshold` | `null` | `null`, -0.2, -0.1 | filters | Drop search candidates below this reward at each step. `null` = keep all. |

### Diffusion / flow sampling

| Key | Default | Typical sweep values | Cost multiplier | Effect |
|---|---|---|---|---|
| `generation.args.nsteps` | 400 | 100, 200, 400, 800 | linear | ODE integration steps. Lower = faster, lossy past ~100. 400 is a strong default. |
| `generation.args.self_cond` | `true` | `true`, `false` | ~1.05× when true | Self-conditioning across steps; usually helps. |
| `generation.args.guidance_w` | 1.0 | 0.0, 0.5, 1.0, 2.0 | none | Classifier-free guidance scale; 0 = unconditional, 1 = nominal, >1 = sharper conditioning. |
| `generation.args.fold_cond` | `false` | `true`, `false` | minor | Fold-conditioning toggle. Off for most binder runs. |
| `generation.model.bb_ca.simulation_step_params.sc_scale_noise` | 0.1 | 0.05, 0.1, 0.2, 0.4, 0.8 | none | Backbone CA noise scale ("temperature"). Higher = more diverse, less ordered structures. The `bb_ca_temperature.yaml` canned sweep tests 0.1 vs 0.4. |
| `generation.model.bb_ca.simulation_step_params.sc_scale_score` | 1.0 | 0.5, 1.0, 1.5 | none | Score multiplier. Rarely swept. |
| `generation.model.bb_ca.simulation_step_params.t_lim_ode` | 0.98 | 0.9, 0.95, 0.98 | none | ODE cutoff time near t=1. |
| `generation.model.local_latents.simulation_step_params.sc_scale_noise` | 0.1 | 0.05, 0.1, 0.2 | none | Latent-feature noise. Affects sequence/local-structure diversity. |
| `generation.n_recycle` | 0 | 0, 1, 2 | linear in N+1 | Recycling iterations through the model. Costly. |

### Reward weights (`af2folding` composite)

Path prefix: `generation.reward_model.reward_models.af2folding.reward_weights.*`. These compose into a single scalar reward at each search step; tuning the ratio rebalances what search optimises for.

| Key (under the prefix above) | Default | Typical sweep | Effect |
|---|---|---|---|
| `i_pae` | -1.0 | -2.0, -1.0, -0.5, 0.0 | Negative weight on interface PAE. More negative = search pushes harder for low iPAE. |
| `plddt` | 0.0 | 0.0, 0.5, 1.0 | Positive weight on overall pLDDT. Turn on to bias toward confident monomers. |
| `con` | 0.0 | 0.0, 0.1, 0.5 | Binder-internal contact loss. Higher = more compact binders. |
| `dgram_cce` | 0.0 | 0.0, 0.1, 1.0 | AF2 distogram cross-entropy. Rarely swept above 0. |
| `min_ipae` | 0.0 | 0.0, -0.5, -1.0 | Min iPAE across chains; aggressive interface-quality push. |

`generation.reward_model.reward_models.bioinformatics.reward_weights.{interface_sc, interface_hydrophobicity, surface_hydrophobicity, ...}` exist for the bioinformatics reward block (shape complementarity, SASA, hydrophobicity). Defaults live in the `binder_generate.yaml` config. Same pattern: list of floats per axis.

### Refinement + filtering

| Key | Default | Typical sweep | Effect |
|---|---|---|---|
| `generation.refinement.algorithm` | `null` | `null`, `sequence_hallucination` | Enable post-generation refinement loop. ~2× wall-clock when on. |
| `generation.filter.reward_threshold` | `null` | `null`, -0.2, -0.1 | Hard floor on reward before top-N filtering. |
| `generation.filter.filter_samples_limit` | 1000 | 100, 500, 1000 | Max samples to keep. |
| `generation.filter.dedup_sequence` | `true` | `true`, `false` | Drop sequence-duplicate samples before ranking. |

## Evaluation axes

These live at top level (the binder_evaluate config is loaded with `@_global_`), not under `generation.*`.

| Key | Default | Typical sweep | Cost multiplier | Effect |
|---|---|---|---|---|
| `metric.binder_folding_method` | `colabdesign` | `colabdesign`, `rf3_latest`, `boltz2_default`, `esmfold` | varies | Which refolder validates the binder. AF2 (`colabdesign`) is the standard; ESMFold ~5× faster, less accurate. |
| `metric.num_redesign_seqs` | 2 | 1, 2, 4, 8, 16 | linear | Number of MPNN redesigns to refold per binder. Higher = more reliable designability signal. |
| `metric.sequence_types` | `[self]` | `[self]`, `[self, mpnn]`, `[self, mpnn_fixed]` | linear per type | Which sequences to evaluate: generated, MPNN-redesigned, or MPNN with fixed interface. |
| `metric.interface_cutoff` | 8.0 | 6.0, 8.0, 10.0 | none | Angstrom cutoff defining interface residues for MPNN_fixed and interface metrics. |
| `metric.inverse_folding_model` | `soluble_mpnn` | `protein_mpnn`, `ligand_mpnn`, `soluble_mpnn` | none | MPNN variant used for redesign. |
| `metric.compute_pre_refolding_metrics` | `false` | `true`, `false` | minor | Compute interface metrics on the generated structure (no fold) — fast. |
| `metric.compute_refolded_structure_metrics` | `false` | `true`, `false` | minor | Compute interface metrics on the refolded structure — slower. |
| `metric.pre_refolding.{bioinformatics,tmol,hbplus}` | mixed | `true`/`false` | minor | Toggle individual interface metric modules. |

## Reading the sweeper YAML format

Annotated example based on `configs/sweeps/example.yaml`:

```yaml
# --- Sweep axes (lists, cartesian-producted) ---
# Each key is a Hydra dot-path. Each list value becomes one dimension.
# Total configs = product of list lengths. Here 2 × 2 = 4.
generation.search.beam_search.beam_width:
  - 2
  - 4
generation.args.nsteps:
  - 200
  - 400

# --- Pinned scalar (no extra dimension) ---
# Scalars are auto-wrapped into a single-element list, so they pin a value
# across the whole sweep without growing the cartesian product.
# generation.args.self_cond: true

# --- Long block-style list (e.g. checkpoint paths) ---
# ckpt_path:
#   - /lustre/checkpoints/model_v1/epoch_100.ckpt
#   - /lustre/checkpoints/model_v2/epoch_200.ckpt
```

Validation rules (`script_utils/generate_inference_configs.py:load_sweeper_file`):

- Top-level YAML must be a mapping. List or scalar at top = error.
- All keys must be strings. Numeric keys = error.
- List values are kept verbatim. Scalar values are wrapped to `[value]`.
- Empty list `[]` for an axis = launcher dies with "No configs were generated."

## Generating sweeper YAMLs programmatically

For large parameter grids it is cleaner to render the YAML than to edit by hand:

```python
import itertools, yaml

axes = {
    "generation.search.beam_search.beam_width": [1, 2, 4, 8],
    "generation.args.nsteps": [200, 400, 800],
    "generation.model.bb_ca.simulation_step_params.sc_scale_noise": [0.1, 0.2, 0.4],
}
# 4 * 3 * 3 = 36 configs
total = 1
for v in axes.values():
    total *= len(v)
print(f"Will generate {total} configs")

with open("configs/sweeps/big_grid.yaml", "w") as f:
    yaml.safe_dump(axes, f, sort_keys=False, default_flow_style=False)
```

For an irregular set of `(key1, key2)` pairs (not a full cartesian product), there is no native support — emit one sweeper file per pair and concatenate the summary CSVs.

## Result-aggregation logic

`sweep_summary.csv` columns produced in Step 6 of the skill:

| Column | Source | Notes |
|---|---|---|
| `config_id` | The index in `inf_{idx}_{run_name}.yaml` | 0-based, sequential, set by `apply_sweeper_and_save_configs`. |
| `<axis_name>` (one per axis) | Read from the per-config `inf_*.yaml` at the swept Hydra path | Strip the dot-path to a short column header (e.g. `beam_width`). |
| `n_samples` | `len(results_csv)` | Rows in the analyze CSV for this config. |
| `success_rate` | `mean(passes_filter)` if column present, else thresholded `mean((i_pae < 10) & (i_plddt > 0.7) & (sc_rmsd < 2.0))` | Confirm thresholds with the user. |
| `mean_i_pae` | `i_pae.mean()` | Lower = better. AF2 interface PAE. |
| `mean_i_plddt` | `i_plddt.mean()` | Higher = better. Interface pLDDT. |
| `mean_sc_rmsd` | `sc_rmsd.mean()` | Self-consistency RMSD between generated and refolded structures. |
| `diversity_score` | Unique sequences / `n_samples`, or 1 − mean pairwise TM-score if available | Higher = more diverse pool. |
| `wall_clock_min` | Timestamp delta from the per-config log (`./logs/design_pipeline_*_<run>_<timestamp>.log`) | Approximate (process wall-clock, not GPU time). |

Ranking:

- **Best by success** = argmax `success_rate`; tie-break on `mean_i_pae` ascending.
- **Pareto frontier** on (`wall_clock_min`, `success_rate`): a config is on the frontier iff no other config has both lower wall-clock AND higher success rate. Implement with a sort + linear sweep.
- **Sanity check**: if every config has `success_rate == 0`, the threshold is too strict OR the sweep regime is broken — surface this to the user before reporting "best".

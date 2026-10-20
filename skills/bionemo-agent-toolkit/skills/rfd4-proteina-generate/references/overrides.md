# Overrides cheat sheet

Every generation parameter you are likely to touch, mirroring
`docs/how-to/run-the-model.md`. **All arguments are Hydra `key=value`, never
`--key value`.** Run from the repo root. Back to the [skill](../SKILL.md).

Entry point:

```bash
rfd4-generate inputs=<file> num_replicates=<N> out_dir=<dir> [overrides...]
```

Activate the environment where you installed RFD4-Proteina before running these
commands. `rfd4-generate` uses that environment's Python.

## Essential (defaults rarely right for a real run)

| Parameter | Description | Default |
| --- | --- | --- |
| `out_dir` | Output directory. Set a real path for anything but a smoke test. | `./runs/<run_name>` |
| `num_replicates` | Designs generated per input example. `1` is a smoke test only. | 1 |
| `batch_size` | Designs processed in parallel on GPU. Start at 8; confirm the longest input fits at 1 first. | 1 |
| `metrics_tags` | Inline metrics as a bracket-quoted Hydra list. Only `*_refolding` tags need an AF3 container. Empty = none. | `[]` |

```bash
rfd4-generate \
    inputs=data/benchmarks/monomer \
    num_replicates=80 batch_size=8 out_dir=./runs/monomers
```

## Inputs & checkpoints

| Parameter | Description | Default |
| --- | --- | --- |
| `inputs` | Input file (annotated CIF / JSON / YAML / CIF / PDB) or a directory of them. Annotated CIF is preferred — build via **rfd4-proteina-annotated-cif**. | Required |
| `subset_to_examples` | Run only specific example keys (comma-separated), e.g. `subset_to_examples=monomer-short` | null |
| `skip_existing` | Skip examples whose output already exists (resume a run) | true |
| `seed` | Random seed (`null` = different each run) | null |
| `save_chain_of_interest` | Write per-design chain-of-interest CIFs — required for later foldseek clustering | false |
| `ckpt_path` / `ckpt_name` | Override the checkpoint dir / filename for a one-off. Read from `$DATA_PATH` otherwise. | from `$DATA_PATH` |

> **Checkpoints.** `configs/inference.yaml` composes the current release pair, which is exactly
> what `scripts/download_assets.sh` downloads — so no override is needed. Native
> checkpoints go into `DATA_PATH`; a configured HF bundle uses `HF_HOME`. Point at a different
> checkpoint with `ckpt_path=<dir> ckpt_name=<file.ckpt>`.
>
> See **rfd4-proteina-setup** for full checkpoint detail.

## Sampling

| Parameter | Description | Default |
| --- | --- | --- |
| `inference_experiment` | Config group controlling generation (nsteps, noise, search, metrics) | `inference_on_user_inputs` |
| `generation.args.nsteps` | Number of model evaluations; the default time grid puts twice the step density in the final 20% | 60 |
| `recycle_strategy` | Recycle-depth preset; `thinking_low` for 0.5x or `thinking_high` for 1.5x depths | `thinking_medium` |
| `generation.args.save_trajectory_every` | Save a trajectory snapshot every N steps (0 = off) | 0 |

**Deterministic (ODE) sampling** — no noise injected mid-trajectory:

```bash
rfd4-generate inputs=data/benchmarks/monomer out_dir=./runs/ode \
    generation.model.bb_ca.gt.mode=ode generation.model.local_latents.gt.mode=ode
```

The default `vf_tsr` (velocity field with temporal score rescaling) sampler is
stochastic because `sc_scale_noise`/`gt` defaults are nonzero; `tsr_k` /
`tsr_sigma` (pre-tuned in `inference_base`) control the end-of-trajectory
temperature drop.

## Temperature and diversity

Use `tsr_k` as the main temperature parameter for each flow. Higher `k` means lower
temperature and stronger score sharpening; lower `k` raises temperature.
`tsr_sigma` provides secondary control over the schedule: larger values apply sharpening earlier.

| Parameter | Controls | Default |
| --- | --- | --- |
| `generation.model.bb_ca.simulation_step_params.tsr_k` | Backbone temperature | 16 |
| `generation.model.local_latents.simulation_step_params.tsr_k` | Sidechain / sequence temperature | 4 |
| `generation.model.bb_ca.simulation_step_params.tsr_sigma` | Backbone sharpening schedule | 3 |
| `generation.model.local_latents.simulation_step_params.tsr_sigma` | Latent sharpening schedule | 12 |

`sc_scale_noise` remains configurable and defaults to 1.0 for both modalities.

```bash
rfd4-generate \
    inputs=data/benchmarks/monomer out_dir=./runs/higher_temperature \
    generation.model.bb_ca.simulation_step_params.tsr_k=8 \
    generation.model.local_latents.simulation_step_params.tsr_k=2
```

## Partial diffusion (refine an existing structure)

Start denoising from a noisy (but non-random) copy of an existing structure
passed with `inputs=`. Two mutually exclusive interfaces:

| Parameter | Description | Default |
| --- | --- | --- |
| `generation.args.partial_trajectory_fraction_steps` | Simple: run this fraction of `nsteps` (e.g. 0.3 = 30%) | null |
| `generation.args.partial_t_backbone` / `partial_t_latent` | Advanced: per-modality starting corruption level, float in (0, 1) | null |
| `generation.args.couple_partial_t` | Derive one modality's `partial_t` from the other via the schedule | false |

`partial_t` is a **corruption level, not Angstroms**: near `1` runs very little
of the trajectory (output stays close to the input), near `0` runs most of it
(closer to full generation). `nsteps` is independent of the level.

```bash
rfd4-generate \
    inputs=my_structure.cif \
    generation.args.partial_t_backbone=0.8 generation.args.partial_t_latent=0.8 \
    num_replicates=8 out_dir=./runs/partial
```

## Inline metrics tags

Pass as a bracket-quoted Hydra list; results go to `per_example_metrics.csv`.

| Tag | Activates |
| --- | --- |
| `unconditional_refolding` | AF3 refolding + pLDDT/scRMSD for unconditional generation |
| `ppi_refolding` | AF3 refolding + target templating + interface metrics for protein binder design |
| `motif_scaffold_refolding` | AF3 refolding + motif RMSD for motif scaffolding / enzyme design |
| `sm_binder_refolding` | AF3 refolding + binding metrics for small molecule binder design |
| `ame_refolding` | AF3 refolding for enzyme (MCSA) active-site benchmarks |
| `hotspot_conditioning` | Hotspot obedience metrics (requires hotspot input) |
| `3d_coordinate_conditioning` | Motif coordinate RMSD metrics |
| `rasa_conditioning` | RASA adherence metrics |
| `interchain_interactions` | Interchain interaction (H-bond / pi-stack / pi-cation / salt-bridge / hydrophobic / metal-coordination) adherence and counts |

All `*_refolding` tags run the AF3 oracle (needs an apptainer/docker container).
Metrics that require a tag are silently skipped if the tag is absent. Deep detail
lives in **rfd4-proteina-evaluate** and `docs/how-to/evaluate-with-metrics.md`.

## Reusable configs and search

- `configs/inference_experiment/TEMPLATE.yaml` documents the three ways to run
  (in-tree config group, CLI overrides, external config file).
- Reward-guided / beam search: `configs/inference_experiment/inference_beam_example.yaml`
  — driven by **rfd4-proteina-search**.

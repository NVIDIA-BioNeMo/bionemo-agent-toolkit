---
name: rfd4-proteina-search
description: Use when running RFD4-Proteina reward-guided beam search with chosen checkpoints, branching, metrics, and compute limits.
license: CC-BY-4.0
allowed-tools: Bash, Read, Write
metadata:
  author: Ohad Mosafi <omosafi@nvidia.com>
  tags: [protein-design, rfd4, search]
---

# RFD4-Proteína Reward-Guided Search

## Purpose

## Reward requirements

Complete `rfd4-proteina-setup` first. Generation requires a CUDA GPU. Rewards
listing refolding oracles also require a configured refolding backend; RFD4-Proteína
supports AF2, AF3, and OpenFold3 through `metrics/refolding_oracles`. Rewards such
as `interchain_interactions` do not require a refolding oracle.

Search explores multiple generation trajectories and keeps the candidates a
**reward** scores highest. **Beam search** ships ready to run: it branches and
prunes partial trajectories at step checkpoints, scoring survivors with a reward
model. The shipped `inference_beam_example` uses the default **AF3 oracle** for
refolding confidence; other search configs may select another backend or avoid
refolding entirely.

Search runs through the **same entry point as generation** — `generate.py` —
selected by an `inference_experiment` config that adds one `search:` block. All
arguments are Hydra `key=value` (never `--key value`).

Run everything from the repository root (the directory containing `.project-root`).

## Prerequisites

A working generation runtime, validated design inputs, and the dependencies of each selected reward provider.

Use the user-selected model checkout at `RFPROTEINA_ROOT` for model commands,
configs, and upstream manuals. This catalog contains the skills, not that checkout.
In helper examples, resolve `open-models-skills/rfd4-proteina/<name>/...` to its absolute installed path
when the catalog and model checkout are separate.

## Inputs

Required: the user's inputs, output directory, reward objective, and compute budget. Optional: checkpoint, beam, branch, and reward-weight overrides. Read other defaults from the chosen config and preserve selected scheduler resources.

## Instructions

### Step 1 — Preflight the selected reward dependencies

Every search needs a green rfd4-proteina-setup:

```bash
bash open-models-skills/rfd4-proteina/rfd4-proteina-setup/scripts/preflight.sh
```

If the reward uses refolding, inspect the selected backend before running. AF3 is
the default; choose AF2 or OpenFold3 with
`metrics/refolding_oracles=af2` or `metrics/refolding_oracles=of3`. Backend
capabilities differ by design case, so confirm that the selected config contains
the oracle provider explicitly listed by each refolding checkpoint. See
[references/rewards.md](references/rewards.md), the AF2/AF3 references, and
rfd4-proteina-setup and the [RFD4-Proteína installation guide](https://github.com/RosettaCommons/RFD4-Proteina/blob/main/docs/installation.rst).
Use `rfd4-generate` from the Python environment activated during setup.
Refolding oracles use their separately configured runtimes. IPD users retain
their existing container launchers.

If a refolding reward fails, verify the selected backend, the checkpoint metric names, and its
runtime before changing the reward.

## Step 2 — Run the ready example

Two search configs ship ready to run:

```bash
# Beam search, AF3 refolding pLDDT as reward (configs/inference_experiment/inference_beam_example.yaml)
rfd4-generate inference_experiment=inference_beam_example

# Beam search, NO refolding — interface protein<->ligand H-bonds as reward
# (configs/inference_experiment/sm_binder_hbond_search.yaml)
rfd4-generate inference_experiment=sm_binder_hbond_search
```

The first uses the AF3 oracle (needs the container); the second scores with
interface H-bond counts and never refolds, so it needs no oracle.

## Step 3 — Build your own search config

Copy a shipped config and edit its flat `search` block. Each entry under
`search.checkpoints` specifies its own metrics, reward terms, and scoring source.
Metric definitions stay under the normal `metrics` configuration.

```yaml
search:
  n_branch: 2
  beam_width: 3
  checkpoints:
    "40":
      metrics: [interchain_interactions]
      use_clean_prediction: true
      rewards:
        interchain_interactions.hbond_atom_pair_count_coi:
          weight: 1.0
          clip: {max: 6.0}
          normalize_by: 6.0
    "60":
      metrics: [oracle]
      rewards:
        oracle.plddt_coi: {weight: 1.0}
generation:
  args:
    nsteps: 60
```

### Select metrics and reward terms

- `metrics` lists provider names from `metrics.inline_metrics`,
  `metrics.refolding_oracles`, or `metrics.refolding_metrics`. For a refold
  comparison, list both the oracle and comparison, e.g.
  `[oracle, refolded_backbone_rmsd]`. Search does not infer dependencies.
- `rewards` maps `metric.output` keys to `{weight, clip, normalize_by}` terms.
  Each term is clipped, divided by a positive `normalize_by`, then multiplied
  by `weight`. Weight and normalization default to 1; clipping is optional.
  Negative weights minimize. Pass/fail metrics are not supported as search rewards.
- Checkpoints are self-contained: omitted `metrics`, `rewards`, and
  `use_clean_prediction` mean `[]`, `{}`, and `false`. Nothing is inherited
  from another checkpoint. An empty reward ranks by deterministic input order.
- Top-level `metrics_tags` controls ordinary output evaluation. Explicit search
  selection bypasses dataset-selection tags but preserves oracle/refold routing.

Full provider and reward examples: [references/rewards.md](references/rewards.md).

### Choose checkpoints and scoring sources

Configure at least one checkpoint. Keys are positive integer integration steps, executed in sorted order.
Quote YAML keys to support dotted Hydra overrides, e.g.
`++search.checkpoints.40.use_clean_prediction=true`. Step zero is implicit;
keys cannot exceed the actual schedule length, including partial diffusion.

`use_clean_prediction: true` decodes and scores the preceding integration step's
clean prediction using design metrics only. It skips scoring rollouts and oracles,
and does not save the prediction. With the default `false`, a separate rollout
completes the candidate for scoring. Both modes continue selected trajectories
from their actual intermediate states.

The schedule-end checkpoint (normally `60`) is optional. If present, it must
score completed structures, and branches and selects using its own reward.
If omitted, every survivor of the last configured checkpoint finishes once,
without additional branching or selection, then runs ordinary final metrics.
These final designs have no final `search.reward`.

`n_branch` is the number of candidates spawned per surviving beam at each
configured checkpoint; `beam_width` is the number retained per input. Both
are positive integers and default to 4. A checkpoint's `n_branch` overrides the
global count for its incoming interval; omitted counts use the global default.

### Stop unpromising inputs

A checkpoint before the schedule end can specify `continuation_criteria`, for
example `search.reward: {min: 4}`. If any reward-selected candidate passes, keep
the entire selected beam. Stop the input only if all selected candidates fail;
passing candidates that lost selection do not count.
List all raw-metric providers explicitly in that checkpoint's `metrics`.
Stopped inputs keep saved rollouts; passing inputs continue normally, including
when the final checkpoint is omitted. See `docs/workflow/search.md` for reductions
and missing-value behavior.

For novelty, explicitly select `FoldseekNoveltyMetric` and threshold
`novelty.is_novel: {min: 1}` in continuation criteria. An `archive_dir` on the
existing final pass criterion publishes passing designed chains; use one shared
directory per target and pass definition. Publication happens after generation,
so these passers help later runs or concurrent jobs. Novelty uses exhaustive Foldseek
search against a cached database, rebuilt when the archive changes. Matches require
TM-score and coverage thresholds on both chains; see `docs/workflow/search.md`.

### Save completed scoring rollouts

The final beam is always returned. Set `save_rollouts: true` to additionally
return completed scoring rollouts. Optional `save_criteria` thresholds filter
those extra outputs using raw metrics or `search.reward`:

```yaml
search:
  beam_width: 3
  n_branch: 2
  save_rollouts: true
  save_criteria:
    search.reward: {min: 80.0}
  checkpoints:
    "60":
      metrics: [oracle]
      rewards:
        oracle.plddt_coi: {weight: 1.0}
```

Every rollout checkpoint must explicitly list the providers required by its
save criteria. Clean predictions are never saved as completed designs.
Rewards at different checkpoints can have different scales; compare final-design
metrics when assessing reward schedules. `sm_binder_hbond_search.yaml` shows
checkpoint-specific reward terms.

## Step 4 — Cost and runtime

Search is **much more expensive** than plain generation. Cost scales roughly as:

```
search oracle calls  ~  beam_width  x  n_branch  x  (oracle-scored checkpoints)
```

This estimate assumes one refold per scored candidate; final evaluation may add
refolds if no cached result exists. Raise `beam_width`/`n_branch` only as compute allows; add checkpoints only when
finer pruning pays off. For a cheap, unguided baseline use **rfd4-proteina-generate**
(one trajectory per design, no oracle). Full guidance and worked numbers:
[references/cost.md](references/cost.md).

## Step 5 — Submit on SLURM

Search is an inference configuration, so the standard generation launcher is the
preferred batch path:

```bash
./scripts/launch_generate.sh \
    inference_experiment=inference_beam_example
```

Before submission, read `scripts/.user_info_<cluster>` and the launcher. Preserve
the user's partition, account, QoS/priority options, GPU request, runtime, memory,
and CPU settings. Add a launcher resource override only when the user explicitly
requested it. State the resolved scheduler values and inspect the generated
`#SBATCH` directives when available.

Search uses the standard `launch_generate.sh` path so scheduler settings and
`SLURM_EXTRA_OPTIONS` follow the same profile contract as ordinary generation.
Never submit a job as part of skill validation.
## Outputs

Search writes the **final beam** as annotated `.cif` files, plus completed scoring
rollouts retained by `save_rollouts` and `save_criteria`. Output metrics land in
`per_example_metrics.csv`; final evaluation reuses any cached oracle results.
If the schedule-end checkpoint is omitted, final designs receive ordinary metrics
without a final search reward. CIF annotations follow the same schema as plain
generation (see `docs/workflow/running.md` Output Files).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Refolding errors or oracle not found | Check that the selected backend defines the checkpoint's named oracle and supports the design case, then verify its runtime. |
| Checkpoint exceeds schedule length | Use positive step keys no greater than the actual schedule length; omit the end checkpoint to finish survivors without selection. |
| Reward not changing / plateaus early | Check the term's `clip` bounds and `normalize_by`, then adjust them or its `weight`. |
| Missing reward or save-criterion output | Explicitly list every required provider in that checkpoint's `metrics`; a refold comparison also needs its oracle. |
| Run slower than expected | Reduce `beam_width`, `n_branch`, or oracle-scored checkpoints. See [references/cost.md](references/cost.md). |
| Only final designs returned | Set `save_rollouts: true` and optionally `save_criteria`; clean-prediction checkpoints never save completed scoring rollouts. |
| Hydra override fails | Use `key=value`. Quote checkpoint keys in YAML; delete unwanted inherited checkpoints with e.g. `'~search.checkpoints.60'`. |

For deeper detail: [rewards](references/rewards.md) ·
[AF2 oracle](references/af2-oracle.md) · [AF3 oracle](references/af3-oracle.md) ·
[cost](references/cost.md). Source of
truth: `docs/workflow/search.md`, `docs/workflow/running.md`, and the current
search implementation/configs.

## Limitations

Rewards are computational proxies and costs grow with branching and oracle calls. Search results must be compared using common final metrics and independently validated as required by the task.

## Examples

Step 2 includes both an AF3 reward example and a structure-only H-bond reward example. Select the provider and reward that match the requested objective.

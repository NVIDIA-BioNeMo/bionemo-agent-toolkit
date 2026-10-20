# Reward reference

Each `search.checkpoints.<step>` entry explicitly selects metric providers and
aggregates their outputs into a scalar reward. Definitions stay under `metrics`;
there is no separate reward file. See `docs/workflow/search.md`.

## Select metric providers

`metrics` is a list of names defined under `metrics.inline_metrics`,
`metrics.refolding_oracles`, or `metrics.refolding_metrics`. For example:

| Checkpoint metric list | Scoring work |
| --- | --- |
| `[interchain_interactions]` | Interchain H-bond and hydrophobic-contact counts; no oracle |
| `[oracle]` | Refolding and confidence outputs from the configured `oracle` |
| `[oracle_ppi]` | Confidence outputs from the configured protein-binder oracle |
| `[oracle, refolded_backbone_rmsd]` | Refolding plus comparison against the design |
| `[oracle_ppi, oracle_apo, refolded_apo_holo_rmsd]` | Holo and apo refolds plus their comparison |

Search does not infer dependencies: name every oracle and comparison explicitly.
Pass/fail metrics are not supported as search rewards. Selecting a metric computes
all its outputs; `rewards` chooses which outputs contribute to ranking.

AF3 is the default backend. AF2 and OpenFold3 can be selected with
`metrics/refolding_oracles=af2` and `metrics/refolding_oracles=of3`. Inspect the
selected configuration for provider names and supported design cases; providers
and capabilities differ by backend. The reward-key prefix is the provider's
configuration name, e.g. `oracle_ppi.iptm_coi`.

Explicit selection bypasses dataset-selection tags but retains routing constraints
such as `is_refold:untransformed`, `exists_refold:untransformed`, and `oracle:af3`.
Top-level `metrics_tags` still controls ordinary final evaluation independently.
A search with design metrics only needs no refolding runtime unless its final
evaluation requests refolding.

## Reward terms

`rewards` maps `metric.output` to a mapping with these optional fields:

| Field | Default | Effect |
| --- | --- | --- |
| `weight` | `1` | Multiply the term; use negative values to minimize and zero to disable |
| `clip` | No clipping | Bound the raw value with `min` and/or `max` |
| `normalize_by` | `1` | Divide the clipped value by this positive finite number |

The reward is the sum of `weight * clipped_value / normalize_by`. Raw metric
values remain unchanged. Each nonzero reward term requires its provider in the
checkpoint's `metrics`. A weighted output missing at scoring gives that candidate
`-inf`; if every candidate at a checkpoint scores `-inf`, search raises unless
continuation criteria stop every input at that checkpoint.

Common outputs (`coi` means chain of interest):

| Key | Meaning | Preferred direction |
| --- | --- | --- |
| `oracle.plddt_coi` | Refolding pLDDT of the chain of interest (0–100) | Maximize |
| `oracle.iptm_coi` | Interface pTM for the chain of interest | Maximize |
| `oracle.ipae_coi` | Mean interface PAE | Minimize |
| `oracle.min_ipae_coi` | Minimum interface PAE | Minimize |
| `interchain_interactions.hbond_atom_pair_count_coi` | Interface H-bond atom-pair count | Maximize |

Check the provider's output units before choosing normalization. A clip flattens
reward outside its bounds: `clip: {min: 50}` treats pLDDT below 50 equally, while
`clip: {max: 80}` stops rewarding improvement above 80.

## Checkpoint-specific objectives

Every checkpoint is self-contained. Omitted `metrics`, `rewards`, and
`use_clean_prediction` mean `[]`, `{}`, and `false`; nothing carries forward
from another checkpoint. An empty reward gives all candidates zero and selects
by deterministic input order.

```yaml
search:
  beam_width: 3
  n_branch: 2
  checkpoints:
    "20":
      metrics: [interchain_interactions]
      use_clean_prediction: true
      rewards:
        interchain_interactions.hbond_atom_pair_count_coi: {weight: 1.0}
    "50":
      metrics: [interchain_interactions]
      rewards:
        interchain_interactions.hbond_atom_pair_count_coi:
          weight: 1.0
          clip: {max: 6.0}
          normalize_by: 6.0
        interchain_interactions.hydrophobic_atom_pair_count_coi: {weight: 0.5}
    "60":
      metrics: [oracle]
      rewards:
        oracle.plddt_coi: {weight: 1.0}
```

Keys are positive steps, sorted for execution; zero is implicit. Quote YAML step
keys so dotted Hydra overrides address them correctly. No step may exceed the
actual schedule length, including partial diffusion.

Clean-prediction scoring (`use_clean_prediction: true`) decodes the preceding
integration step's prediction and runs only design metrics. It does not roll out,
refold, or save that prediction. Default scoring completes a separate rollout.
Selected candidates always continue from their intermediate trajectory states.
A checkpoint at the schedule end must use completed-structure scoring.

Omit the schedule-end checkpoint to finish each retained beam once without
extra branching, scoring, or selection. Ordinary final metrics still run, but
those final designs have no final `search.reward`. For the example above,
`'~search.checkpoints.60'` makes step 50 the last selection.

## Retain completed scoring rollouts

Set `search.save_rollouts: true` to keep completed scoring rollouts in addition
to the final beam. Optional `search.save_criteria` maps raw output keys or
`search.reward` to threshold mappings such as `{min: 80}`. List all providers
needed by the criteria at every rollout checkpoint; search never adds them.
Clean-prediction checkpoints do not produce completed scoring rollouts to save.

Reward scales can differ by checkpoint. A shared save threshold on `search.reward`
must make sense for each objective; raw metric thresholds can be easier to compare.

## Worked monomer example

Maximize refolding pLDDT at steps 40 and 60, treating sub-50 values equally:

```yaml
# @package _global_
defaults:
  - inference_on_user_inputs
  - _self_

inputs: ${oc.env:PROJECT_ROOT}/data/benchmarks/monomer
subset_to_examples: monomer-short
num_replicates: 2
out_dir: outputs/my_search
run_name_: my_search
metrics_tags: [design, unconditional_refolding]

search:
  n_branch: 2
  beam_width: 3
  checkpoints:
    "40": &confidence_checkpoint
      metrics: [oracle]
      rewards:
        oracle.plddt_coi: {weight: 1.0, clip: {min: 50.0}, normalize_by: 100.0}
    "60": *confidence_checkpoint
generation:
  args:
    nsteps: 60
```

The YAML anchor explicitly repeats a configuration; it does not create inheritance
between checkpoints. Stage different objectives when different properties become
useful for ranking, and measure the effect using common final metrics and pass
rates. Put oracle scoring where it changes which candidates survive.

See [af2-oracle.md](af2-oracle.md), [af3-oracle.md](af3-oracle.md), and
[cost.md](cost.md) for backend requirements and compute budgeting.

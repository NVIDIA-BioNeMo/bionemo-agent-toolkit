# Tasks and design controls

## Contents

- [Task selection](#task-selection)
- [Sampling and reproducibility](#sampling-and-reproducibility)
- [Partial diffusion](#partial-diffusion)
- [Search](#search)
- [Metrics and deployment limits](#metrics-and-deployment-limits)

## Task selection

Task names select the sampler and validation rules. Conditions specify the
biological problem. These seven names are not an exhaustive list of capabilities.

| Task | Use |
| --- | --- |
| `generation` | New regions from noise, with any supplied conditions; includes protein/DNA target binders and peptide–MHC binders |
| `motif_scaffolding` | Scaffold indexed motif segments |
| `enzyme_design` | Scaffold unindexed catalytic/tip-atom motifs; retain required ligand context |
| `small_molecule_binder` | Design around a ligand carried in the input |
| `antibody_design` | Hold framework/antigen; leave selected CDR regions designable; also used for VHH examples |
| `partial_diffusion` | Refine a supplied complete design/backbone from partway along the trajectory |
| `inverse_folding` | Hold an existing backbone and generate sequence |

The older name `unconditional` is accepted as a legacy alias by the inspected
source and normalized to `generation` with a warning. It does not mean that
target conditioning is ignored. New requests should use `generation` on
compatible deployments. Do not add `binder`, `nanobody`, or `tcr` task names.

Use `C_CRD`, `C_SEQ`, and `C_HOT` to hold a target and mark an interface. Ig
conditions `C_CDR`, `C_ABH`, `C_ABL`, `cdr`, `ab-heavy`, and `ab-light` are
rejected because the pinned feature pipeline does not consume them. Cyclic
conditioning is disabled on the inspected default pin; a linear output with
copied cyclic annotations would not demonstrate ring closure. `C_SEC` is
accepted by the inspected source for secondary structure. However, sample 25
returned HTTP 422 on staging during authoring, with no field-level error
exposed by the gateway. Source acceptance is not deployed success; resolve
that discrepancy before recommending this sample for a live campaign.

## Sampling and reproducibility

| `sampling` field | Inspected contract |
| --- | --- |
| `num_replicates` | Integer >=1; default 1; current source has no fixed count cap |
| `batch_size` | Optional integer >=1 and <=replicate count; omitted means all replicates in one batch |
| `seed` | Optional integer 0 through `2**63-1`; omitted selects a new base seed |
| `num_steps` | Optional integer 1–1000 in the schema; deployment and checkpoint can impose tighter bounds |
| `recycle_strategy` | `thinking_low`, `thinking_medium`, `thinking_high` |
| `recycle_schedule` | Custom `[[step_count, depth], ...]`; mutually exclusive with named strategy |

| Named strategy | Steps | Trunk passes |
| --- | ---: | ---: |
| `thinking_low` | 60 | 110 |
| `thinking_medium` | 60 | 185 |
| `thinking_high` | 60 | 295 |

Omitting all schedule fields inherits the checkpoint preset; on the validated
staging deployment that is `thinking_medium`. Explicit `num_steps` alone
requests flat sampling. On the inspected source, `num_steps` alongside a
named strategy rescales its band widths and emits a warning; earlier source
rejected this combination when counts differed. Custom bands must sum to
`num_steps` if supplied, allow depths 0–32 and at most 64 bands, and receive
a warning because their quality is unvalidated. Depth 0 still costs one pass.

Use named schedules without a conflicting explicit step count for normal
requests. Unknown/retired strategy names can fall back with warnings on newer
servers; acceptance does not mean that the requested schedule ran. Legacy
`midpeak6_50` bands had a documented poly-alanine failure and should not be
introduced as a speed optimization. This does not imply every 50-step schedule
has identical behavior. Always report the returned schedule, not an assumption.

With `batch_size=1`, replicate i uses `(seed+i) % 2**63`. A larger batch draws
from one RNG stream: designs remain distinct but share a batch seed. Replay
the whole request with the same batch size, including a smaller final batch.
Retain input, weights, backend, software versions, and seeds; bitwise GPU
determinism across runtimes is not guaranteed. Do not assume seeds identify
single designs produced in a batch or under search.

## Partial diffusion

`partial` is required only for `task="partial_diffusion"` and refused for
other tasks. Use one of:

- `{"trajectory_fraction_steps": 0.4}`: run 40% of the trajectory; valid range
  `(0,1]`. Do not also send modality start times or `couple_partial_t`.
- `{"t_backbone": 0.6, "t_latent": 0.7}`: explicit times, each strictly `(0,1)`.
- One of those times with `"couple_partial_t": true`: derive the missing time.

The tested BioIR response for fraction 0.4 reported 60 steps, 185 trunk passes,
and null start times, despite `kind=partial`. This matches a response-builder
limitation in the inspected source, not proof that the partial input was
ignored. Do not use those reported values to estimate partial-run savings.

Use a complete, finite starting backbone. Samples 09/10 use the upstream
complete 2KL8 fixture; a motif-only input is not a substitute. Inverse folding
holds backbone geometry and cannot repair defects already present in it.

## Search

`search` is beam search over intermediate trajectories; requesting ordinary
replicates does not enable it. Example 06 contains:

```json
{
  "step_checkpoints": [0, 30, 60],
  "n_branch": 2,
  "beam_width": 2,
  "reward_metrics_tags": ["interchain_interactions"],
  "weights": {"interchain_interactions.hbond_atom_pair_count_coi": 1.0},
  "clip_values": {"interchain_interactions.hbond_atom_pair_count_coi": {"max": 6.0}}
}
```

Checkpoints start at 0, strictly increase, and end at the number of executed
steps. Pin the schedule. The schema allows 2–21 checkpoints and 1–16 branches
and beam width. Search requires `batch_size=1`; set it explicitly when
`num_replicates>1` because the batching default is otherwise incompatible.

For partial diffusion with a fraction, the final checkpoint is
`round(resolved_num_steps * trajectory_fraction_steps)` (24 for 60 × 0.4).
Search with explicit modality start times is refused because the scaled step
count depends on the model's schedule. Inverse folding does not support search.

Weights name actual `metric.output_key` entries, not metric tags. Negative
weights penalize. `reward_metrics_tags` enables the metrics used while scoring;
it is independent of `metrics.tags`, which controls final reporting. A missing
or null reward metric can make candidates unscorable; do not substitute zero.
Clip bounds apply before weighting, without changing reported metric values.

`checkpoint_overrides` can replace weights, clips, and reward tags at a listed
checkpoint after zero. `intermediate_save_min_reward` also retains qualifying
scoring rollouts; `scoring_chunk_size` bounds decode/scoring memory. Preserve
the returned `origin` so retained rollouts are not confused with final winners.

The deployment budgets approximately
`beam_width * n_branch * (len(step_checkpoints)-1) * num_replicates` rollouts.
Use the response's rollout report for actual work. Search designs share their
replicate seed; replay the full search. `diagnostics.search_rollout_seed` is
provenance and is not an independently settable replay handle.

## Metrics and deployment limits

Begin with the sample's tags or `metrics.tags=["design"]` for basic geometry.
An omitted/empty tag list returns diagnostics without requested metric families.
Use `hotspot_conditioning`, `interchain_interactions`, `cms`,
`3d_coordinate_conditioning`, `unindexed`, `rasa_conditioning`, or
`centroid_conditioning` only when relevant to the input. Inspect `/v1/tasks`
and actual results for availability. `small_molecule_only` describes pure
ligand generation upstream and can suppress protein geometry metrics; it is
not the usual choice for protein design around a small molecule.

Default deployments have no refolding oracle; `*_refolding`, `antibody`, and
other oracle tags require an operator-enabled plugin. `developability` is
unavailable in the inspected stock runtime. `ligand_interface` was removed;
do not copy it from older samples. Availability and scientific usefulness are
different questions, so report null/empty results and warnings honestly.

The inspected defaults are 1024 tokens, 200 integration steps, 600 trunk
passes, a 32 MiB request, and 256 search rollouts. These are deployment values,
not universal model limits. Read `runtime.limits` from the actual response.
GPU memory also depends on token count and batch size; an uncapped replicate
field does not mean an unlimited batch will fit.

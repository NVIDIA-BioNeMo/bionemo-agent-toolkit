# Composite reward engineering

The reward is what turns a vague goal into something an autoresearch loop can
optimize. In RFD4-Proteína it is defined under `search.checkpoints.<step>.rewards` (mechanics in
the **rfd4-proteina-search** skill and `docs/workflow/search.md`); this reference is
about *how to shape it* for a campaign.

## RFD4-Proteína reward keys

Reward keys come from providers explicitly listed in a checkpoint's `metrics`.
The configured provider name prefixes its outputs (e.g. `oracle` or
`oracle_ppi`); commonly used keys include:

| Key | Meaning | Typical direction |
| --- | --- | --- |
| `oracle.plddt_coi` | Refold pLDDT of the chain-of-interest | maximize |
| `oracle.iptm_coi` | Interface pTM | maximize |
| `oracle.ipae_coi` | Interface pAE | minimize (negative weight) |
| `oracle.min_ipae_coi` | Min interface pAE | minimize (negative weight) |

Use raw metric outputs, not pass/fail criteria. A comparison requires both its
metric and oracle to be listed; dependencies are never inferred. Top-level
`metrics_tags` independently controls final evaluation.

## The shape of a reward block

For a protein binder using the configured `oracle_ppi` provider:

```yaml
search:
  checkpoints:
    "60":
      metrics: [oracle_ppi]
      rewards:
        oracle_ppi.plddt_coi:
          weight: 1.0
          clip: {min: 50.0}
          normalize_by: 100.0
        oracle_ppi.ipae_coi: {weight: -0.5}
```

Terms are clipped, divided by `normalize_by`, then multiplied by `weight` and
summed. Omitted weight and normalization are 1; clipping is optional.

## Four rules that keep a composite reward honest

Adapted from the muni technical note (the reasoning transfers directly; the exact
term names there are Complexa's — translate to the RFD4-Proteína keys above):

1. **Normalize term scales before weighting.** Check the actual provider units;
   pLDDT is 0–100, interface-area terms can be hundreds-thousands (Å²), H-bond counts are small
   integers. If you sum raw values, the largest-magnitude term dominates for purely
   numerical reasons. Set a positive `normalize_by` for each term to bring
   values onto comparable scales before weighting.
2. **Gate instead of paying forever.** For "must clear a bar" quantities (a minimum
   interface size, a confidence floor), use the term's `clip` so the term stops
   contributing once satisfied — the agent has to clear the bar but is not rewarded
   for runaway values. (muni gated `interface_dSASA >= 1000 Å²` rather than
   rewarding area continuously.)
3. **Down-weight wide-range terms.** A term reported on 0-100 will swamp a 0-1 term
   at equal weight; scale its coefficient down accordingly. (muni down-weighted a
   0-100 hydrophobicity term to 0.025.)
4. **Use negative weights to minimize.** Error-like metrics (`*_ipae_*`) should
   carry negative coefficients.

## Scheduling the reward across the trajectory

Each checkpoint defines its complete `metrics`, `rewards`, and
`use_clean_prediction` settings. Nothing is inherited from another checkpoint.
This example uses clean-prediction design scoring early and a completed rollout
with oracle scoring at the end:

```yaml
search:
  checkpoints:
    "40":
      metrics: [interchain_interactions]
      use_clean_prediction: true
      rewards:
        interchain_interactions.hbond_atom_pair_count_coi: {weight: 1.0}
    "60":
      metrics: [oracle]
      rewards:
        oracle.plddt_coi: {weight: 1.0}
```

Clean-prediction checkpoints run only design metrics and do not complete or save
scoring rollouts. Without a checkpoint at the schedule end, each retained beam
finishes once without extra branching or selection; ordinary final metrics run
but those outputs have no final `search.reward`.

Every prune ranks a **noisy** state. Early in the trajectory only broad features
are settled — fold, topology, whether an interface forms at all — so a candidate
killed at an early checkpoint on a fine detail it had not yet committed to is a
pass lost for nothing. Staging the reward to match what the trajectory has
actually decided by each checkpoint (broad structural features early, finer
details late) is therefore a **pass-rate** lever first and a cost lever second.

The cost lever is still real: explicitly listing oracles only at selected
checkpoints makes oracle calls scale with those checkpoints rather than all of
them, freeing budget for a wider beam. But do not assume the oracle belongs at
the end — the useful placement is wherever it changes *which candidates survive*,
which for some problems is mid-trajectory or even early. Treat both "flat vs
staged reward" and "where the oracle sits" as their own branches.

Two things to check when staging: a term added late is only worth it if it is
still *reachable* then (an objective the trajectory can no longer satisfy just
wastes the last prune), and a term dropped early must not be one the search will
irreversibly destroy before anything scores it again.

## Reward as a hypothesis

The score you optimize is not ground truth — it is a hypothesis about what matters,
made explicit so it can steer search and be replaced when better evidence arrives
(a predicted confidence today; a measured binding/expression/stability signal
later). Different composite rewards produce **different search behaviors**, not
just different numbers — so pick the reward that encodes the objective you actually
care about, and expect to iterate on the reward itself, not only the designs.

Do not compare `search.reward` totals across different reward functions — they are
different objectives (different units). Compare campaign arms using common final
metrics and pass criteria, even when those arms belong to the same campaign.

# Campaign strategy

Use this reference to choose experiments and decide when to move from baseline to
search, scaling, and partial diffusion. Execution mechanics remain in the sibling
skills; provenance and recovery remain in the campaign ledger references.

## Objective and scorecard

Agree on one primary campaign objective with the user. For a filtering campaign,
the useful default framing is unique passing designs per GPU-hour, where both
`passing` and `unique` refer to named, versioned definitions. Keep total passers,
failure rate, and metric distributions visible so efficiency does not hide a
collapsed family or incomplete evaluation.

Every experiment records:

- exact annotated-CIF input and resolved generation/search config;
- scientific hypothesis and the one attributable change from its parent branch;
- planned and observed sample count;
- actual metric values, passers, unique passers, wall time, and GPU-hours;
- failures, missing evaluations, and the decision to stop, retry, freeze, or
  promote the branch.

Best-of-N ordinary generation is the baseline. Search or partial diffusion earns
additional budget when it improves the agreed objective or provides information
needed to choose the next experiment.

## Input portfolio

Start from the validated annotated CIF and create explicit variants for material
conditioning hypotheses. Candidate levers include coordinate and sequence masks,
which atoms or sidechains are fixed, index groups, expandable segments, SSE,
burial/RASA, hydrogen-bond roles, and hotspot or interaction conditions. Use
`rfd4-proteina-annotated-cif` to confirm what the selected checkpoint supports
and to author each variant.

Do not turn a campaign preference into a universal condition. For example,
cysteine exclusion, sidechain freedom, or a particular secondary structure is
applied only when it follows from the user's design intent and model contract.

Aim for enough distinct inputs to test the hypotheses that matter, not an
arbitrary count. Register each variant before generation and retain its parent and
rationale.

## Criteria and reward allocation

Survey the configured metrics before adding a custom one. Define exact gating
criteria separately from ranking metrics and search rewards. A criterion that is
cheap and usually passes may be a post-hoc gate; a hard, informative metric may
justify reward-guided search. Measure cost and pass fraction rather than assuming
which category a metric belongs to.

For on/off-target design, name each oracle role and metric explicitly. Preserve
every transformed evaluation and prediction, and define whether gating uses an
absolute value, a target/off-target gap, or an aggregate over predictions.

Reward terms must use keys actually emitted at the scoring checkpoint. Normalize
or clip unlike scales deliberately, and keep weights synchronized with the active
metric tags. Use `rfd4-proteina-search` for the current reward schema.

## Pilot and baseline

Before scaling, take one input/config pair through generation, every required
oracle role, metrics, ledger ingest, criteria evaluation, reconciliation, and TAR
packaging. Confirm expected versus observed design and prediction counts, finite
metric values, and useful wall time.

Then run the best-of-N baseline over the input portfolio. Use its distributions to
identify the filters that dominate attrition and the inputs that merit search.
Record the full population, not only passers.

## Search exploration

Use `rfd4-proteina-autoresearch` for branch waves. Change one attributable axis per
child: input condition, reward term/weight, reward timing, beam/branch allocation,
trajectory settings, or diversity noise. Freeze and promotion rules are campaign
decisions recorded before allocation, not hidden defaults.

Use `rfd4-proteina-commitment-curves` when the useful checkpoint for a metric is
uncertain. Reward a property where the trajectory contains predictive signal;
avoid scoring checkpoints that only add cost or rank noise.

Save and register materialized intermediate candidates and checkpoint refolds.
For rare passers, inspect movement in the actual hard metrics and near-passer
counts rather than drawing conclusions from a small lucky sample.

## Scaling

Scale selected annotated-CIF/config pairs only after the pilot and baseline show
complete scoring. Discuss batch size, sharding, and job duration with the user in
the context of the selected hardware and queue. Never change partition, priority,
memory, GPU, or other scheduler choices without explicit instruction.

Use registered expected counts and incremental events to detect under-produced or
under-scored jobs. Reconcile before topping up or retrying so completed designs and
oracle predictions are not paid for twice.

## Partial diffusion

Use partial diffusion when the selected parent pool and baseline indicate that
local proliferation is useful. Register every parent-child edge, the annotated CIF
that supplies conditioning, and the resolved partial-diffusion config. Use the
current `partial_trajectory_fraction_steps` contract described by
`rfd4-proteina-generate`; do not substitute an unrelated absolute-time parameter.

Evaluate children as new designs. Parent metrics remain historical evidence and
are never copied forward as child results.

## Delivery

At the agreed stop condition, run final evaluations, apply the named criteria and
uniqueness versions, and reconcile all selected designs. Use
`rfd4-proteina-package` to create the database-free TAR while retaining the full
ledger as the internal reproducibility record.

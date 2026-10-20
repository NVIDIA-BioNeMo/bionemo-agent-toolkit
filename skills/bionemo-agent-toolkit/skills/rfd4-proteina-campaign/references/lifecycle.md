# Campaign lifecycle

Use this reference to plan the campaign and decide when to advance between phases.

## 1. Interview and initialize

Record the scientific objective, target or motif, design cases, requested outputs,
compute budget, stop condition, cluster, and scheduler choices. Ask what counts as
a passer and what counts as unique; do not infer either from a benchmark config.

Run setup preflight, create the campaign directory, and initialize
`campaign.sqlite`. Capture the RFD4-Proteína and AtomWorks revisions, checkpoint
identity, and any dirty diff needed to explain the running code.

## 2. Build the input portfolio

Inspect prose, structures, and annotated CIFs with
`rfd4-proteina-annotated-cif`. Preserve the original annotated CIF and create explicit
variants for each conditioning hypothesis. Validate and register every variant
before using it in a run.

Do not silently add conditions during later phases. A new conditioning hypothesis
is a new registered input with a recorded parent and rationale.

## 3. Freeze a criteria version

Write each gating criterion as an exact metric name, operator, threshold, and
missing-value policy. Record ranking-only metrics separately. Define uniqueness
by the requested sequence or structural rule and configuration.

Pilot the complete metric stack on a small sample. Confirm that every required
metric is present and scientifically sensible before freezing the first criteria
version.

## 4. Establish the baseline

Run an ordinary best-of-N baseline for every input worth comparing. Record sample
count, pass rate, unique passers, wall time, GPU-hours, and failure rate. The
baseline is the reference against which search and partial diffusion are judged.

## 5. Explore deliberately

Treat an input/config pair as an experiment branch. Use autoresearch waves to
freeze, promote, and allocate branches; mutate one attributable choice per child.
Use commitment curves when the useful timing of a reward is unknown.

Record the hypothesis and decision before the child run. Failed branches remain
queryable evidence and are never removed from the ledger.

## 6. Scale and proliferate

Scale only input/config pairs supported by the pilot and baseline. Re-read the
launcher and user profile before every submission, state the scheduler resolution,
and preserve it exactly.

When partial diffusion is used, register every parent and child. The child keeps
the original annotated-CIF input, partial-diffusion config, parent design, and new
evaluation history as separate links.

## 7. Final evaluation and delivery

Run the requested final oracle and post-hoc evaluations. Preserve all predictions
and confidence artifacts, then evaluate the named criteria version from the exact
metric observations. Apply the named uniqueness definition after gating.

Use `rfd4-proteina-package` to create the recipient-facing TAR. Reconcile the
ledger before declaring the campaign complete.

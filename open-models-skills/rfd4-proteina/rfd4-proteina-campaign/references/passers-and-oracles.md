# Passers, uniqueness, and oracle evidence

## Criteria versions

A criteria set is immutable. Each criterion names an actual metric, comparison
operator, threshold, display label, and missing-value policy. Supported operators
are `<`, `<=`, `>`, `>=`, `==`, and `!=`.

Evaluate all criteria in their declared order. Store the actual metric value and
metric-observation ID used for each result. A new threshold or missing-value rule
creates a new criteria set; it does not change an existing evaluation.

After importing new or corrected metrics, rerun `evaluate-passers` with the same
criteria-set ID. Changed criterion evidence appends a new decision revision;
unchanged evidence creates no duplicate. Earlier decisions and their exact
observations remain available in `show-design`. Delivery uses only the latest
revision per design and criteria set, including when a correction revokes a pass.

Ranking metrics do not gate passers. Keep them available in exports without
representing them as filters.

## Oracle outputs

An oracle evaluation belongs to one source design and has an explicit role such
as `on-target`, `off-target-X`, `checkpoint-50`, or `final`. Preserve every model
sample and seed as an `oracle_prediction`, even when only one contributes to an
aggregate metric.

Link prediction-derived metrics to the exact prediction. If a criterion uses an
aggregate over predictions, record the aggregate as a distinct metric observation
whose evaluator/configuration explains the reduction.

Failed evaluations stay in the ledger with their input design, backend, role,
status, and error. Do not treat absence of a prediction as a passing or zero value.

## Uniqueness

Define uniqueness independently from gating. Record the clustering or sequence
comparison method, thresholds, tool version, cluster ID, and representative rule.
A unique passer is a passer under one criteria version and a representative under
one uniqueness version.

The initial ledger schema records cluster fields on export-compatible metrics;
keep full clustering artifacts alongside the campaign when the method produces
them. Do not silently collapse passers without naming the uniqueness definition.

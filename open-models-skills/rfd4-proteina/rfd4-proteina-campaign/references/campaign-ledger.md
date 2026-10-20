# Campaign ledger

The campaign root contains `campaign.sqlite`, a content-addressed `artifacts/`
directory, immutable worker events under `runs/`, and regenerated exports. SQLite
is the canonical metadata record; the archived files are the canonical artifacts.

## Identity and lineage

- `inputs` link exact annotated-CIF artifacts and optional parent inputs.
- `config_snapshots` link original and fully resolved configs plus CLI overrides.
- `runs` link one input/config pair, phase, command, output root, status, and exact
  scheduler allocation.
- `designs` link the generated CIF to its run, seed/sample identity, chain of
  interest, and optional parent design or search checkpoint.
- `oracle_evaluations` describe backend, role, model, status, and configuration.
- `oracle_predictions` preserve every prediction CIF and available confidence JSON.
- `metric_observations` hold actual values and link to the design and, when
  applicable, exact oracle prediction.
- `criteria_sets`, `criteria`, `passer_evaluations`, and `criterion_results` keep
  threshold definitions and the observations used to evaluate them.

Artifact paths stored in the database are relative to the campaign root. Each
artifact is archived by SHA-256 so repeated inputs or predictions are deduplicated.
The digest and size describe the staged copy, even if a worker replaces its source
during ingestion. Resolved-config hashes use that archived snapshot as well. The
database also retains the original path for operator context.

Schema v2 retains decision revisions. Opening a v1 database with the ledger helper
upgrades it transactionally: existing decision IDs, criterion evidence, and all
other records are preserved. A failed foreign-key check rolls the upgrade back.
The read-only package builder requires v2; run `evaluate-passers` with the updated
ledger helper after importing metrics and before delivery. The
`latest_passer_evaluations` view exposes one current decision per design and criteria
set; the underlying table retains all revisions.

Both metric exports and criterion evaluation choose observations by descending
`observed_at`, breaking ties by insertion order. A correction imported at the same
timestamp wins; a later import with an older observation timestamp does not.

## Worker events

Workers emit one JSON object per line with a stable `event_id`. Supported event
types are `design`, `oracle_evaluation`, `oracle_prediction`, `metrics`, and
`run_status`. Paths are resolved relative to the event file.

```json
{"event_id":"e1","type":"design","design_id":"d1","run_id":"r1","cif_path":"d1.cif","chain_of_interest":"B"}
{"event_id":"e2","type":"oracle_evaluation","evaluation_id":"oe1","design_id":"d1","backend":"af3","role":"on-target"}
{"event_id":"e3","type":"oracle_prediction","prediction_id":"op1","evaluation_id":"oe1","cif_path":"op1.cif","confidence_path":"op1.json"}
{"event_id":"e4","type":"metrics","design_id":"d1","prediction_id":"op1","evaluator":"af3","values":{"on_target_af3_min_ipae":4.2}}
```

Import is transactional and idempotent. A repeated `event_id` is skipped. Do not
edit imported events; append a correcting event with a new ID.

## Required records

Register inputs and resolved configs before planning runs. Register a run before
submission. A completed design needs an archived CIF and a direct run link. A
completed oracle prediction needs its evaluation and source design. Missing or
failed metrics are observations with explicit status rather than absent success.

Use `reconcile` after every run and before packaging. It verifies that archived
files exist and match their recorded checksum, and reports incomplete designs,
oracle evaluations, and criterion evidence without deleting records.

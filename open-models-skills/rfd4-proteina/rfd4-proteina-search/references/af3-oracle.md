# AF3 oracle runtime

## Current interface

The AF3 oracle refolds a design and reports confidence metrics through the metric
keys configured in `configs/metrics/refolding_oracles/af3.yaml`. Common reward
keys include `oracle.plddt_coi`, `oracle.iptm_coi`, `oracle.ipae_coi`, and
`oracle.min_ipae_coi`.

Generation and evaluation select oracles through metric tags. Search selects
providers by name in each checkpoint's `metrics` list, e.g. `[oracle]` or
`[oracle_ppi]`. Design-only scoring such as `[interchain_interactions]` does not
use AF3; final evaluation can independently request it.

## Runtime configuration

Configure the selected oracle's image, weights, and cache paths in `.env.local`,
as described in the [installation guide](../../rfd4-proteina-setup/references/environment.md).
Verify that the required paths are readable in the execution environment.

Run generation in the Python environment activated during setup:

```bash
rfd4-generate inference_experiment=inference_beam_example
```

The model runs in that Python environment; refolding uses the separately configured
oracle runtime and host launcher.

## Search and evaluation behavior

Each `search.checkpoints.<step>.metrics` list explicitly selects oracle providers
and any refold comparison metrics. Search does not infer dependencies. The
top-level `metrics_tags` controls final reporting; when it selects an oracle
already run on that output, final evaluation can reuse the cached result.

If expected oracle columns are absent during search, check the checkpoint's
metric names, the selected backend, and its runtime. For final reporting, also
check `metrics_tags`. When the schedule-end checkpoint is omitted, final designs
have no cached search refolds and ordinary final evaluation runs as configured.

Source of truth: `configs/metrics/refolding_oracles/af3.yaml`,
`src/rfproteina/metrics/oracles/af3_oracle.py`, `.env.local`, and
`docs/workflow/metrics.md`.

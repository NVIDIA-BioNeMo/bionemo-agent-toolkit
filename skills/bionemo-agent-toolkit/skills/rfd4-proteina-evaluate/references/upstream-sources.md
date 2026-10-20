# Resolve the installed metric contract

The model source and manuals are external prerequisites of this skill catalog.
Use the user's RFD4-Proteina checkout and its activated Python environment. Set
`RFPROTEINA_ROOT` to that checkout's absolute path; model commands run there.

| Needed detail | File relative to the model checkout |
| --- | --- |
| Full metric columns, tags, and thresholds | `docs/workflow/metrics.md` |
| Custom classes, Hydra registration, and worked examples | `docs/workflow/custom-metrics.md` |
| Evaluation and aggregation workflow | `docs/workflow/running.md` |
| Environment and refolding backends | `docs/installation.rst` |

Read the relevant manual from that checkout, rather than resolving its path
relative to the installed skill. For example:

```bash
test -f "$RFPROTEINA_ROOT/docs/workflow/custom-metrics.md" || exit 1
```

The bundled metrics reference summarizes the imported revision. Check the
checkout's composed configs under `configs/metrics/` before selecting tags,
thresholds, or custom classes. If a required manual or implementation is absent,
obtain it from the operator for that revision before constructing a custom
metric. Do not infer metric availability from a name in the summary table.

Record the model revision, selected metric config, and actual returned columns
with each evaluation. Missing oracle outputs remain unmeasured.

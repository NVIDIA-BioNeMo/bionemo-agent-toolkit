# Operational constraints and failure conditions

## Phase-2 conditioning must equal phase-1 conditioning

**Do not re-run a stochastic sampling transform in phase 2.** Anything that re-draws a
conditioning target per replicate moves the conditioning away from the parent and adds a
second source of variation on top of the noise being measured. Setting its `scale: 0` is
*not* equivalent — that pins the target at a distribution mean, which is also not the
parent's value. Remove the transform.

## Naming and joins

- Follow [Step 5](../SKILL.md#step-5--assemble-the-parents-into-a-flat-directory)
  for generated-only parent links, stable IDs, and preserved compression suffixes.

## The fidelity curves go missing

- **A custom `metrics_group` that drops the inline design metrics drops them too.**
  `sequence_similarity_to_input` and `ca_rmsd_to_input` live in
  `configs/metrics/inline_metrics/design_metrics.yaml`, gated on the `partial_diffusion`
  tag that `generate.py` adds by itself for any partial-diffusion run. Keep the inline
  design metrics in the group or `commitment_curve.py` warns and writes only the ρ figure.
- **CA RMSD is silent when the CA counts differ.** `StructureComparisonMetric` returns
  nothing rather than a wrong number, so a run with insertions loses that column with only
  a log line. Sequence identity returns `nan` in the same situation.

## The distribution figure lies quietly

- **A threshold far outside the data does not move the axis.** Stretching to reach it
  would collapse every bar into one bin, so the cut is left off screen and its caption
  reads *(off axis)*. The pass rate beside it is still correct — but a fully shaded panel
  with no visible line means "everything passes", not "no threshold".
- **`--pass_criteria` defaults to the repo config, not the one the run used.** If the run
  scored against a custom `metrics_group`, its criteria live in a git-ignored
  `configs/metrics/custom_metrics/`, and the default config's thresholds are then the
  wrong numbers on a plausible-looking chart. Point `--pass_criteria` at the file the run
  actually composed.
- **A tail estimate off a bimodal metric is worthless**, and the two the script computes
  can differ by three orders of magnitude on one — see the *poor fit* flag and the
  disagreement note in [method.md](method.md). Refolding confidence metrics (ipTM, pLDDT)
  are the usual offenders, because "folded" and "not folded" are two populations.
- **Nothing checks that a criterion's metrics were all computed.** A pass criterion is
  indeterminate, not failed, when a key is missing; the histogram of the keys that *are*
  present will happily imply a pass rate the run could never have scored. Cross-check
  against the criterion's `all_metrics_present` column.

## Cluster mechanics

- **Aggregation jobs request no GPU.** Some clusters deny a GPU-partition job with no
  `gres`, in which case every concatenation job fails to submit while generation runs
  fine — runs complete and quietly never produce a merged CSV. Both launchers use
  `CPU_PARTITION` when nonempty, otherwise `PARTITION` when nonempty, and finally
  `batch`. Set `CPU_PARTITION` to the operator's CPU partition in the cluster configuration.
- **Resume with the same design IDs and output directory.** `skip_existing=true`
  loads saved structures across supported encodings and evaluates them without
  regenerating or rewriting them. Size the time limit to include the metric stage.
- **Foldseek off.** Clustering near-identical designs costs time and answers nothing here.

## Cost

One full generation per parent per grid point, plus metrics. A 20-point grid over 128
parents is 2,560 designs — before any refolding oracle, which typically dominates. Pilot
a coarse grid (6 points, few parents) and confirm both controls before densifying.

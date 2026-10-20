# Cost and runtime

Reward-guided search is **much more expensive** than plain generation. Scoring
checkpoints evaluate every branched candidate, and those listing refolding
oracles run the selected backends for each candidate. Budget accordingly.

## The cost model

For one refold per candidate at each oracle-scored checkpoint:

```
search oracle calls  ~  beam_width  x  n_branch  x  (oracle-scored checkpoints)
```

Count entries in `search.checkpoints` that explicitly list an oracle. Step zero
is implicit and is not scored. The shipped example has keys `20`, `40`, `50`,
and `60`: four scoring checkpoints.

| beam_width | n_branch | oracle-scored checkpoints | ~search oracle calls per input |
| --- | --- | --- | --- |
| 3 | 2 | 4 | ~24 |
| 4 | 4 | 4 | ~64 |
| 8 | 4 | 4 | ~128 |
| 4 | 4 | 8 | ~128 |

Multiply by `num_replicates` and the number of input examples. Multiple named
oracles or transforms emitting multiple refolds add calls per candidate.
Design-only and clean-prediction checkpoints make no oracle calls. Clean
prediction scoring also avoids completing separate scoring rollouts.

Ordinary final evaluation can add refolds when no cached result exists. In
particular, omitting the schedule-end checkpoint finishes each retained beam
once without search scoring, but final `metrics_tags` can still request oracles.
Saved scoring rollouts can also need final metrics not computed during search.

## Practical guidance

- **Start small.** Validate a config end to end at tiny settings (small
  `beam_width`/`n_branch`, few short checkpoints, small `nsteps`) before scaling.
- **`beam_width` and `n_branch`** are the two biggest cost multipliers. Defaults
  are 4 and 4; the example ships 3 and 2. Raise them only as compute allows —
  higher values buy quality/diversity at linear cost.
- **`search.checkpoints`** — more entries mean more scoring passes. Keys are
  positive steps no greater than the actual schedule length; zero is implicit
  and the schedule-end entry is optional. Choose each checkpoint's metric list
  and scoring source deliberately.
- **`save_rollouts` and `save_criteria`** reuse already-computed scoring metrics
  when retaining candidates, but increase output count and may add final-evaluation work.
- **Prefer non-refold rewards when they capture your objective** (e.g. interface
  H-bond counts) — they avoid the oracle entirely.

## Compared to plain generation

`rfd4-proteina-generate` runs **one trajectory per design with no oracle** — a
single forward sampling pass, optionally followed by metrics. Search runs many
trajectories and scores each, so a search run can cost tens to hundreds of times
more than generating the same number of final designs.

Use plain **rfd4-proteina-generate** for a cheap baseline or when you need many
designs quickly; use search when quality-per-design justifies the refolding or
reward-computation budget.

## SLURM

For real runs, submit through `scripts/launch_generate.sh` with a search
`inference_experiment`. See the main [SKILL.md](../SKILL.md) Step 5 and the
[installation guide](https://github.com/RosettaCommons/RFD4-Proteina/blob/main/docs/installation.rst).

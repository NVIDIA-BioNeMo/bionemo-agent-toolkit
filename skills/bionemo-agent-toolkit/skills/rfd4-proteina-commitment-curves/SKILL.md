---
name: rfd4-proteina-commitment-curves
description: Use for RFD4-Proteina commitment timing, partial-diffusion sweeps, parent-child correlations, and metric distributions.
license: CC-BY-4.0 AND BSD-3-Clause
allowed-tools: Bash, Read, Write
metadata:
  author: Ohad Mosafi <omosafi@nvidia.com>
  tags: [protein-design, rfd4, commitment-curves]
---

# RFD4-Proteína Commitment Curves

## Purpose

Take a finished design, re-noise it back to a restart step, denoise it again, and ask
how much its metric still agrees with its parent's. Sweep the restart step and you get a
curve that says **when the model made up its mind** — restart near the end and the child
reproduces its parent (ρ → 1); restart near the start and it no longer recovers the
parent's answer. The payoff is knowing how early you can screen: if a metric is at
ρ = 0.97 by step 25, the last 75 steps cannot change its ranking.

**The convention that is easy to get backwards: `t = 1` is clean, `t → 0` is pure
noise.** `partial_trajectory_fraction_steps` is the *fraction re-run*, so restart step =
`(1 - frac) * nsteps`. A small fraction means LESS noise and a SHORTER re-run.

Run everything from the **repo root**. All arguments are Hydra `key=value`.

## Prerequisites

The model runtime for sampling; pandas, NumPy, SciPy, Matplotlib, PyYAML, and Python Fire for the bundled analysis helpers.

Use the user-selected model checkout at `RFPROTEINA_ROOT` for model commands,
configs, and upstream manuals. This catalog contains the skills, not that checkout.
In helper examples, resolve `open-models-skills/rfd4-proteina/<name>/...` to its absolute installed path
when the catalog and model checkout are separate.

## Inputs

Required: the user's parent inputs or generation spec, metric names, output directory, and compute budget. Optional: restart grid, sampling settings, and pass-criteria file; derive metric thresholds from the config actually used.

## Instructions

### Step 1 — Settle what you are tracking

Ask the user which metrics the curve should follow, unless a spec already says. Each is
one line on the plot; **three is the maximum** the palette stays colourblind-safe for.

**Two curves come free and are always drawn**, so do not spend a slot on them: sequence
identity to the parent and CA RMSD to the parent. Phase 2 feeds the parent CIF in as the
*input* structure, so `sequence_similarity_to_input` and `ca_rmsd_to_input` measure the
child against its own parent with no join. They must reach 100% and 0 Å at the clean end,
and they are the scale the ρ curves get read on (see *Reading the result*).

- **Which metrics?** They must be columns in the metrics CSV — check a
  `configs/metrics/<group>.yaml`; any `*_refolding` tag needs the AF3 container.
  `rfd4-proteina-evaluate` [references/metrics.md](../rfd4-proteina-evaluate/references/metrics.md)
  lists what is available. A custom `metrics_group` must keep the inline design metrics,
  or the two free curves vanish with it.
- **How many parents?** ρ is computed *across* parents, so its precision follows the
  parent count, not the design count. Budget **40+**; ρ from 4 parents has a confidence
  interval near ±0.9.
- **Do they already have designs?** If so, score those instead of generating new ones.

## Step 2 — Write the spec and generate the configs

One spec produces all three configs, which is what keeps both phases scoring parents and
children by the *same* code path:

```yaml
name: my_commitment
inputs: /path/to/design_inputs        # phase-1 design problems (a directory of CIFs)
parents_dir: /path/to/parents         # the flat parent directory built in step 5
out_root: /path/to/runs

metrics_group: tcr_design             # a configs/metrics/<group>.yaml; omit for all_metrics
metrics_tags: [design, tcr_design]    # what actually switches metrics on

phase1:
  num_replicates: 4                   # replicates belong HERE — each one is another parent
  batch_size: 4
  existing_designs: null              # a directory -> skip generation, score it offline

phase2:
  step: 5                             # grid every N of nsteps
  nsteps: 60
  batch_size: 4
  gen_njobs: 1                        # >1 only helps where gen_njobs can divide examples
```

```bash
python open-models-skills/rfd4-proteina/rfd4-proteina-commitment-curves/scripts/make_configs.py --spec my_study.yaml
```

It writes `configs/inference_experiment/<name>_phase1.yaml`,
`configs/inference_experiment/<name>_sweep.yaml` and `configs/sweeps/<name>.yaml`, then
prints the commands for the remaining steps. `--dry_run` previews. Edit the generated
configs freely for cluster specifics (`hardware:`, transforms).

`phase2.nsteps` sets `generation.args.nsteps` in the phase-2 experiment and the
`--nsteps` argument in the printed analysis command. Keep that count consistent
with the sweep fractions if editing the generated files.

**Phase 2 is one child per parent, and the generator enforces it.** Extra children of
one parent are correlated with each other and buy a within-parent spread estimate rather
than a tighter curve. Spend replicates in phase 1, where each becomes another parent.

## Scheduler intent

For any batch run, read the selected `scripts/.user_info_<cluster>` and the
launcher before constructing the command. Preserve the user's partition,
account, QoS/priority options, GPU request, runtime, memory, and CPU settings.
Use a resource override only when the user explicitly requested it. State the
resolved scheduler values before submission; use dry-run or non-submitting tests
when validating the workflow.

## Step 3 — Phase 1: get the parents

**Either** generate them:

```bash
./scripts/launch_generate.sh inference_experiment=<name>_phase1 --no-foldseek
```

**Or**, if the user already has a curated set, score it offline so the parents carry
metric values from the same metric set:

```bash
rfd4-evaluate inputs=/path/to/curated \
    metrics_tags='[design,...]' out_dir=<out_root>/<name>_phase1
```

Foldseek is off on purpose: clustering near-identical designs costs time and answers
nothing here.

## Step 4 — Ask how rare each metric is before buying the sweep

The parents are the only unbiased sample of the design problem you will get. Before phase 2,
ask them about *difficulty* — a question the commitment curve cannot answer, because ρ is
scale-free and says nothing about whether anything passes:

```bash
python open-models-skills/rfd4-proteina/rfd4-proteina-commitment-curves/scripts/metric_distributions.py \
    --metrics_csv <out_root>/<name>_phase1/per_example_metrics.csv \
    --out_dir <out_root>/<name>_phase1/analysis
```

One histogram per metric, in one figure. Thresholds are read straight out of
`configs/metrics/pass_criteria/all_pass_criteria.yaml` — the same numbers the run scored its
`*.pass` columns with — and drawn as vertical cuts with the passing side shaded. Only criteria
whose columns are present in the CSV appear. Narrow with `--criteria ppi,sm_binder`, point
`--pass_criteria` at a custom config, and add `--metrics 'Label=col:min=1.5'` for a metric no
criterion covers.

Beside every cut: how many designs passed, and **how many you would have to sample for one**.
Where too few passed for that to mean anything (fewer than 10), the figure quotes an
extrapolation instead — a generalised-Pareto fit to the tail, or the best-AIC density curve
drawn over the histogram — and always names which one. That is how a criterion nothing passed
still gets a number.

Three readings worth acting on:

- **Nothing passes and the extrapolated rate is 1 in thousands.** Either the threshold is wrong
  for this problem or the campaign needs a different search; knowing when the model commits
  fixes neither. Settle that before buying the sweep.
- **Nearly everything passes.** The criterion is not selecting, so a commitment curve on it
  measures noise. Spend the slot on something that discriminates.
- **A caption reading *poor fit*, or two models disagreeing by 10x** — the figure prints the
  second whenever they do. The metric is usually bimodal, and no tail estimate off it is worth
  quoting; say the rate is below what the sample resolves and move on.

The script takes any run's `per_example_metrics.csv`, not only phase 1's.

## Step 5 — Assemble the parents into a flat directory

Phase 2's `inputs=` needs a directory holding *only* designs — a phase-1 run directory
also contains refolded oracle CIFs. Link designs into a new directory, dropping
`_generated` so each child's `task` matches its parent's `example_id`. Keep the
compression suffix; phase 2 reads compressed inputs directly:

```python
from pathlib import Path
from rfproteina.utils.structure_files import iter_structure_files, structure_file_stem

sources = iter_structure_files("<out_root>/<name>_phase1", stem_suffix="_generated")
stems = [structure_file_stem(path) for path in sources]
if not sources or len(set(stems)) != len(stems):
    raise ValueError("Expected generated designs with unique parent IDs")
parents = Path("<parents_dir>")
parents.mkdir(parents=True)  # Refuse an existing destination.
for path, stem in zip(sources, stems, strict=True):
    name = stem.removesuffix("_generated") + path.name[len(stem):]
    (parents / name).symlink_to(path.resolve())
```

Keep the source run directory while using these links.
After the **offline** path there is nothing to assemble — the curated directory already
holds only designs, so point `parents_dir` at it directly.

Design IDs preserve internal dots: `design_z1.61.cif.zst` has ID `design_z1.61`.

## Step 6 — Phase 2: sweep the restart step

```bash
./scripts/launch_sweep.sh --sweep-config configs/sweeps/<name>.yaml \
    --base-out-dir <out_root>/<name>_sweep --no-foldseek
```

One run per restart step, each with its own concatenation job, then a dependent
sweep-level job that merges everything into `sweep_per_example_metrics.csv`. Lineage
needs no bookkeeping: `task` is the parent and
`generation.args.partial_trajectory_fraction_steps` is the restart step.

Parallelism comes from the sweep points running side by side. Raising `phase2.gen_njobs`
splits a single restart step further, but only helps where `gen_njobs` can divide
*examples* — with one replicate per parent there is nothing else for it to divide.

Sanity-check the clean end before reading anything else: the smallest fraction **must**
reproduce the parents — ρ ≈ 1, and, more bluntly, sequence identity ≈ 100% with CA RMSD
≈ 0 Å. Those are plumbing controls, not data points.

## Step 7 — Plot the commitment curve

```bash
python open-models-skills/rfd4-proteina/rfd4-proteina-commitment-curves/scripts/commitment_curve.py \
    --sweep_csv <out_root>/<name>_sweep/sweep_per_example_metrics.csv \
    --parent_csv <phase-1 per_example_metrics.csv> \
    --out_dir <out_root>/<name>_sweep/analysis \
    --nsteps 60 \
    --metrics 'Docking Z=tcr_docking_geometry.docking_z,Interface E=...'
```

Replace `60` with the study's `phase2.nsteps` when using a different trajectory length.

Writes a tidy `commitment_curve.csv` (one row per metric x step, with bootstrap CIs) plus
light and dark PNGs. A metric column may be `Label=min(colA|colB)` to reduce several
columns to their row-wise minimum first.

The same command also writes `fidelity_curve.csv` and its PNGs — the median sequence
identity and CA RMSD to the parent per restart step, with the same parent-level bootstrap.
No flag switches them on; if the columns are missing it warns and writes only the ρ curve.

## Reading the result

Say the crossing point in steps, not "early/late": *above step X the property is
preserved; by step Y a child is indistinguishable from an independent design.* Five
things that are not obvious:

1. **ρ does not fall to 0 at step 0.** If the parents are different design problems, a
   fully regenerated child still inherits its problem. The step-0 value is the
   between-problem floor — how much of the metric the *input* fixes regardless of
   trajectory.
2. **ρ need not reach 1 at the clean end.** There the child is structurally its parent,
   so anything below 1 is that metric's own reproducibility ceiling (a stochastic relax,
   a sampled oracle). A metric ceilinged at 0.7 is noisy, not uncommitted.
3. **Check the children's absolute values too.** Below some restart step children may not
   only forget their parent but land on measurably *worse* structures than a fresh run,
   which makes partial diffusion pointless there. Correlation alone hides that.
4. **Read ρ against the fidelity curves.** They separate two things ρ conflates. Where
   identity and CA RMSD say the child is still essentially its parent, a metric whose ρ
   has already fallen is *sensitive* — small changes move it — not uncommitted. Where the
   child is structurally a different protein, high ρ is the conditioning speaking, not
   memory of the trajectory. Quote the restart step where each fidelity curve leaves its
   plateau; that is the step the model stopped rebuilding and started refining.
5. **Pair every ρ with its pass rate from step 4.** They are orthogonal, and only the two
   together are a screening recommendation: "committed by step 30 *and* 1 in 12 designs
   passes" means screen early and cheaply, while "committed by step 30 *and* 1 in 4,000
   passes" means the screen is right but the budget is not.

See [references/method.md](references/method.md) for the statistics and
[references/gotchas.md](references/gotchas.md) for operational constraints and failure conditions.

## Limitations

Correlation measures preservation across parents, not biological success. Small parent sets, stochastic metrics, and mismatched conditioning can invalidate the interpretation; inspect the controls below.

## Troubleshooting

For missing fidelity columns, joins, aggregation, or unreliable tail fits, read [operational constraints](references/gotchas.md) and [statistical interpretation](references/method.md).

## Examples

Use the study YAML and `make_configs.py` command in Step 2, then the distribution and correlation commands in Steps 4 and 7. Start with a coarse pilot before funding the full sweep.

## Available Scripts

| Script | Purpose | Arguments |
| --- | --- | --- |
| `scripts/make_configs.py` | Generate matching phase and sweep configs | `--spec`; optional `--repo_root`, `--dry_run` |
| `scripts/metric_distributions.py` | Plot metrics against criteria | `--metrics_csv`, `--out_dir`; optional `--pass_criteria` |
| `scripts/commitment_curve.py` | Correlation and fidelity curves | `--sweep_csv`, `--parent_csv`, `--out_dir`, `--metrics` |

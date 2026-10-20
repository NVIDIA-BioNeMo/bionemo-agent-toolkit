---
name: rfd4-proteina-evaluate
description: Use when scoring existing RFD4-Proteina designs, aggregating metrics, adding custom metrics, or clustering diversity.
license: CC-BY-4.0
allowed-tools: Bash, Read, Write
metadata:
  author: Ohad Mosafi <omosafi@nvidia.com>
  tags: [protein-design, rfd4, evaluate]
---

# RFD4-Proteína Evaluate (post-hoc metrics + aggregation)

## Purpose

Score structures that already exist on disk, without re-running generation.
`evaluate.py` shares the exact same metrics stack and Hydra config as generation,
so any `metrics_tags` or custom-metric config behaves identically inline and
offline. The two things this skill exists to get right: (1) pick the *right*
metric tags for the design task (and know which ones silently need the AF3
container), and (2) aggregate the parallel per-job CSVs into one table before you
try to read results.

Run everything from the repository root (the directory containing `.project-root`). **All arguments are
Hydra `key=value`, never `--key value`.**

## Inline (during generation) vs post-hoc (this skill)

- **Inline** — pass `metrics_tags` to `generate.py`; metrics run immediately
  after each design and land in `per_example_metrics.csv` next to the CIFs. Best
  when you already know what you want measured. See **rfd4-proteina-generate**.
- **Post-hoc** — this skill. Score a folder of CIFs you already generated, add
  metrics you forgot to turn on, or re-score with different tags. Same config,
  same outputs.

## Prerequisites

A configured model environment and existing design CIFs. Refolding additionally needs its selected oracle backend; diversity clustering needs FoldSeek.

Use the user-selected model checkout at `RFPROTEINA_ROOT` for model commands,
configs, and upstream manuals. This catalog contains the skills, not that checkout.
In helper examples, resolve `open-models-skills/rfd4-proteina/<name>/...` to its absolute installed path
when the catalog and model checkout are separate.

## Inputs

Required: the user's structure directory, metric tags, and output directory. Optional: task CSV, custom metric config, and clustering. Read thresholds from the config actually used, not an unrelated default.

## Instructions

### Step 1 — Run evaluate.py over a folder of structures

```bash
rfd4-evaluate \
    inputs=/path/to/structures \
    metrics_tags='[design]' \
    out_dir=/path/to/eval_output
```

- `inputs` — a directory scanned recursively for CIF-like files. Required.
  To evaluate one structure, place it in a dedicated directory.
- `metrics_tags` — a **bracket-quoted Hydra list**: `'[design]'`,
  `'[unconditional_refolding]'`, or multiple, e.g.
  `'[design, unconditional_refolding]'`. Required (no default in
  `configs/evaluate.yaml`).
- `out_dir` — required; `evaluate.py` has no run directory to derive one from.
  Results go under `out_dir/evaluation_metrics/`.
- `task_csv=<csv>` — optional; a CSV with `designed_structure_path` and `task`
  columns when different structures need different tag/pass-criterion treatment.
  Otherwise every structure is scored the same way.

Design tags and refolding tags are **separate namespaces** — pass both families
if you want both to run. See [references/metrics.md](references/metrics.md) for
the full tag table and semantics.

## Scheduler intent

For any batch run, read the selected `scripts/.user_info_<cluster>` and the
launcher before constructing the command. Preserve the user's partition,
account, QoS/priority options, GPU request, runtime, memory, and CPU settings.
Use a resource override only when the user explicitly requested it. State the
resolved scheduler values before submission; use dry-run or non-submitting tests
when validating the workflow.

## Step 2 — Aggregate across parallel jobs

Large evaluations split across SLURM array jobs; each job writes its own
`per_example_metrics_job{N}.csv`. After **all** jobs finish, concatenate:

```bash
python -m rfproteina.inference_utils.aggregate_metrics /path/to/eval_output/evaluation_metrics/
```

The metrics directory is the first **positional** argument. This concatenates
the per-example job CSVs, writes `aggregated_metrics.csv` and
`per_task_metrics.csv`, and moves the individual job files into
`individual_job_results/`. Aggregation moves those source CSVs and can replace
existing aggregate outputs. Preserve prior results before repeating it; use a
fresh `--output_dir` for a separate aggregate (source CSVs are still moved). Flags: `--output_dir <dir>` to write elsewhere,
`--cluster_with_foldseek` for diversity clustering (Step 3). With
`scripts/launch_evaluate.sh` (or `launch_generate.sh`) this aggregation runs
**automatically** as a dependent SLURM job — foldseek on by default; disable with
`--no-foldseek`.

## Step 3 — FoldSeek diversity clustering (optional)

```bash
python -m rfproteina.inference_utils.aggregate_metrics /path/to/eval_output/evaluation_metrics/ \
    --cluster_with_foldseek
```

Adds a `foldseek_cluster_id` column so you can count structurally distinct
designs per task. Clustering is **scoped to the designed chain** (the
`chain_of_interest`, identified from conditioning annotations and stored in the
metrics CSV) at a TM-score threshold of 0.5. `FOLDSEEK_EXEC` in the active environment must point at the FoldSeek executable.
Post-hoc `evaluate.py` writes the designed-chain CIFs that its aggregation step
needs. Generation-time aggregation instead requires
`save_chain_of_interest=true` so generation writes those chain CIFs.

## Step 4 — Custom metrics (no tracked-file edits)

Both custom-metric directories are git-ignored, so nothing you add here is ever
committed:

- `src/rfproteina/metrics/custom_metrics/` — your Python `Metric` subclasses.
- `configs/metrics/custom_metrics/all_custom_metrics.yaml` — Hydra registration
  (scaffolded by `setup.sh` on first run; `# @package metrics`).

They are picked up automatically (no extra flags), and results land in
`per_example_metrics.csv` prefixed by the config key (e.g.
`residue_count.n_residues`). Often you don't even need new Python — an existing
ready-made-but-opt-in class (interface ddG, atom-pair distance constraints,
charge complementarity, ...) just needs a few lines of YAML. See
[docs/workflow/custom-metrics.md](references/upstream-sources.md) and
[references/metrics.md](references/metrics.md).

## The AF3-container caveat (read this)

Refolding metrics (`refolded_backbone_rmsd`, `refolded_motif_*_rmsd`, ...) and
the refolding **oracles** (`oracle`, `oracle_ppi`, `oracle_dna` — the AF3
variants) run the AF3 structure predictor, which runs **only inside an
apptainer/docker container** configured via the cluster env files. Plain
(non-refolding) design metrics like `[design]` do **not** need a container. If
you request a refolding tag without the container, those metrics silently do not
run — you get no oracle columns and no error. Configure the container first (see
**rfd4-proteina-setup**, [RFD4-Proteína installation guide](references/upstream-sources.md),
or use `scripts/launch_evaluate.sh ...` which wires it in.

## Metrics-tag reference

A compact table of the imported metric, oracle, pass-criterion, and filter entries,
their categories and config paths, the tag semantics
(`required_tags_any` / `required_tags_all` / `prohibited_tags`), and the opt-in
classes is in [references/metrics.md](references/metrics.md). The full source of
truth is [docs/workflow/metrics.md](references/upstream-sources.md).

## Outputs

| File | Written by | Contents |
| --- | --- | --- |
| `per_example_metrics.csv` (or `per_example_metrics_job{N}.csv`) | `evaluate.py` / `generate.py` | One row per design; metric columns prefixed by config key |
| `aggregated_metrics.csv` | `aggregate_metrics` | All per-example rows concatenated; adds `foldseek_cluster_id` with `--cluster_with_foldseek` |
| `per_task_metrics.csv` | `aggregate_metrics` | Per-task summary (pass rates, means, cluster counts) |
| `individual_job_results/` | `aggregate_metrics` | The original per-job CSVs, moved aside |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| No oracle / refolding columns, no error | Refolding needs the AF3 container — configure it or use `launch_evaluate.sh`; plain `[design]` metrics need no container |
| `metrics_tags` metric silently skipped | Tags are matched by set intersection; pass the exact tag string a metric declares (design vs refolding are separate namespaces) |
| `foldseek` clustering does nothing | Set `FOLDSEEK_EXEC`; for generation-time aggregation also set `save_chain_of_interest=true` before generation |
| `out_dir` missing / config error | `out_dir` is mandatory for `evaluate.py`; there is no run dir to infer it from |
| Hydra "could not override" / arg ignored | Use `key=value`, not `--key value`; quote list values as `metrics_tags='[design]'` |
| Only job CSVs present, no aggregate | Run `python -m rfproteina.inference_utils.aggregate_metrics <metrics_dir>` after all jobs finish |

For deeper detail: [metrics reference](references/metrics.md) ·
[docs/workflow/metrics.md](references/upstream-sources.md) ·
[docs/workflow/custom-metrics.md](references/upstream-sources.md) ·
[Evaluating Results](references/upstream-sources.md).

## Limitations

Missing refolding columns mean unmeasured results. Metric and pass-rate interpretations depend on the exact model revision, providers, and criteria configuration.

## Examples

The Step 1 command scores existing CIFs with the `design` tag. Steps 2 and 3 show aggregation with and without FoldSeek; choose the requested operation and a fresh result destination.

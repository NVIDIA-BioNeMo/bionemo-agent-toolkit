---
name: rfd4-proteina-generate
description: >
  Run RFD4-Proteina (RFD4-Proteina) single-shot generation across every design
  task — the scientific anchor of the skill set. Reach for this skill for "design
  a protein", "generate a monomer", "run rfproteina inference", "scaffold a
  motif", "design an enzyme", "design a small molecule binder", "design a
  protein binder", "design a DNA binder", "fold / inverse-fold this backbone",
  "partial diffusion", "refine this structure", "make my designs more diverse",
  "deterministic (ODE) sampling", or "compute refolding metrics inline". It first
  runs the setup preflight, then routes by design case to the right benchmark
  example + overrides, and drives `rfd4-generate`. It hands off to
  rfd4-proteina-annotated-cif to build or edit an annotated CIF, to
  rfd4-proteina-search for reward-guided / beam search, and to rfd4-proteina-evaluate
  for deep metric analysis (the AF3 oracle).
license: See the RFD4-Proteina repository (Baker Lab x NVIDIA collaboration)
---

# RFD4-Proteina Generate

Single-shot generation for RFD4-Proteina. One entry point drives every design task —
unconditional monomers/complexes, folding & inverse folding, motif scaffolding,
enzyme design, small-molecule binders, protein binders, and DNA binders. The
skill's job is to **route** the request to the right example input and the right
overrides, then run one command. Deep input construction, reward-guided search,
and oracle metrics live in sibling skills; this skill points at them.

Run everything from the repository root (the directory containing `.project-root`). All model arguments
are Hydra `key=value`, **never** `--key value`.

## Step 1 — Preflight

Never launch a long run against a broken environment. Confirm venv, GPU, and
checkpoints first:

```bash
bash skills/rfd4-proteina-setup/scripts/preflight.sh
```

Fix every `FAIL` (see **rfd4-proteina-setup**) before generating.
`scripts/download_assets.sh` fetches the release pair composed by
`configs/inference.yaml`, so the default run needs no checkpoint override.

## Step 2 — Route the task

Pick the design case, then open its reference for the exact command, example
input, task-specific overrides, and gotchas:

| Design task | Example input(s) in `data/benchmarks/` | Reference |
| --- | --- | --- |
| Unconditional monomer | `monomer`, `adherence/monomer_helical`, `adherence/monomer_ig` | [tasks/unconditional.md](references/tasks/unconditional.md) |
| Folding / inverse folding | annotated CIF (backbone-only vs `C_SEQ`) | [tasks/folding-inverse.md](references/tasks/folding-inverse.md) |
| Motif scaffolding | `motif_scaffolding/motif_indexed`, `motif_scaffolding/motif_unindexed`, `motif_scaffolding/motif_indexed_internal_coords` | [tasks/motif.md](references/tasks/motif.md) |
| Enzyme design (active site) | `mcsa/mcsa_37`, `mcsa/mcsa_37_fixed_ligand`, `mcsa/mcsa_37_no_ligand` | [tasks/enzyme.md](references/tasks/enzyme.md) |
| Small-molecule binder | `small_molecule_binder/sm_binder`, `small_molecule_binder/SAM_hbonds.cif` | [tasks/sm-binder.md](references/tasks/sm-binder.md) |
| Protein binder | `ppi/ppi_all_atom/` | [tasks/protein-binder.md](references/tasks/protein-binder.md) |
| DNA binder | `dna_binder/dna_binder_denovo_val` | [tasks/dna-binder.md](references/tasks/dna-binder.md) |

**Need an input the request doesn't have?** Annotated CIF is the recommended,
lossless format. When the task needs coordinate/sequence conditioning, hotspots,
fixed ligands, H-bonds, RASA, or unindexed motifs, **hand off to
rfd4-proteina-annotated-cif** to build and validate the CIF, then come back and
pass it via `inputs=<file>.cif`.

## Step 3 — Run

General form:

```bash
rfd4-generate inputs=<file> num_replicates=<N> out_dir=<dir> [overrides...]
```

Use the Python environment activated during setup. The installed command runs
in that environment; see the [installation guide](../../docs/installation.rst)
for environment and scheduler settings.

**The four parameters you almost always set** (defaults are only right for a
smoke test):

| Parameter | What to set it to | Default |
| --- | --- | --- |
| `out_dir` | a real output path | `./runs/<run_name>` |
| `num_replicates` | designs per example (e.g. 8-80); `1` is a smoke test | 1 |
| `batch_size` | start at 8, but first confirm the longest input fits at `batch_size=1` | 1 |
| `metrics_tags` | inline metrics as a bracket-quoted Hydra list; only refolding tags need a container | `[]` |

Useful extras: `subset_to_examples=monomer-short` (run only named keys),
`seed=<int>` (reproducibility), `skip_existing=true` (resume a run),
`save_chain_of_interest=true` (required for later foldseek clustering).

```bash
# 80 designs of each monomer example, 8 at a time
rfd4-generate \
    inputs=data/benchmarks/monomer \
    num_replicates=80 batch_size=8 out_dir=./runs/monomers
```

## Scheduler intent

For any batch run, read the selected `scripts/.user_info_<cluster>` and the
launcher before constructing the command. Preserve the user's partition,
account, QoS/priority options, GPU request, runtime, memory, and CPU settings.
Use a resource override only when the user explicitly requested it. State the
resolved scheduler values before submission; use dry-run or non-submitting tests
when validating the workflow.

## Step 4 — Pick your overrides

Full cheat sheet: [references/overrides.md](references/overrides.md). The knobs
that matter most:

- **Temperature / diversity.** Use
  `generation.model.bb_ca.simulation_step_params.tsr_k` (default 16) and
  `generation.model.local_latents.simulation_step_params.tsr_k` (default 4).
  Higher `k` lowers temperature; lower `k` raises it. `tsr_sigma` provides secondary
  control over when sharpening takes effect (defaults: backbone 3, latent 12).
- **Partial diffusion (refine an existing structure).** Simple:
  `generation.args.partial_trajectory_fraction_steps=<f>` (fraction of `nsteps`).
  Advanced: `generation.args.partial_t_backbone=<t>` /
  `generation.args.partial_t_latent=<t>` (floats in `(0,1)`; near 1 stays close
  to the input, near 0 approaches full generation), optionally
  `generation.args.couple_partial_t=true`. `partial_t` is a corruption level, not
  Angstroms.
- **Deterministic (ODE) sampling** (no mid-trajectory noise):
  `generation.model.bb_ca.gt.mode=ode generation.model.local_latents.gt.mode=ode`.
- **Steps / recycling.** The default 1x schedule uses 60 model evaluations
  and 185 trunk passes, with twice the integration-step density in the final 20%
  of each modality's clock. Select `recycle_strategy=thinking_high` for the
  1.5x recycle-depth variant.

## Step 5 — Inline metrics (optional)

Pass `metrics_tags='[...]'` to compute metrics right after each design; results
land in `per_example_metrics.csv` alongside the CIFs. Common tags include `design`, `unconditional_refolding`, `ppi_refolding`,
`dna_refolding`, `motif_scaffold_refolding`, `sm_binder_refolding`,
`ame_refolding`, `disco_refolding`, `hotspot_conditioning`,
`3d_coordinate_conditioning`, `rasa_conditioning`, and
`interchain_interactions`. Check `docs/how-to/evaluate-with-metrics.md` and the composed
metric configs before treating any list as exhaustive.

> [!NOTE]
> Every `*_refolding` tag runs the **AF3 oracle**, which needs an apptainer/docker
> container (see **rfd4-proteina-setup** for the container, **rfd4-proteina-evaluate**
> for what the metrics mean and how to read them). Plain generation needs no
> container. Deep metric detail belongs to **rfd4-proteina-evaluate** — this skill
> only turns the tags on.

```bash
rfd4-generate \
    inputs=data/benchmarks/monomer num_replicates=50 batch_size=8 \
    out_dir=./runs/monomers_scored metrics_tags='[unconditional_refolding]'
```

## Reward-guided / beam search

For "generate many, keep the best under an AF3 reward", do **not** hand-roll it
here — use **rfd4-proteina-search**, which drives
`configs/inference_experiment/inference_beam_example.yaml` and the search config
knobs (beam width, branching, checkpoints, metric weights).

## Reusable configs

For a repeatable experiment instead of one-off CLI overrides, copy
`configs/inference_experiment/TEMPLATE.yaml` — it documents the three ways to run
(in-tree experiment config, CLI overrides, config file anywhere on the
filesystem). The default group is `inference_on_user_inputs`.

## Outputs

Each design is an **annotated CIF** with per-atom provenance columns (`SA_SRC`,
`SA_CRDSRC`, `SA_IDXGRPSRC`, `SA_UII`) tying output atoms back to the input spec.
With metrics on, a `per_example_metrics.csv` is written alongside. Full column
table and how to read annotations: [references/outputs.md](references/outputs.md).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Out of memory | Lower `batch_size`; confirm your longest input fits at `batch_size=1` first |
| `--inputs`/`--out_dir` not recognized / Hydra config error | Use `=` not `--`: `inputs=file.cif`, never `--inputs file.cif` |
| checkpoint not found | Confirm `DATA_PATH`, then compare `ckpt_name` and `ckpt_path` with `configs/inference.yaml`; override only when intentionally using another checkpoint |
| `DATA_PATH` / checkpoint not found | `export DATA_PATH=...` then `./scripts/download_assets.sh "$DATA_PATH"` |
| `atomworks not found` | Re-run `make setup` to install the public AtomWorks dependency |
| `hydra not found` / import errors | `source .venv/bin/activate` |
| `No .env file found for cluster '<name>'` | `export CLUSTER=local` and create `.env.local` |
| AF3 / `*_refolding` errors | Refolding metrics need an AF3 container — see rfd4-proteina-setup + rfd4-proteina-evaluate |
| Segfault in rdkit/posebusters | uv's Python needs `LD_PRELOAD` set to the bundled `libstdc++.so.6` (see `Makefile`) |

For deeper detail: [overrides](references/overrides.md) ·
[outputs](references/outputs.md) · per-task guides under
[references/tasks/](references/tasks/).

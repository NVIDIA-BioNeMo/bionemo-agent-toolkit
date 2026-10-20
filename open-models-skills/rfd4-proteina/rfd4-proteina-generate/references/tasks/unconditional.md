# Unconditional generation

Generate novel protein structures (and multi-chain complexes) from scratch — no
motif, no ligand, no target. Back to the [skill](../../SKILL.md).

## Example inputs (`data/benchmarks/`)

| File | Keys | What it is |
| --- | --- | --- |
| `monomer` | `monomer-short` (100), `monomer-medium` (150), `monomer-long` (250) | Plain single-chain monomers by length |
| `adherence/monomer_helical` | `monomer-short/medium/long` | Monomers conditioned on CAT mainly-alpha class `1.x.x` |
| `adherence/monomer_ig` | `monomer-short` | Monomer conditioned on immunoglobulin CAT topology `2.60.40` |

## Run

```bash
# Smoke test: one short monomer
rfd4-generate \
    inputs=data/benchmarks/monomer subset_to_examples=monomer-short \
    num_replicates=1 out_dir=./runs/uncond_smoke

# Real run: 80 designs of each monomer example, 8 at a time
rfd4-generate \
    inputs=data/benchmarks/monomer \
    num_replicates=80 batch_size=8 out_dir=./runs/monomers
```

## Task-specific overrides & metrics

- **Temperature / diversity.** Sweep
  `generation.model.bb_ca.simulation_step_params.tsr_k` (default 16) and
  `generation.model.local_latents.simulation_step_params.tsr_k` (default 4).
  Lower `k` raises temperature. Use `tsr_sigma` as a secondary schedule control
  (see [overrides](../overrides.md)).
- **Metrics.** `metrics_tags='[unconditional_refolding]'` for AF3 refolding +
  pLDDT/scRMSD (needs an AF3 container — see **rfd4-proteina-evaluate**).
- **Length** is defined by the input. Use **rfd4-proteina-annotated-cif** to
  create an input with the requested length or expandable segments.

## Gotchas

- `batch_size=8` is a good start, but the longest example (`monomer-long`, 250
  residues) should be confirmed at `batch_size=1` first.

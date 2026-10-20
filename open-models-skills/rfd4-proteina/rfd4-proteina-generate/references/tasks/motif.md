# Motif scaffolding

Build a complete protein around one or more structural motifs. A motif is
residues carrying **both** coordinate (`C_CRD`) and sequence (`C_SEQ`)
conditioning; the model designs the surrounding scaffold. Back to the
[skill](../../SKILL.md).

## Example inputs (`data/benchmarks/`)

| File | Notes |
| --- | --- |
| `motif_scaffolding/motif_indexed` | Indexed-motif variants (keys like `1PRW_AA`, `1BCF_AA`, `1YCR_AA`) |
| `motif_scaffolding/motif_unindexed` | Unindexed-motif variants (model chooses chain position) |
| `motif_scaffolding/motif_indexed_internal_coords` | Internal-coordinate groups (motif's internal geometry without fixing where it sits) |

## Run

```bash
# One indexed motif-scaffold task
rfd4-generate \
    inputs=data/benchmarks/motif_scaffolding/motif_indexed \
    subset_to_examples=1PRW_AA \
    num_replicates=8 batch_size=8 out_dir=./runs/motif \
    metrics_tags='[motif_scaffold_refolding,3d_coordinate_conditioning]'
```

## Task-specific overrides & metrics

- **`motif_scaffold_refolding`** — AF3 refolding + motif RMSD.
- **`3d_coordinate_conditioning`** — coordinate RMSD of the conditioned motif.
- Both refolding tags need the AF3 container (see **rfd4-proteina-evaluate**); plain
  scaffolding (no tags) needs none.
- **Indexed vs unindexed** is a property of the input, not a CLI flag: indexed
  pins the motif to a chain position; unindexed lets the model place it. Choose
  when building the input.

## Gotchas

- **Length ranges are re-rolled per design.** `"180-180"` is degenerate (one
  length); a real range like `"150-350"` resamples length each replicate — the
  motif residues are *not* subtracted from the count.
- Building a new motif input (which atoms to fix, index vs unindex, internal
  coordinate groups) is exactly what **rfd4-proteina-annotated-cif** is for.

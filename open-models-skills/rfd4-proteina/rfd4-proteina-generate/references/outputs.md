# Outputs

What a generation run writes and how to read it. Back to the [skill](../SKILL.md).

Everything lands under `out_dir` (default `./runs/<run_name>`):

- **Annotated CIFs** — one per design, the primary artifact.
- **`per_example_metrics.csv`** — only when `metrics_tags` is set (one row per
  design, columns per metric; job-parallel runs write
  `per_example_metrics_job{N}.csv`).
- **Per-design chain-of-interest CIFs** — only when `save_chain_of_interest=true`
  (needed for foldseek clustering).

## Annotated-CIF provenance columns

Each output design is a CIF whose `_atom_site` loop carries extra columns
recording how each atom was produced, so any CIF reader can pick them up. The
Python aliases live in `rfproteina.utils.standard_annotations`.

| Accessor | CIF column / key | Description |
| --- | --- | --- |
| `SA_SRC` | `annotation_src-component_1_atom` | Which part of the input spec the atom originated from (`.` if unassigned) |
| `SA_CRDSRC.annotation(...)` | `annotation_src-coordinate-conditioned-region_1_atom` | Which input motif region provided each atom's coordinate conditioning (`.` if none) |
| `SA_IDXGRPSRC` | `annotation_src-index-group_1_atom` | Original unindexed `IndexGroup` of a mapped motif token (`-1` if none) |
| `SA_UII` | `is_unindexed_insertion` | `True` for atoms corresponding to an unindexed input motif |

The aligned motif coordinates themselves are written as a separate
`_annotation_coords-with-insertion_1_atom` loop (accessor `SA_CWI`), not an
`_atom_site` column, but are accessible analogously to any other
`StandardAnnotation`.

## Reading annotations in Python

```python
import rfproteina.conditions  # noqa: F401 -- REQUIRED registry side-effect; do this FIRST
from rfproteina.utils.standard_annotations import SA_SRC, SA_CRDSRC, SA_UII
# ... parse the output CIF into an AtomArray with your usual atomworks/biotite reader ...

crd_mask = SA_CRDSRC.mask(atom_array)       # derived from non-"." source labels
src_labels = SA_SRC.annotation(atom_array)  # which input component each atom came from
```

> The **import-order landmine** from **rfd4-proteina-annotated-cif** applies here too:
> `import rfproteina.conditions` must run before parsing, or every rfproteina
> annotation column is silently dropped on read.

These provenance columns map output atoms back to the exact input regions you
defined when building the annotated CIF (via **rfd4-proteina-annotated-cif**) — e.g. which
atoms are your fixed motif, which are unindexed insertions, which came from a
coordinate group.

## per_example_metrics.csv

Written when `metrics_tags` is set. One row per design; columns depend on the
tags used (e.g. pLDDT / scRMSD from `unconditional_refolding`, motif RMSD from
`motif_scaffold_refolding`, interface metrics from `ppi_refolding`). Custom
metrics are prefixed by their config name (e.g. `residue_count.n_residues`). When
foldseek clustering is run, a `foldseek_cluster_id` and `chain_of_interest`
column are added.

For aggregating multi-job runs and the full metrics catalog, see
**rfd4-proteina-evaluate** and `docs/how-to/evaluate-with-metrics.md`.

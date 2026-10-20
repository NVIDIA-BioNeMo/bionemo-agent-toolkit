# Small-molecule binder design

Design a protein that binds a small-molecule ligand. The input must contain the
ligand; the model designs a protein pocket around it. Back to the
[skill](../../SKILL.md).

## Example inputs (`data/benchmarks/`)

| File | Keys | Notes |
| --- | --- | --- |
| `small_molecule_binder/sm_binder` | `FAD`, `IAI`, `OQO`, `SAM` | Ligand named via `ligand`, `contig` 150, `select_fixed_atoms: false` (model invents pose/conformer) |
| `small_molecule_binder/SAM_hbonds.cif` | `SAM_hbonds` | Adds H-bond donor/acceptor conditioning to SAM |

## Run

```bash
# One small-molecule binder target
rfd4-generate \
    inputs=data/benchmarks/small_molecule_binder/sm_binder \
    subset_to_examples=SAM \
    num_replicates=8 batch_size=8 out_dir=./runs/sm_binder \
    metrics_tags='[sm_binder_refolding,interchain_interactions]'
```

## Task-specific overrides & metrics

- **`sm_binder_refolding`** — AF3 refolding + binding metrics.
- **`interchain_interactions`** — H-bond / pi-stack / salt-bridge etc. adherence
  and counts; use the `SAM_hbonds.cif` input to score H-bond adherence to SAM.
- Refolding tags need the AF3 container (see **rfd4-proteina-evaluate**).

## Gotchas

- **The ligand must be in the input** — this task cannot be run from a bare
  length spec. Use the ligand-carrying benchmarks or build an annotated CIF with
  the ligand via **rfd4-proteina-annotated-cif**.
- Without ligand coordinate conditioning, the model generates both the pose
  and the conformer. Confirm that is intended; build a fixed-pose input with
  **rfd4-proteina-annotated-cif** when the ligand should stay put.
- PDB-derived ligands frequently arrive with wrong bond orders / missing charges;
  validate with **rfd4-proteina-annotated-cif** before committing compute.

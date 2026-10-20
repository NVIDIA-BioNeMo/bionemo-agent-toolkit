# Python authoring workflow

Use this reference when creating or modifying an annotated CIF. Source of truth:
[Python API tutorial](../../../docs/examples/python_api_tutorial.ipynb),
[input documentation](../../../docs/how-to/input_prep/index.md), and
[parse presets](../../../src/rfproteina/utils/parse_presets.py).

## Pick the parser deliberately

| Input | Python preset | Behavior that matters |
| --- | --- | --- |
| Existing annotated CIF | `ANNOTATED_CIF` | Loads saved `StandardAnnotation` conditions and makes minimal structural changes |
| Raw RCSB mmCIF | `RCSB_WITH_METALS` | Prepares an RCSB entry, adds missing atoms, reads covalent/metal `struct_conn`, removes configured waters/aids, and applies cleanup |
| Cleaned or predicted unannotated structure | `DISTILLATION` | Does not add missing atoms or perform the more destructive RCSB cleanup |

`ANNOTATED_CIF` preserves existing conditions by loading standard annotations
without rebuilding the structure.

For `.pdb`, establish provenance before choosing between RCSB preparation and
distillation. See [chemistry review](validation.md#chemistry-and-component-completeness).
If provenance changes the parser choice and cannot be inferred, ask whether the
input is raw, cleaned, or already annotated. Report parser preprocessing,
including missing-atom addition, water/aid removal, MSE conversion, and altloc
selection when applicable.

Import `rfproteina.conditions` before parsing any annotated CIF to register its
condition classes; otherwise RFProteina-specific columns can be lost.

## Load and edit a benchmark target

```python
from pathlib import Path

import rfproteina.conditions  # noqa: F401  -- register before parse
import numpy as np
from atomworks.io import parse
from atomworks.io.utils.annotator import ensure_annotations
from atomworks.io.utils.atom_array_plus import as_atom_array_plus
from atomworks.ml.conditions import C_CRD, C_IDX, C_SEQ
from rfproteina.conditions import C_HOT
from rfproteina.utils.parse_presets import RCSB_WITH_METALS

input_path = Path("input.cif")
output_path = Path("annotated.cif")

parsed = parse(str(input_path), config=RCSB_WITH_METALS)
aa = as_atom_array_plus(parsed["assemblies"]["1"][0])

ensure_annotations(aa, "is_protein", "is_ligand")
target = aa.chain_id == "A"
target_backbone = (
    target & aa.is_protein
    & np.isin(aa.atom_name, ["N", "CA", "C", "O"])
    & np.isfinite(aa.coord).all(axis=1)
)

assert target.any(), "Target chain A matched no atoms"
assert target_backbone.any(), "Target chain A has no protein backbone atoms"

# Benchmark BB-only fixes target identity and resolved backbone coordinates.
C_CRD.set_annotation_from_ground_truth(aa, target_backbone)
C_SEQ.set_annotation_from_ground_truth(aa, target | aa.is_ligand)

# Mark atoms on the target that a generated binder should contact.
hotspots = target & np.isin(aa.res_id, [35, 38, 42])
C_HOT.set_annotation(aa, hotspots)

# C_IDX is all-on by default. This explicit call keeps all residues indexed.
C_IDX.set_annotation(aa, np.ones(aa.array_length(), dtype=bool))
```

For explicit target-sequence redesign, use the
[selection example](annotators-and-selections.md#backbone-conditioning).
The assembly key above is an example, not a default to apply blindly. Inspect
the parsed assemblies and select the biological assembly the user intends. Also
record model and alternate-location choices when the source contains options.

`set_annotation_from_ground_truth()` and `set_annotation()` replace that condition's stored array. For
an additive edit to an existing annotated CIF, start from the current value:

```python
from rfproteina.transforms.utils.conditioning_utils import set_absolute_coordinate_conditioning

set_absolute_coordinate_conditioning(aa, np.flatnonzero(target_backbone), True)

known = C_SEQ.annotation(aa, default="generate").copy()
selected = target | aa.is_ligand
known[selected] = C_SEQ.ground_truth_value(aa)[selected]
C_SEQ.set_annotation(aa, known)
```

Start from a fresh default only when authoring a new condition or intentionally
resetting an old one.

Use `chain_iid` instead of `chain_id` when an assembly contains multiple
instances of the same source chain. Inspect unique values before selecting:

```python
print("chain_id:", np.unique(aa.chain_id))
if "chain_iid" in aa.get_annotation_categories():
    print("chain_iid:", np.unique(aa.chain_iid))
```

## Value-valued conditions

Boolean conditions use `set_annotation()`. Enum or coordinate-valued conditions use
`default_annotation()`/`annotation()` followed by `set_annotation()`:

```python
from rfproteina.conditions import C_HB, HBondEnum

ensure_annotations(aa, "is_ligand")
hbond = C_HB.default_annotation(aa).copy()
hbond[aa.is_ligand & (aa.atom_name == "N1")] = HBondEnum.DONOR
hbond[aa.is_ligand & (aa.atom_name == "O1")] = HBondEnum.ACCEPTOR
C_HB.set_annotation(aa, hbond.astype(int))
```

For an existing annotation, prefer
`C_HB.annotation(aa, default="generate").copy()` so unrelated authored values
are preserved.

For fold (CAT) conditioning, use the dedicated helper rather than writing the
`C_CATH` annotation directly — it preserves the internal `C.A.T.x` format and
prevents string truncation:

```python
from rfproteina.utils.condition_resolution import set_cath_condition

set_cath_condition(aa, np.flatnonzero(aa.chain_id == "A"), "2.60.40")
# Clear fold conditioning on that chain:
set_cath_condition(aa, np.flatnonzero(aa.chain_id == "A"), "x.x.x")
```

## Expandable segments

Insert a variable-length polypeptide sentinel with AtomWorks. Insertions into an
existing chain must occur at a residue boundary:

```python
from atomworks.ml.utils.expandable_segment import insert_expandable_segment

ensure_annotations(aa, "is_res_start")
anchor = np.flatnonzero(
    (aa.chain_id == "A") & (aa.res_id == 50) & aa.is_res_start
)
assert len(anchor) == 1, f"Expected one residue-start anchor, got {len(anchor)}"

aa = insert_expandable_segment(
    aa,
    seg_min=20,
    seg_max=40,
    atom_idx=int(anchor[0]),
    insert_before=True,
    new_chain=False,
)
```

To add a new design chain:

```python
from atomworks.enums import ChainType

aa = insert_expandable_segment(
    aa,
    seg_min=80,
    seg_max=120,
    new_chain=True,
    new_chain_id="B",
    new_chain_type=ChainType.POLYPEPTIDE_L,
)
```

Choose the representation using the task and workspace policy:

- **Source template:** retain collapsed sentinels when lengths should be sampled
  independently for each design.
- **Sampled child or fixed-length benchmark input:** materialization with
  `realize_expandable_segments()` is intentional when a concrete sampled length
  is required. Save a distinct child as required by the workspace, retaining
  source provenance and the sampled lengths/seed. Its length will not resample.

Read the canonical [expandable-segment semantics](../../../docs/concepts/conditioning.md#expandable-segments)
before choosing index conditioning: an unindexed segment samples residue-index
spacing, not additional conditioning tokens. Follow that documentation for its
flanking residues and index group; check the installed implementation supports
this behavior before authoring a task that depends on it.

## Unindex residues

Apply the [indexing rules](validation.md#indexing-and-grouping) before editing.
For two disconnected motif residues requested as independent islands:

```python
from atomworks.io.utils.standard_annotations import S_ATM
from rfproteina.conditions import C_IDXGRP
from rfproteina.conditions_reporting import sync_index_groups

island_57 = (aa.chain_id == "A") & (aa.res_id == 57)
island_102 = (aa.chain_id == "A") & (aa.res_id == 102)
islands = [island_57, island_102]
to_unindex = np.logical_or.reduce(islands)

atomized = S_ATM.mask(aa, default="generate")
if (to_unindex & atomized).any():
    raise ValueError("Atomized tokens cannot be unindexed")

indexed = C_IDX.mask(aa, default="generate").copy()
indexed[to_unindex] = False
C_IDX.set_annotation(aa, indexed)

# Retain intentional subdivisions while synchronizing mandatory boundaries.
sync_index_groups(aa, preserve_manual_edits=True)

groups = C_IDXGRP.annotation(aa, default="generate").copy()
next_group = int(groups.max()) + 1
for island in islands:
    groups[island] = next_group
    next_group += 1
C_IDXGRP.set_annotation(aa, groups)

# Fast authoring assertions; the full pipeline validation still runs later.
assert C_IDX.mask(aa, default="raise")[atomized].all()
for group_id in np.unique(groups):
    group_indexed = C_IDX.mask(aa, default="raise")[groups == group_id]
    assert np.all(group_indexed == group_indexed[0]), (
        f"Index group {group_id} mixes indexed and unindexed atoms"
    )
```

Call `sync_index_groups()` after changing the Index condition, as shown above.

## Combine annotated CIFs / AtomArrays

Multiple annotated CIFs can be loaded as `AtomArrayPlus` objects and combined.
Use AtomWorks' `concatenate_atom_array_plus()`; do not use plain Biotite
concatenation or Python `+`, which can lose `AtomArrayPlus` state. Resolve chain-ID
collisions and refresh chain-derived annotations when combining structures.

For a programmatic combination:

```python
from atomworks.io.transforms.atom_array import (
    add_id_and_entity_annotations,
    add_iid_annotations,
)
from atomworks.io.utils.atom_array_plus import concatenate_atom_array_plus
from rfproteina.conditions_reporting import sync_index_groups

# Each entry was parsed with ANNOTATED_CIF and converted with
# as_atom_array_plus(). Make chain_id values unique before concatenating.
arrays = [target_aa, motif_aa]
chain_sets = [set(map(str, np.unique(arr.chain_id))) for arr in arrays]
for i, left in enumerate(chain_sets):
    for right in chain_sets[i + 1 :]:
        overlap = left & right
        if overlap:
            raise ValueError(f"Rename colliding chain IDs before combine: {overlap}")

# concatenate_atom_array_plus retains only annotations present in every input.
# Materialize defaults for every condition column present in any input so an
# unset condition in one file does not cause an authored condition to disappear.
condition_columns = {
    name
    for arr in arrays
    for name in arr.get_annotation_categories()
    if name.startswith(("mask_", "condition_"))
}
for arr in arrays:
    ensure_annotations(arr, *condition_columns)

combined = concatenate_atom_array_plus(arrays)

# Re-derive IDs over the merged structure and synchronize index groups.
combined = add_id_and_entity_annotations(combined, overwrite=True)
combined = add_iid_annotations(combined, overwrite=True)
sync_index_groups(combined, preserve_manual_edits=True)
```

The low-level concatenator preserves bonds within each input and merges custom
CCD registries, rejecting conflicting definitions for the same residue code. It
does not infer bonds between inputs. Add an inter-array covalent or coordination
bond only when explicitly intended and chemically specified.

Only 2D annotation categories present in all inputs survive concatenation. If a
material pairwise annotation exists in only one input, decide how to initialize
it on the others before combining. After combination, inspect renamed/unique
chains, molecule IDs, `C_IDX`, and `C_IDXGRP`, then run the normal pre-save
checks.

## Validate and save

Complete the [validation and round-trip procedure](validation.md) on the edited
array before handing off the CIF.

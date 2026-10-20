# AtomWorks annotators and selections

Use this reference when translating structural intent into an atom mask.

## Check installed annotation support

The implementation and lazy registry live in
[annotator.py](upstream-sources.md#annotation-registries-and-validation).
`ensure_annotations()` mutates the array in place, retaining existing annotations
and computing missing dependencies. If a name is absent from `ANNOTATOR_REGISTRY`,
its `_resolve_standard_annotation()` fallback matches canonical names or aliases
in the [StandardAnnotation registry](upstream-sources.md#conditions-and-interactions).
Import RFProteína conditions before using that fallback.

Inspect these installed registries instead of relying on a copied catalog:

```python
import rfproteina.conditions  # noqa: F401
from atomworks.io.utils.annotator import ANNOTATOR_REGISTRY, ensure_annotations
from atomworks.io.utils.selection import get_annotation_categories
from atomworks.io.utils.standard_annotations.base import STANDARD_ANNOTATIONS

requested = {"is_protein", "is_ligand"}
standard_names = {
    name
    for annotation in STANDARD_ANNOTATIONS
    for name in (annotation.full_name, *annotation.aliases)
}
available = (
    set(get_annotation_categories(aa, n_body="all"))
    | set(ANNOTATOR_REGISTRY)
    | standard_names
)
unsupported = requested - available
if unsupported:
    raise ValueError(f"Unsupported annotation names in installed AtomWorks: {sorted(unsupported)}")
ensure_annotations(aa, *sorted(requested))
```

If generation itself fails, report the requested name and underlying error;
do not silently substitute another annotation or an all-false mask. Standard
annotation defaults are not evidence that the model consumes the condition;
consult the [condition reference](upstream-sources.md#conditions-and-interactions).

## Backbone conditioning

`is_protein_backbone` includes `OXT`. For RFProteína backbone-only coordinate
conditioning, select exactly `N`, `CA`, `C`, and `O`, and require finite xyz:

```python
import numpy as np
from atomworks.ml.conditions import C_CRD, C_SEQ

ensure_annotations(aa, "is_protein")
target = aa.chain_id == "A"
target_backbone = (
    target & aa.is_protein
    & np.isin(aa.atom_name, ["N", "CA", "C", "O"])
    & np.isfinite(aa.coord).all(axis=1)
)
print("target atoms", int(target.sum()))
print("resolved target backbone atoms", int(target_backbone.sum()))
assert target_backbone.any(), "No resolved target backbone atoms selected"

from rfproteina.transforms.utils.conditioning_utils import set_absolute_coordinate_conditioning

set_absolute_coordinate_conditioning(aa, np.flatnonzero(target), False)
set_absolute_coordinate_conditioning(aa, np.flatnonzero(target_backbone), True)
```

Sequence intent is independent. For benchmark **BB-only** mode, keep target
sequence conditioning enabled over the entire target, including unresolved atoms:

```python
known = C_SEQ.annotation(aa, default="generate").copy()
known[target] = C_SEQ.ground_truth_value(aa)[target]
C_SEQ.set_annotation(aa, known)
```

Only when the request explicitly calls for target-sequence redesign, set
`known[target] = C_SEQ.default_annotation(aa)[target]` instead, after checking the
[interaction rules](upstream-sources.md#conditions-and-interactions)
for other conditions on that target. Outside-target conditions remain unchanged.

## AtomWorks query syntax

AtomWorks adds `mask()`, `query()`, and `idxs()` methods to Biotite atom arrays.
Only annotations already present on the array are visible to the expression:

```python
ensure_annotations(aa, "is_ligand")

ligand_oxygens = aa.mask("is_ligand & (element == 'O')")
resolved = np.isfinite(aa.coord).all(axis=1)
bonded_target = aa.mask("has_bonds() & (chain_id == 'A')")
ca_idxs = aa.idxs("(chain_id == 'A') & (atom_name == 'CA')")
ligand = aa.query("is_ligand")
```

The path-selection DSL is available through `sel()` inside expressions:

```python
motif = aa.mask("sel('A/*/[35-42]')")
functional_atoms = aa.mask("sel('A/HIS/57/[ND1,NE2]')")
```

Use parentheses around comparisons joined with `&`, `|`, or `~`. Prefer
`chain_iid` when assemblies contain repeated instances. Print residue and atom
identities for small functional selections; a nonzero count alone does not prove
the intended atoms were selected. Condition APIs accept atom-length arrays;
respect the residue/token levels in the canonical condition reference when
spreading a selection.

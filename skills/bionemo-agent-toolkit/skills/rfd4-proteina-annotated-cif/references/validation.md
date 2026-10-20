# Annotated-CIF validation

Use this reference before accepting a newly authored or modified annotated CIF.
The [condition documentation](../../../docs/concepts/conditioning.md#conditions-are-not-independent),
and [reporting checks](../../../src/rfproteina/conditions_reporting.py) define the
invariants. Run the checked-out implementation and report unsupported conditions
rather than silently dropping them.

## Saved CIF checks

Run these helpers from the repository root:

```bash
bash skills/rfd4-proteina-annotated-cif/scripts/inspect_cif.sh input.cif
bash skills/rfd4-proteina-annotated-cif/scripts/check_annotated_cif.sh input.cif
```

The inspector reports structure, chemistry, conditions, and expandable segments.
The checker runs pipeline validation and checks selected coordinates, sequence/index
consistency, missing atoms, unknown formal charges, ligand bond orders, metal bonds,
component-name collisions, and declared covalent connections. It reports findings
without repairing the input. `--strict` also fails on warnings; `--quiet` limits
output to findings and the verdict. `--skip_pipeline` omits the pipeline check and
must not be reported as full validation.

Chemistry warnings require intent review: these checks cannot establish whether a
ligand pose, metal coordination, or unusual component is scientifically appropriate.

## Chemistry and component completeness

Read the canonical [charges and bonds guidance](../../../docs/reference/annotations.md#charges-and-bonds)
for chemistry consumed by the model and aromatic bond representation.

- Preserve authored bonds, formal charges, and atom identities. Do not infer
  missing chemistry or add metal coordination without specified partners.
- PDB often lacks the bond orders, charges, aromaticity, and connectivity needed
  for ligand/metal fidelity. Prefer source mmCIF and visually review
  bonds and charges when chemistry is uncertain.
- Express tip-atom conditioning with masks on a complete residue, not by deleting
  unconditioned atoms. Review unresolved polymer atoms and parser preparation.
- A known CCD code with a different heavy-atom inventory needs review: determine
  whether it is unresolved or an intentionally authored custom component.
  Non-CCD components are valid when their explicit atoms, bonds, bond orders,
  aromaticity, and formal charges are complete and intentional.

## Indexing and grouping

- `C_IDX` defaults on. When unindexing, change whole non-atomized residues and
  synchronize `C_IDXGRP`; atomized tokens must remain indexed.
- No index group may mix indexed and unindexed residues. Indexed atoms in one
  covalent molecule must share an index group.
- A peptide-connected unindexed stretch can share a group. Disconnected islands
  use separate groups for independent placement, or share a group when their
  relative sequence offsets are intentionally tied. Use the bond graph to
  determine connectivity, not residue-number adjacency.
- Review residue-ID gaps within each group. Preserve intentional offsets,
  including [sampled unindexed-segment spacing](../../../docs/concepts/conditioning.md#expandable-segments),
  rather than renumbering them to satisfy a check. If the installed validator
  rejects required semantics, report the version conflict.

The [unindexing recipe](python-authoring.md#unindex-residues) applies these rules.
Independent expandable segments do not express a coupled total-length constraint.
For materialization choices, follow the [segment workflow](python-authoring.md#expandable-segments).

## Pre-save checks

Run all three input-validation checks on the authored array:

```python
from rfproteina.conditions_reporting import (
    check_index_group_molecule_consistency,
    check_index_group_res_id_gaps,
    run_pipeline_validation,
    summarize_conditions,
)

checks = (
    run_pipeline_validation,
    check_index_group_res_id_gaps,
    check_index_group_molecule_consistency,
)
violations = [message for check in checks for message in check(aa)]
if violations:
    raise ValueError("Annotated CIF validation failed:\n" + "\n".join(violations))

print(summarize_conditions(aa))
```

The pipeline check realizes expandable segments once with a fixed seed. It
validates that realization, not every length in a range.

These checks do not establish scientific correctness of chemistry. Resolve any
conflict with the intended design before changing the structure or conditions.

## Save and round-trip

After the [registry import and parsing setup](python-authoring.md#pick-the-parser-deliberately),
save standard annotations and reload with `ANNOTATED_CIF`:

```python
from atomworks.io import parse
from atomworks.io.utils.atom_array_plus import as_atom_array_plus
from atomworks.io.utils.io_utils import to_cif_file
from rfproteina.utils.parse_presets import ANNOTATED_CIF

to_cif_file(
    aa,
    str(output_path),
    save_standard_annotations=True,
    chain_disambiguation="chain_iid",
)
reloaded = as_atom_array_plus(
    parse(str(output_path), config=ANNOTATED_CIF)["assemblies"]["1"][0]
)
roundtrip_violations = [message for check in checks for message in check(reloaded)]
if roundtrip_violations:
    raise ValueError("Round-trip validation failed:\n" + "\n".join(roundtrip_violations))
```

Compare exact selections and values for all changed conditions, aligning by atom
identity if serialization changes order; counts alone cannot establish equality.
For edits, also compare component inventories, bonds, charges, expandable ranges,
and unrequested conditions with the source. Report only checks actually run.

# Skill Card

## Description

`rfd4-proteina-annotated-cif` creates, inspects, modifies, combines, and validates RFProteina annotated CIF inputs with Python-first AtomWorks workflows. It covers parser selection, derived masks, conditions, safe unindexing, expandable segments, chemistry preservation, input-validation invariants, and save/reload validation.

This skill is for research and development only.

## Owner

RFProteina maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFProteina repository. Skill text follows the NVIDIA agent-skills documentation convention (CC-BY-4.0); repository source follows its stated source license.

## Use Case

Anyone asking about or authoring an annotated CIF for RFProteina, including coordinate/sequence/index conditioning, hotspots, RASA, H-bonds, secondary structure, internal coordinates, centroids, expandable segments, ligands, metals, PTMs, charges, and bonds.

Workspace and campaign rules govern shared inputs, length materialization, generation, and database accounting; see the [skill boundary](SKILL.md#rfproteina-annotated-cif-authoring).

## Deployment Geography for Use

Global, subject to the repository license.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None.

Depends on: a completed `rfd4-proteina-setup` (venv plus the AtomWorks package). No GPU is required to author or validate CIFs.

## Known Risks and Mitigations

Risk: Loading an annotated CIF before importing `rfproteina.conditions` can silently discard RFProteina-specific conditions.
Mitigation: The skill requires registry import before parsing and a save/reload comparison.

Risk: PDB or poorly prepared ligand inputs may lack charges, bond orders, aromaticity, or connectivity used by the model.
Mitigation: The skill flags PDB provenance, avoids inferred chemistry, and requires visual review when chemistry fidelity is uncertain.

Risk: A syntactically valid condition can violate RFProteina interaction rules or be attached at the wrong structural level.
Mitigation: The skill uses condition APIs, explicit selection counts, and all three input-validation pre-save checks.

Risk: Incorrect unindexing can mix indexed and unindexed residues in one group, unindex atomized tokens, or accidentally tie disconnected motif islands together.
Mitigation: The skill treats `C_IDX` and `C_IDXGRP` as one edit, checks `S_ATM`, synchronizes mandatory boundaries, and assigns disconnected peptide islands deliberately.

Risk: Naively concatenating independently parsed structures can collide chain, molecule, or index-group IDs or discard annotations.
Mitigation: The skill uses `concatenate_atom_array_plus()`, requires unique chain IDs, harmonizes condition columns, re-derives entity/instance IDs, and synchronizes index groups.

## References

- `docs/examples/python_api_tutorial.ipynb`
- `docs/how-to/input_prep/index.md`
- `src/rfproteina/utils/parse_presets.py`
- `src/rfproteina/conditions_reporting.py`
- `skills/rfd4-proteina-annotated-cif/references/validation.md`
- AtomWorks annotators (`atomworks.io.utils.annotator`)
- StandardAnnotation fallback registry (`atomworks.io.utils.standard_annotations.base`)
- [Expandable-segment semantics](../../docs/concepts/conditioning.md#expandable-segments)

## Skill Output

Output type(s): annotated `.cif`, condition summary, invariant and round-trip report.

Output format: mmCIF with AtomWorks `StandardAnnotation` conditions and preserved structural chemistry.

## Skill Version

0.3.0 (2026-09).

## Ethical Considerations

Annotated CIFs define molecular design problems and inherit the dual-use considerations of protein generation. Do not assist with hazardous biomolecule design. Make destructive preprocessing and uncertain chemistry visible to the user.

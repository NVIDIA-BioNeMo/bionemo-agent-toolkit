---
name: rfd4-proteina-annotated-cif
description: Use when creating, inspecting, editing, or validating RFD4-Proteina annotated CIF inputs and conditioning with AtomWorks.
license: CC-BY-4.0 AND BSD-3-Clause
allowed-tools: Bash, Read, Write
metadata:
  author: Ohad Mosafi <omosafi@nvidia.com>
  tags: [protein-design, rfd4, annotated-cif]
---

# RFProteína annotated CIF authoring

## Purpose

An annotated CIF is a structure plus AtomWorks `StandardAnnotation` columns that
encode the RFProteína design problem. Prefer direct Python manipulation of an
`AtomArrayPlus`: parse, derive selection annotations, set conditions, validate,
write, and round-trip. Visually inspect chemistry and intent, especially for
ligands, metals, PTMs, or PDB sources.

This skill defines CIF authoring semantics. Workspace instructions and the
active campaign govern shared-input ownership, output locations, length
materialization, generation, and database accounting. Authoring a CIF does not
by itself authorize a generation run or establish a campaign ledger policy.

## Prerequisites

An RFD4-Proteina environment with AtomWorks, NumPy, Biotite, and Python Fire; access to the matching input manual and source structures.

Use the user-selected model checkout at `RFPROTEINA_ROOT` for model commands,
configs, and upstream manuals. This catalog contains the skills, not that checkout.
In helper examples, resolve `open-models-skills/rfd4-proteina/<name>/...` to its absolute installed path
when the catalog and model checkout are separate.

## Inputs

Required: the user-requested operation, source structure paths/provenance, and destination for authored CIFs. Optional: assembly, chains, and conditioning selections when already unambiguous. Reuse established intent; resolve any ambiguity that changes the design problem.

## Instructions

1. Inspect the source, existing conditions, requested assembly, and design intent.
   Ask only about ambiguities that change the design problem.
2. Read [python-authoring.md](references/python-authoring.md) for registry import,
   parser selection, condition edits, expandable segments, and combining arrays.
3. Read [annotators-and-selections.md](references/annotators-and-selections.md)
   when translating structural intent into atom masks or checking installed
   annotation support.
4. Use the canonical [condition reference](references/upstream-sources.md#conditions-and-interactions)
   and [interaction rules](references/upstream-sources.md#conditions-and-interactions)
   for condition levels, values, and model support. Do not infer support from an
   annotation's ability to round-trip.
5. Complete [validation.md](references/validation.md), including chemistry and
   indexing review, pre-save checks, and save/reload comparison.

For a saved CIF, use `bash open-models-skills/rfd4-proteina/rfd4-proteina-annotated-cif/scripts/inspect_cif.sh <file.cif>`
to inventory its structure, chemistry, expandable segments, and conditions. Use
`bash open-models-skills/rfd4-proteina/rfd4-proteina-annotated-cif/scripts/check_annotated_cif.sh <file.cif>`
for pipeline validation and chemistry checks. Both helpers are read-only; see the
[validation reference](references/validation.md#saved-cif-checks) for options and limits.

## Output standard

Return the annotated CIF artifacts required by the task, identifying source
templates and any sampled children. Report input provenance and parse preset,
selections and conditioning counts, segment and chemistry edits, validation
results, and any unresolved scientific ambiguity.

## Limitations

Successful parsing and round-trip checks do not establish biological correctness. Pipeline validation samples one expandable-segment realization, not every possible length.

## Troubleshooting

If an import or annotation is unavailable, check the selected environment and installed registries. If validation or round-trip comparison fails, retain the source and report the specific condition or chemistry mismatch.

## Examples

Inspect and validate a saved input without modifying it:

```bash
bash open-models-skills/rfd4-proteina/rfd4-proteina-annotated-cif/scripts/inspect_cif.sh input.cif
bash open-models-skills/rfd4-proteina/rfd4-proteina-annotated-cif/scripts/check_annotated_cif.sh input.cif --strict
```

For authoring, follow the [Python recipes](references/python-authoring.md) and save/round-trip checks.

## Available Scripts

| Script | Purpose | Arguments |
| --- | --- | --- |
| `scripts/inspect_cif.sh` | Read-only structure and condition inventory | CIF path |
| `scripts/check_annotated_cif.sh` | Validate conditions and chemistry | CIF path; `--strict`, `--quiet`, `--skip_pipeline` |

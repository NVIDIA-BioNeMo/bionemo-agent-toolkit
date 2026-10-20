---
name: rfd4-proteina-package
description: Use when packaging selected RFD4-Proteina designs, aligned refolds, measured metrics, and filters into a shareable TAR.
license: CC-BY-4.0 AND BSD-3-Clause
allowed-tools: Bash, Read, Write
metadata:
  author: Ohad Mosafi <omosafi@nvidia.com>
  tags: [protein-design, rfd4, package]
---

# Package RFD4-Proteína designs

## Purpose

Create a recipient-facing archive, not a second provenance system. The campaign
ledger remains authoritative; the TAR contains only the files and explanations a
recipient needs to inspect selected designs and refolds.

## Output Format

```text
package/
├── README.md
├── WATERFALL.md
├── metrics.csv
├── inputs/
│   └── <input-name>.cif
└── outputs/
    └── <input-name>/
        └── <design-id>/
            ├── <design-id>__design.cif
            ├── <design-id>__<role>__<backend>__<prediction-id>__refold.cif
            └── <design-id>__<role>__<backend>__<prediction-id>__confidence.json
```

The generated design is the oracle input and alignment reference. Include it once.
Transform each copied refold into the design's frame by superimposing the recorded
chain or chains of interest, then write only that aligned refold to the package.
Include confidence JSON when it exists. Do not add a database, manifest, checksum
file, duplicate raw/aligned structures, provenance JSON, filter-results table, or
alignment metadata file.

## Prerequisites

The RFD4-Proteina Python environment with AtomWorks, Biotite, and NumPy; a reconciled campaign ledger and its archived structures.

Use the user-selected model checkout at `RFPROTEINA_ROOT` for model commands,
configs, and upstream manuals. This catalog contains the skills, not that checkout.
In helper examples, resolve `open-models-skills/rfd4-proteina/<name>/...` to its absolute installed path
when the catalog and model checkout are separate.

## Inputs

Required: the user-selected existing database, immutable criteria-set ID, selected designs, and fresh archive destination. Optional: package display name. Read chain-of-interest mappings and measured values from the reconciled ledger.

## Instructions

1. Confirm the immutable criteria-set version and whether the selection is all
   passers or an explicitly defined unique-passer subset.
2. Import corrections and rerun `evaluate-passers` for the chosen criteria set,
   then reconcile the campaign ledger. Delivery uses each design's latest decision
   and its exact evidence; historical passes do not override newer failures.
   Stop on missing selected designs, missing input
   mappings, missing criteria evidence, or ambiguous chain-of-interest alignment.
3. Group selected designs by their exact annotated-CIF input and assign unique,
   filesystem-safe names.
4. Copy each annotated CIF and design. Copy and align every linked oracle prediction,
   preserving role (`on-target`, named off-target, checkpoint), backend, and
   prediction identity in its filename. Copy available confidence JSON beside it.
5. Write `metrics.csv` with one row per design and the actual numeric values used
   by every filter. Do not replace those values with Boolean pass/fail columns.
6. Write `WATERFALL.md` with the exact metric, operator, threshold, missing policy,
   and cumulative counts overall and per input.
7. Write a short `README.md`, create the TAR, reopen it, and validate its expected
   paths and one-to-one design/input grouping.

Read [references/package-format.md](references/package-format.md) when building or
reviewing the archive. Read [references/alignment.md](references/alignment.md)
before aligning refolds.

## Examples

```bash
python open-models-skills/rfd4-proteina/rfd4-proteina-package/scripts/package_campaign.py --help
```

The builder reads the campaign database only while constructing the archive. The
archive itself is a pure directory tree of Markdown, CSV, CIF, and optional JSON
files.
Compressed source structures are decoded into ordinary CIFs in the archive; never
copy gzip or Zstandard bytes under a plain `.cif` filename.

## Limitations

Alignment requires an unambiguous recorded chain-of-interest mapping. Packaging preserves measured evidence; it does not validate biological claims or repair missing provenance.

## Troubleshooting

Stop on missing archived files, unreconciled metrics, or ambiguous alignment. Resolve the ledger evidence first; select a new destination if an archive already exists.

## Available Scripts

| Script | Purpose | Arguments |
| --- | --- | --- |
| `scripts/package_campaign.py` | Build a TAR from an existing ledger | `--database`, `--criteria-set`, `--output`; optional `--package-name` |

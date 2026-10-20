# Skill Card

## Description

`rfd4-proteina-package` creates a simple TAR of selected RFD4-Proteína designs grouped
by annotated-CIF input, with exact filter waterfall, actual metric values, aligned
on/off-target refolds, and available confidence JSON.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository.

## Use Case

Use when campaign results need to be shared with recipients who should not need
SQLite or the RFD4-Proteína runtime to browse the deliverable.

## Requirements / Dependencies

Building from a campaign requires its reconciled SQLite ledger. CIF alignment uses
the repository's AtomWorks/Biotite environment. Reading the final TAR has no
software dependency beyond ordinary archive and text/structure viewers.

## Known Risks and Mitigations

Risk: a refold is paired with or aligned to the wrong design. Mitigation: database
foreign keys provide the pair and the recorded chain of interest provides the
alignment selection; the builder never matches by filename fragment.

Risk: a waterfall hides the values behind Boolean columns. Mitigation:
`metrics.csv` contains the exact numeric evidence and `WATERFALL.md` contains the
operator and threshold.

## Skill Output

A `.tar` or `.tar.gz` containing README, waterfall, actual-values metrics CSV,
annotated inputs, designs, aligned refolds, and optional confidence JSON.

## Ethical Considerations

The package communicates computational outputs and proxy metrics, not experimental
validation. README language must preserve that distinction.

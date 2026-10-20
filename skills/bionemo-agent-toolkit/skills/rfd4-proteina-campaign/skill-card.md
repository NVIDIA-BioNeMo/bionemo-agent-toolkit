# Skill Card

## Description

`rfd4-proteina-campaign` orchestrates a reproducible RFD4-Proteína design campaign.
It records exact annotated-CIF inputs, resolved configs, runs, design lineage,
oracle predictions, actual metrics, and versioned passer decisions in a portable
SQLite ledger with archived artifacts.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository.

## Use Case

Use for multi-stage campaigns that must remain inspectable and recoverable across
generation, reward search, evaluation, and partial diffusion. Use the narrower
sibling skills for individual runs.

## Requirements / Dependencies

Requires a completed `rfd4-proteina-setup`. Generation and oracle requirements are
those of the composed sibling skills. The ledger helper uses Python's standard
library and does not submit jobs.

## Known Risks and Mitigations

Risk: output filenames are used as provenance and later join to the wrong input or
config. Mitigation: stable database IDs and foreign keys connect every design to
its input, config, run, parents, predictions, and metric evidence.

Risk: preempted jobs appear to have lost all work. Mitigation: immutable,
incremental worker events and idempotent ingestion preserve completed designs and
oracle predictions before retry decisions.

Risk: scheduler optimization changes the user's allocation. Mitigation: the skill
requires exact preservation and disclosure of every scheduler choice.

Risk: passer thresholds change and rewrite the scientific record. Mitigation:
criteria sets and their evaluations are immutable and versioned.

## Skill Output

A campaign directory containing `campaign.sqlite`, archived artifacts, run event
streams, and regenerated reports. Delivery TARs are produced by
`rfd4-proteina-package`.

## Ethical Considerations

Computational metrics and oracle confidence are proxies rather than experimental
validation. Apply the repository's dual-use constraints and do not represent a
computational passer as experimentally safe or functional.

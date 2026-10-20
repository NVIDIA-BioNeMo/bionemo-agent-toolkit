---
name: rfd4-proteina-campaign
description: Use when running RFD4-Proteina campaigns with provenance linking inputs, designs, oracle results, metrics, and passer criteria.
license: CC-BY-4.0 AND BSD-3-Clause
allowed-tools: Bash, Read, Write
metadata:
  author: Ohad Mosafi <omosafi@nvidia.com>
  tags: [protein-design, rfd4, campaign]
---

# RFD4-Proteína design campaigns

## Purpose

A campaign is an inspectable scientific program, not a collection of output
directories. Its durable product is a ledger that connects every design to the
exact annotated CIF, resolved configuration, run, lineage, metrics, oracle
predictions, and versioned passer decision that produced it.

## Required operating contract

1. Interview the user about intent, success criteria, uniqueness, compute budget,
   and scheduler choices before launching work.
2. Initialize the campaign ledger before the first run. Register inputs, resolved
   configs, and planned runs before submission; ingest designs and oracle results
   incrementally.
3. Preserve every user-selected partition, account, QoS/priority, reservation,
   constraint, GPU, memory, CPU, and runtime setting. State the resolved values
   before submission and never substitute a competing directive.
4. Give every materialized design a stable ID. Never recover input, config, or
   parentage by matching filename fragments.
5. Preserve all oracle predictions and available confidence JSON, including
   on-target, off-target, checkpoint, and failed evaluations. Metrics link to the
   exact design or prediction that produced them.
6. Define passers with an immutable criteria-set version. Store actual metric
   values and evidence; changing a threshold creates a new evaluation rather than
   overwriting history.
7. Treat interrupted runs as recoverable. Ingest completed outputs, record missing
   or failed work explicitly, and reconcile the filesystem with the ledger before
   retrying.

## Prerequisites

Python 3.12 for the ledger, a writable campaign directory, and the setup/generation/evaluation skills for model runs.

Use the user-selected model checkout at `RFPROTEINA_ROOT` for model commands,
configs, and upstream manuals. This catalog contains the skills, not that checkout.
In helper examples, resolve `open-models-skills/rfd4-proteina/<name>/...` to its absolute installed path
when the catalog and model checkout are separate.

## Inputs

Required: the user's campaign location, objective, criteria, uniqueness rule, budget, and scheduler choices. Optional: an existing ledger to resume. Reuse established choices; ask only for missing values that affect the campaign.

## Instructions

1. **Intent and setup** — complete `rfd4-proteina-setup`, interview the user, and
   initialize the ledger.
2. **Inputs** — use `rfd4-proteina-annotated-cif` to create and validate each
   annotated CIF; archive every conditioning variant as a distinct input.
3. **Criteria** — agree on gating metrics, exact operators and thresholds,
   missing-value policy, and the definition of uniqueness.
4. **Pilot** — run one small end-to-end generation and evaluation, including the
   ledger ingest and reconciliation path.
5. **Baseline** — use `rfd4-proteina-generate` to establish best-of-N pass rate,
   diversity, and GPU-hour efficiency.
6. **Explore** — use `rfd4-proteina-commitment-curves` when reward timing matters
   and `rfd4-proteina-autoresearch` for wave-based search experiments.
7. **Scale and proliferate** — scale selected input/config pairs, then use partial
   diffusion where supported by the evidence. Preserve parent-child lineage.
8. **Evaluate and deliver** — use `rfd4-proteina-evaluate`, recompute passers under
   the named criteria version, and call `rfd4-proteina-package` for a shareable TAR.

Read [references/campaign-strategy.md](references/campaign-strategy.md) when
choosing baselines, experiments, scaling, or partial diffusion. Read
[references/lifecycle.md](references/lifecycle.md) before planning or running a
campaign. Read [references/campaign-ledger.md](references/campaign-ledger.md) before
creating or ingesting records. Read
[references/passers-and-oracles.md](references/passers-and-oracles.md) when
defining filters, uniqueness, or refolding. Read
[references/execution-and-recovery.md](references/execution-and-recovery.md)
before any real launch or recovery.

## Examples

The deterministic helper creates a portable SQLite ledger and content-addressed
artifact store:

```bash
python open-models-skills/rfd4-proteina/rfd4-proteina-campaign/scripts/campaign_ledger.py --help
```

Cluster workers write immutable JSONL events under their run directory. A single
coordinator imports those events into SQLite; workers do not write the shared
database concurrently. CSV/Markdown reports are exports, never the source of
truth.

## Output Format

A campaign handoff reports the criteria-set version, number of evaluated designs,
passers and unique passers, unresolved failures or missing metrics, compute used,
and exact location of the ledger and delivery TAR. A delivered design must trace
to its annotated CIF, resolved config, output CIF, oracle predictions, actual
metric values, and passer evidence.

## Limitations

The ledger records provenance and measured criteria; it does not establish experimental binding or activity. Missing metrics remain explicit and cannot count as evidence of a passer.

## Troubleshooting

For interrupted jobs, ingest completed events and reconcile before retrying. For missing artifacts or criteria evidence, inspect the recorded IDs and source paths; do not infer lineage from filenames.

## Available Scripts

| Script | Purpose | Arguments |
| --- | --- | --- |
| `scripts/campaign_ledger.py` | Create, ingest, reconcile, and query the ledger | Subcommand; `--help` lists its required arguments |

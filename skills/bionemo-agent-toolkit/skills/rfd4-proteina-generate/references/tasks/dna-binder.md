# DNA binder design

Design transcription-factor-like proteins that bind DNA. Back to the
[skill](../../SKILL.md).

## What the task is

Condition on a DNA duplex (coordinate-conditioned, often with H-bond acceptor /
donor conditioning to base edges) and design a protein that binds a target site.

## Example inputs (`data/benchmarks/`)

| File | Keys | Notes |
| --- | --- | --- |
| `dna_binder/dna_binder_denovo_val` | `7n5u_structure_context`, `7n5u_sequence_context`, `7m5w_*`, `7rte_*` | Structure- vs sequence-context variants |

## Run

```bash
rfd4-generate \
    inputs=data/benchmarks/dna_binder/dna_binder_denovo_val \
    subset_to_examples=7n5u_structure_context \
    num_replicates=8 batch_size=8 out_dir=./runs/dna_binder \
    metrics_tags='[dna_refolding,interchain_interactions]'
```

## Task-specific overrides & metrics

- **`interchain_interactions`** — protein-DNA H-bond / interaction adherence and
  counts (no AF3 container required; see **rfd4-proteina-evaluate**).
- **`dna_refolding`** — AF3 refolding and DNA-interface quality metrics; requires
  the configured AF3/OpenFold3 container.

## Gotchas

- Base-edge H-bond donor and acceptor selections are per-atom and easy to get
  wrong. Use **rfd4-proteina-annotated-cif** to annotate and validate them.

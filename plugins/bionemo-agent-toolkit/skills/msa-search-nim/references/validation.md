# MSA-Search Validation

Validate that the search produced usable alignment or template artifacts before
passing them downstream.

## Alignment Checks

- `alignments` exists for standard search.
- `alignments_by_chain` exists for paired search.
- Each returned alignment has `alignment` text and a `format`.
- A3M/FASTA text starts with FASTA-style headers.
- Saved filenames include database and format so outputs do not overwrite each
  other.
- Record database names and e-value used for the search.

## Template Checks

- Template response includes `structures` and `search_hits`.
- Save each returned structure as `.cif`.
- Save M8 hit tables as `.m8` or `.tsv`.
- Confirm `max_msa_sequences` matches `NIM_GLOBAL_MAX_MSA_DEPTH` for local GPU
  server mode.

## Scientific Warnings

- Very shallow alignments may not improve downstream structure prediction.
- Excessive near-duplicate sequences can bias an MSA.
- Pairing failure can reduce complex-prediction usefulness.
- Template hits should be inspected for coverage, e-value, and biological
  relevance before use.

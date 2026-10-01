# MSA-Search Validation

Validate that the search produced usable alignment or template artifacts before
passing them downstream.

## Alignment Checks

- `alignments` exists for standard search.
- `alignments_by_chain` exists for paired search.
- Each returned alignment has `alignment` text and a matching `format` (`a3m`
  for the hosted client's requested output).
- Each A3M/FASTA record has a nonempty FASTA-style header followed by sequence
  data. Reject missing records, empty records, and invalid sequence characters.
- A3M records have equal numbers of match columns: uppercase residues and `-`
  count toward the width; lowercase insertions do not. Wrapped sequence lines,
  blank lines, and `#` comments are allowed.
- Saved filenames include database and format so outputs do not overwrite each
  other.
- The hosted client publishes the output directory after every file is written;
  a write failure removes temporary files so the same output path can be retried.
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

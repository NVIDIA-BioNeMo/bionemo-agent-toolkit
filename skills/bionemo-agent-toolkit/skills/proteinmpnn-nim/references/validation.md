# ProteinMPNN Validation

Validate both response shape and biological plausibility before presenting
designed sequences as useful.

## Response Checks

- `mfasta` exists and is non-empty.
- FASTA headers and sequences parse cleanly.
- Designed sequence count matches `num_seq_per_target` after accounting for any
  native/WT row.
- `scores`, when present, are reported for designed sequences only.

## Artifact Checks

- Save `mfasta` as `.fa` or `.fasta`.
- Keep request metadata including input PDB name, chains, temperatures, omitted
  residues, and soluble-model flag.
- Do not overwrite outputs from multiple temperatures.

## Scientific Checks

- Confirm designed chains and fixed chains match the user request.
- Check for excluded amino acids in designed sequences.
- Flag unusual cysteine/methionine exclusions or extreme composition choices.
- Recommend fold-back validation with OpenFold3 or Boltz2 for serious use.

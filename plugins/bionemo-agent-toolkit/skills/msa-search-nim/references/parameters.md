# MSA-Search Parameter Guidance

Use exact database names and keep local-depth settings consistent with the
container configuration.

## Standard Search

- `sequence`: one protein sequence, 1-4096 amino acids.
- `databases`: case-sensitive names such as `Uniref30_2302` and
  `colabfold_envdb_202108`; use `all` only when appropriate.
- `output_alignment_formats`: usually `["a3m"]`; include `fasta` only when the
  user asks.
- `e_value`: default `0.0001`; relax for remote homologs, tighten for precision.
- `max_msa_sequences`: default `500`; for local GPU server mode it must match
  `NIM_GLOBAL_MAX_MSA_DEPTH`.

## Paired Search

- Use `/paired/predict`.
- Use `sequences`, not `sequence`.
- Provide at least two chains.
- Parse `alignments_by_chain`; do not expect the standard `alignments` shape.
- `pairing_strategy` may be `greedy` or `complete`.

## Template Search

- Use local `/structure-templates/predict`.
- Use canonical template database names such as `pdb70_220313`.
- Set `max_structures` to the requested count.
- Include `max_msa_sequences=500` unless the local `NIM_GLOBAL_MAX_MSA_DEPTH`
  was changed.

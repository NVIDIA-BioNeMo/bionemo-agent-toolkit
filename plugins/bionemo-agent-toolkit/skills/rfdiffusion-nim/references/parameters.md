# RFDiffusion Parameter Guidance

## Core Fields

- `contigs`: required design DSL.
- `input_pdb`: inline PDB content. Hosted validation requires non-empty
  `input_pdb` or `input_pdb_asset`, even for de novo examples.
- `hotspot_res`: list of chain-residue strings such as `["A50", "A51"]`.
- `diffusion_steps`: 1-50. Use `50` for maximum quality.
- `random_seed`: optional reproducibility for development comparisons.

## Contig Patterns

- `"100"`: generate exactly 100 residues.
- `"80-120"`: generate a length sampled from the range.
- `"A25-35/0 50-80"`: preserve chain A residues 25-35, then chain break, then
  generate 50-80 residues.
- `"A1-100/0 50-100"`: keep target chain A and generate a binder segment.

## De Novo Hosted Quirk

For de novo inline requests, include a minimal dummy PDB because live hosted
validation rejects requests that omit both `input_pdb` and `input_pdb_asset`.

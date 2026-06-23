# DiffDock Parameter Guidance

## Core Fields

- `protein`: required receptor PDB content. Use non-empty ATOM records only.
- `ligand`: required ligand content. For SMILES, pass one SMILES per line.
- `ligand_file_type`: required. Use `"txt"` for SMILES, `"sdf"` for SDF, or
  `"mol2"` for MOL2. Do not use `"smiles"`.
- `num_poses`: optional integer, up to `100`. Use `5-20` for quick exploration
  and more poses when screening a difficult target.
- `time_divisions`: optional integer, maximum `20`. Higher values are slower
  and more thorough.
- `steps`: optional integer, maximum `18`. Higher values are slower and more
  thorough.
- `save_trajectory`: optional boolean. Keep `false` for normal pose generation;
  use `true` only when trajectory frames are needed.
- `skip_gen_conformer`: optional boolean. Use with care when ligand input already
  encodes a suitable conformation.
- `is_staged`: optional boolean staging flag.

## Ligand Format Choices

- Use SMILES plus `ligand_file_type="txt"` for simple single-ligand requests.
- Use SDF when the ligand has a known protonation state, stereochemistry, or 3D
  conformer that should be preserved.
- Use multi-entry SDF for batch docking when appropriate, and keep output file
  naming explicit because returned poses and confidences are parallel arrays.

## Practical Tuning

- Start with `num_poses=10`, `time_divisions=20`, and `steps=18`.
- Increase `num_poses` before changing diffusion controls if the issue is pose
  diversity.
- Keep `save_trajectory=false` unless the user explicitly asks for trajectory
  artifacts.
- For reproducible reporting, record all parameter values, receptor source,
  ligand source, endpoint mode, NIM image/version if local, and elapsed time.

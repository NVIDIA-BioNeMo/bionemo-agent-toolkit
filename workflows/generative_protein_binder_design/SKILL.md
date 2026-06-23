# Generative Protein Binder Design

Two composable skills for de novo protein binder design. Each resolves a target +
hotspots, generates binders, then runs an **independent** structure-prediction co-fold
and ranks by interface metrics (ipTM / ipSAE / pLDDT / apo↔holo RMSD):

- **[`complexa-binder-design/`](complexa-binder-design/SKILL.md)** — NVIDIA
  **Proteina-Complexa** reward-guided co-design (binder sequence + structure together)
  with an AF2-reward gate, validated independently with Boltz2 / OpenFold3.
- **[`protein-binder-design/`](protein-binder-design/SKILL.md)** — **RFdiffusion +
  ProteinMPNN + Boltz2 / OpenFold3** BioNeMo NIM orchestration (backbones → sequences →
  co-fold → filter).

See each skill's `SKILL.md`, `README.md`, and `references/` for setup (incl. local-NIM
launch) and usage.

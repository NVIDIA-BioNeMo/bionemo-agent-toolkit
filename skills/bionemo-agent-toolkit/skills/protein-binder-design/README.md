# protein-binder-design (Agent Skill)

De novo protein binder design as an **Agent Skill**: an agent composes BioNeMo
NIMs — **RFdiffusion → ProteinMPNN → Boltz2 / OpenFold3** — to diffuse binder
backbones, design sequences, co-fold each binder with the target, validate, and
rank, writing a reproducible run manifest.

## Layout

```
protein-binder-design/
├── SKILL.md                 # entry point (agent reads this first)
├── references/
│   ├── pipeline.md          # stage-by-stage orchestration + per-NIM request shapes
│   ├── validation.md        # controls, success-rate methodology, metric defs
│   └── manifest.md          # run-manifest schema
├── scripts/
│   ├── manifest.py          # campaign manifest (create/score/filter/rank/CSV)
│   ├── pdb_utils.py         # PDB parse, chain extract, residue remap
│   ├── metrics.py           # Kabsch CA-RMSD (self-consistency)
│   ├── controls.py          # scrambled negative controls
│   └── registry.py          # target-registry loader
├── assets/targets.json      # EXAMPLE target registry (verify before real use)
└── evals/                   # trigger + assertion evals
```

## Prerequisites

- A Skill-aware agent (Claude Code / Cursor / Codex, etc.).
- Access to the BioNeMo NIMs you intend to use (RFdiffusion, ProteinMPNN, Boltz2
  and/or OpenFold3, optional MSA-Search) — hosted at
  [build.nvidia.com](https://build.nvidia.com) or self-hosted via NGC.
- Python ≥ 3.10 with `numpy` (`pip install numpy`). Scripts are otherwise stdlib.

## Configure

Pick hosted or local once (see `SKILL.md` → Configuration). For hosted:

```bash
export NVIDIA_API_KEY=nvapi-...
```

## Run (from an agent)

Open this folder in your agent and prompt, e.g.:

> Design 10 binders against `<your target>` (give a name, UniProt accession, or PDB +
> chain, and the epitope/hotspots); validate with Boltz2 and give me a ranked table.

The agent loads `SKILL.md`, follows `references/pipeline.md`, and writes results
under `runs/<target>_<date>/` (manifest + `candidates.csv` + a short report).

## License

Apache-2.0 (see `LICENSE`).

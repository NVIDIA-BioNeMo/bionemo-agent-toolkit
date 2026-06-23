# complexa-binder-design (Agent Skill)

De novo protein binder design as an **Agent Skill**, powered by NVIDIA
**Proteina-Complexa** — a generative model that **co-designs the binder sequence and
full-atom structure together** (no inverse-folding step) with reward-guided
test-time search. The skill drives the open `complexa` CLI to generate, then
**independently validates** each binder with a different model (Boltz2 / OpenFold3),
gates on interface confidence, ranks, and writes a reproducible manifest.

## Layout

```
complexa-binder-design/
├── SKILL.md                 # entry point (agent reads this first)
├── references/
│   ├── target-and-hotspots.md  # Stage 1: structure resolution + evidence-based hotspots + crop
│   ├── complexa-cli.md         # how to drive the open `complexa` CLI (overrides, search, outputs)
│   ├── pipeline.md             # stage-by-stage orchestration + run-until-N-validated loop
│   └── validation.md           # independent holo/apo refold, metrics, gate
├── scripts/
│   ├── pipeline.py          # Stage-1 resolution + Stage-2 generation (open CLI) + scoring
│   ├── preflight_design.py  # no-GPU target/hotspot/size planner (READY verdict)
│   ├── hotspot_strategy.py  # evidence-based, accessibility-aware hotspot resolver
│   ├── pdb_interface.py     # PDB co-complex interface hotspots (gold standard)
│   ├── complexa_design.py   # thin `complexa design` driver (submit → discover → extract)
│   ├── validate_binders.py  # independent Boltz2/OF3 scoring, ipSAE, apo↔holo RMSD, gating
│   ├── fetch_ipsae.sh       # fetch the MIT ipSAE script into vendor/ipsae/
│   ├── fetch_target_msa_colabfold.py
│   └── pdb_to_boltz_template_cif.py
├── prompts/hotspot_paperclip.md  # literature-mining fallback prompt
├── assets/targets.json      # EXAMPLE upstream targets; use `complexa target add` for your own
├── vendor/
│   ├── science-skills/      # vendored UniProt + AFDB tooling (Apache-2.0)
│   └── ipsae/               # ipSAE lands here after fetch_ipsae.sh (not bundled)
├── NOTICE                   # third-party attribution
└── LICENSE                  # Apache-2.0
```

## Setup

Full standalone (no-NIM) setup — install Proteina-Complexa + weights, Python deps,
AF2 configure-vs-bypass, optional analyze tools, validation endpoint, and all env
vars — is in **[`references/setup.md`](references/setup.md)**. After setup, run
`bash scripts/check_setup.sh` for a readiness checklist. Quick prerequisites:

## Prerequisites

1. **Proteina-Complexa** — clone, build, and download weights:
   ```bash
   git clone https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa
   cd Proteina-Complexa && ./env/build_uv_env.sh && source .venv/bin/activate
   complexa init && complexa download --complexa-all
   export COMPLEXA_REPO=$PWD
   ```
   Project page: <https://research.nvidia.com/labs/genair/proteina-complexa/> ·
   Weights (NGC): `nvidia/clara/proteina_complexa`.
2. **A validator NIM** — Boltz2 (default) or OpenFold3, hosted at
   [build.nvidia.com](https://build.nvidia.com) (`export NVIDIA_API_KEY=nvapi-...`)
   or self-hosted (`--endpoint local`).
3. **ipSAE** — `bash scripts/fetch_ipsae.sh` (one-time; MIT, fetched not bundled).
4. **Python** ≥ 3.10 with `numpy`, `gemmi`, `pyyaml` (Stage-1 structure handling +
   target registration); `gemmi` also enables Boltz2 templates. The optional
   **Paperclip** CLI enables the literature-mining hotspot fallback.

Then plan a target with **no GPU**:

```bash
python scripts/preflight_design.py <target>  # name, UniProt accession, or PDB; READY / NEEDS-ATTENTION verdict
```

## Run (from an agent)

Open this folder in your agent and prompt, e.g.:

> Design 10 binders for `<your target>` with Proteina-Complexa using best-of-N search,
> then validate them independently with Boltz2 and rank by interface confidence.

The agent loads `SKILL.md`, generates via the `complexa` CLI (`references/complexa-cli.md`),
re-folds each binder independently, gates, and writes `runs/<target>_<date>/`
(manifest + `ranked_binders.json/.csv` + report).

> **Why two models?** Proteina-Complexa's own evaluate stage uses AF2/RF3/ESMFold —
> the family its search optimizes against. Validating with Boltz2/OpenFold3 gives an
> *independent* interface-confidence check.

## License

Apache-2.0 (see `LICENSE`); third-party components keep their own licenses (`NOTICE`).

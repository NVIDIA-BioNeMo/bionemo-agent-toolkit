---
name: protein-binder-design
description: >
  Orchestrate an end-to-end de novo protein binder design campaign against a protein target by composing BioNeMo NIM skills. Use for binder design, minibinder design, de novo binders, RFdiffusion + ProteinMPNN + Boltz2/OpenFold3 pipelines, epitope/hotspot-targeted design, in-silico binder validation, and ranking designs by interface confidence.
license: Apache-2.0
compatibility: "numpy>=1.24; requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Protein Binder Design (workflow)

Run a de novo binder design campaign by composing atomic NIM skills. This skill
owns orchestration, handoff contracts, filtering, validation, and the run
manifest. It does NOT duplicate per-NIM API details — defer those to each
atomic skill's `SKILL.md`.

## Composed skills

| Step | Skill | Owns |
|---|---|---|
| Backbones | `rfdiffusion-nim` | binder backbone PDBs (contigs + hotspots) |
| Sequences | `proteinmpnn-nim` | sequences for each backbone |
| Co-fold / score | `boltz2-nim` or `openfold3-nim` | binder–target complex + confidence / ipTM |
| MSA (optional) | `msa-search-nim` | target A3M for higher-quality folding |

The atomic NIM skills are recommended companions (one per NIM, from the BioNeMo
NIM skill set). They are **not required**: `references/pipeline.md` carries the
concrete request shape for every NIM call, so an agent with NIM access can follow
this skill standalone. For endpoints/auth see **Configuration** below.

## Pipeline

1. **Target prep** — get the target PDB + epitope; map epitope/hotspot author
   residue numbers to RFdiffusion `hotspot_res` strings; optionally build a
   target MSA with `msa-search-nim`.
2. **Backbones** (`rfdiffusion-nim`) — binder contig + `hotspot_res`; N backbones.
3. **Sequences** (`proteinmpnn-nim`) — k sequences per backbone; drop the
   native/WT row from `mfasta`.
4. **Co-fold + score** (`boltz2-nim` / `openfold3-nim`) — co-fold binder+target;
   collect interface confidence (ipTM) and binder pLDDT.
5. **Self-consistency** — CA-RMSD between the RFdiffusion backbone and the
   predicted binder (`scripts/metrics.py`).
6. **Filter + rank** — apply thresholds; rank survivors; write manifest + CSV.

Full handoff contracts, branching, and the cost funnel: `references/pipeline.md`.

## Handoff contracts (the fragile glue)

- RFdiffusion `output_pdb` → ProteinMPNN `input_pdb` (inline PDB text).
- ProteinMPNN `mfasta` → Boltz2 binder polymer `sequence` (exclude the
  native/WT row; pair scores only with designed rows).
- Epitope author residue numbers → 1-based sequence indices: remap with
  `scripts/pdb_utils.py:remap_to_seq_index`. RFdiffusion `hotspot_res` uses
  chain+author strings like `"A50"`; Boltz2 pocket/contacts use 1-based indices.
- Boltz2 complex `.cif` → binder chain → self-consistency RMSD vs the backbone.

## Run manifest (reproducibility backbone)

Every campaign writes `manifest.json` (+ `candidates.csv`) under a run dir via
`scripts/manifest.py`. It records lineage, params, scores, artifacts, filter
status, and controls — enabling ranking, resumability, validation, and the
final report. Schema and usage: `references/manifest.md`.

## Filters (defaults)

- ipTM ≥ 0.8, binder pLDDT ≥ 80, self-consistency RMSD ≤ 2.0 Å.
- Override per campaign and record overrides in the manifest `filters`.

## Validation

Always run controls and report a **success rate**, not just top scores.
Negative controls via `scripts/controls.py` (scrambled sequences); positive
controls = published binders re-scored through the same pipeline. Benchmark
targets live in `assets/targets.json` (`scripts/registry.py`). Methodology and
metric definitions: `references/validation.md`.

## Human-in-the-loop + cost

- Confirm target, epitope/hotspots, binder length range, and hosted-vs-local
  with the user before generating backbones (AskUserQuestion).
- Co-folding is the expensive stage: co-fold a capped shortlist, review, then
  expand. State hosted vs local once and reuse it across all NIM calls.

## Responsible use

De novo binder design is dual-use. Decline requests aimed at enhancing pathogen
fitness, toxin potency, or bioweapon function; keep designs to legitimate
research and therapeutic intent.

## Configuration (NIM access)

Each composed NIM is reached over HTTP; choose **hosted** or **local** once and
reuse it for every call:

- **Hosted** (managed): base URL `https://health.api.nvidia.com/v1/...` per NIM at
  [build.nvidia.com](https://build.nvidia.com); set `NVIDIA_API_KEY` (sent as
  `Authorization: Bearer`). Read keys from the env — never hardcode them.
- **Local** (self-hosted NGC containers): point each NIM at its local URL
  (e.g. `http://localhost:8000/...`); local NIMs need no auth header. To **launch** the
  NIMs yourself (docker run per NIM, persistent caches, health checks, and the GPU
  **profile‑selection gotcha** — some NIMs (e.g. Boltz2) need `NIM_MODEL_PROFILE` pinned
  on GPUs that have no bundled profile, while others (RFdiffusion/ProteinMPNN) auto‑select
  by compute capability): see **`references/local-nim-setup.md`**.

Per-NIM paths, request/response schemas, and worked `curl`/Python examples live in
`references/pipeline.md`.

## Scripts

- `scripts/manifest.py` — campaign manifest (create / load / score / filter / rank / CSV).
- `scripts/pdb_utils.py` — PDB parse, chain extract, sequence, residue remap, CA coords.
- `scripts/metrics.py` — Kabsch CA-RMSD for self-consistency.
- `scripts/controls.py` — scrambled negative controls.
- `scripts/registry.py` + `assets/targets.json` — **example** benchmark target
  registry (illustrative epitopes — verify against the cited structure before a
  real campaign). Replace with your own targets.

---
name: protein-binder-design
description: >
  Orchestrate an end-to-end de novo protein binder design campaign against a protein target by composing BioNeMo NIM skills. Use for binder design, minibinder design, de novo binders, RFdiffusion + ProteinMPNN + Boltz2/OpenFold3 pipelines, epitope/hotspot-targeted design, in-silico binder validation, and ranking designs by interface confidence.
license: Apache-2.0
compatibility: "numpy>=1.24; requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
permissions:
  - env      # reads NVIDIA_API_KEY/NGC_API_KEY and configured NIM endpoints
  - network  # calls hosted NVIDIA APIs or user-configured local NIM endpoints
---

# Protein Binder Design (workflow)

<!-- nv-carps: dummy edit to trigger NIM skill validation. -->

Run a de novo binder design campaign by composing atomic NIM skills. This skill
owns orchestration, handoff contracts, filtering, validation, and the run
manifest. For per-NIM API details, consult the corresponding NIM skill.

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

## Instructions

Resolve the campaign inputs before inference. The bundled `assets/targets.json`
is a template, not a populated PD-L1 registry. A named target needs a verified
structure, chain, and epitope; controls need existing candidate sequences and
sourced positive controls; resuming needs the original manifest and artifacts.
Check the supplied paths first. If an input or NIM credential is missing, record
the blocker and the unexecuted stages. Do not invent registry entries, measured
scores, or an interrupted run. An empty CSV is not a completed campaign.

### Pipeline

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
- Every enabled metric needs a finite score to pass. Keep a composite confidence
  value in its own field; do not substitute it for an unavailable ipTM.

## Validation

Always run controls and report a **success rate**, not just top scores.
Negative controls via `scripts/controls.py` (scrambled sequences); positive
controls = published binders re-scored through the same pipeline. Benchmark
targets live in `assets/targets.json` (`scripts/registry.py`). Methodology and
metric definitions: `references/validation.md`.

## Human-in-the-loop + cost

- Reuse target, epitope/hotspots, binder length range, and hosted-vs-local
  choices already supplied by the user. Ask only for unresolved inputs before
  generating backbones.
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
  [build.nvidia.com](https://build.nvidia.com); use `NGC_API_KEY` or the
  `NVIDIA_API_KEY` fallback (sent as `Authorization: Bearer`). Read keys from the
  environment. Check only presence with
  `bool(os.getenv("NGC_API_KEY") or os.getenv("NVIDIA_API_KEY"))`; never print
  environment dumps, key values, or authorization headers. An `OPENAI_API_KEY`
  belongs to the agent runtime and must not be used as a NIM credential. If both
  NIM keys are absent, report missing access before sending authenticated calls.
- **Local** (self-hosted NGC containers): point each NIM at its local URL
  (e.g. `http://localhost:8000/...`); local NIMs need no auth header. To **launch** the
  NIMs yourself (docker run per NIM, persistent caches, health checks, and the GPU
  **profile‑selection gotcha** — some NIMs (e.g. Boltz2) need `NIM_MODEL_PROFILE` pinned
  on GPUs that have no bundled profile, while others (RFdiffusion/ProteinMPNN) auto‑select
  by compute capability): see **`references/local-nim-setup.md`**.

Per-NIM paths, request/response schemas, and worked `curl`/Python examples live in
`references/pipeline.md`.

## Examples

- **New campaign:** with a verified target entry and NIM access, create the
  manifest, remap residues with `pdb_utils.py`, generate backbones, design binder
  sequences, co-fold a shortlist, and save response-derived scores before
  filtering and exporting. Record any stages that could not run.
- **Controls:** load the existing campaign, use `make_scrambled_controls` on
  its binder sequences, and add sourced published binders. Mark all controls
  `is_control=True`, co-fold with the same settings, then report
  `n_passed / n_candidates` from `summary()` with controls excluded. With no
  candidates the rate is unavailable; disclose incomplete scoring.
- **Resume:** call `Manifest.load("runs/<campaign>")`, inspect required scores
  and saved artifacts, and execute only missing stages. Reuse saved predictions
  when only metric extraction is missing; preserve completed candidates.

## Scripts

- `scripts/manifest.py` — campaign manifest (create / load / score / filter / rank / CSV).
- `scripts/pdb_utils.py` — PDB parse, chain extract, sequence, residue remap, CA coords.
- `scripts/metrics.py` — Kabsch CA-RMSD for self-consistency.
- `scripts/controls.py` — scrambled negative controls.
- `scripts/registry.py` + `assets/targets.json` — **example** benchmark target
  registry (illustrative epitopes — verify against the cited structure before a
  real campaign). Replace with your own targets.

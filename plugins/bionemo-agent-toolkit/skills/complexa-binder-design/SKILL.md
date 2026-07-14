---
name: complexa-binder-design
description: >
  Run a complete protein binder design campaign with NVIDIA Proteina-Complexa: resolve a target structure and hotspots from a name/sequence/PDB, co-design binder sequence+structure with reward-guided test-time search (best-of-n, beam search, FK steering, MCTS), select with the internal AF2 reward gate, then INDEPENDENTLY validate each binder by refolding the complex with Boltz2 (default) or OpenFold3 and rank on interface confidence, pLDDT, ipSAE, apo/holo stability, and hotspot contact. Use whenever the user wants de novo binders against a named target, sequence, or PDB, hotspot/epitope-targeted design, Proteina-Complexa / Complexa, or ranked validated binders from one request. Sibling of protein-binder-design (RFdiffusion + ProteinMPNN); this skill uses Proteina-Complexa.
license: Apache-2.0
compatibility: "python>=3.10; numpy>=1.24; gemmi (target prep + Boltz2 templates); pyyaml (target registration)"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Complexa Binder Design (workflow)

From one request — "design binders for `<target>`" — to ranked, **independently
validated** binders. Each returned binder is a **co-designed sequence + predicted
binder–target complex**, gated by interface confidence, by whether the binder
actually contacts the target hotspots, and by **apo/holo stability**.

Generation uses **Proteina-Complexa** (co-designs binder sequence + full-atom
structure together — no inverse-folding step — with reward-guided test-time search).
Validation uses a **different** model family (Boltz2 / OpenFold3), so the headline
confidence is an independent check, not the generator grading its own homework.

> **Upstream model + code (you provide these):**
> - Project page: <https://research.nvidia.com/labs/genair/proteina-complexa/>
> - Code: <https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa> (the `complexa` CLI)
> - Weights (NGC): `nvidia/clara/proteina_complexa`
> - Paper: Didi et al., *Scaling Atomistic Protein Binder Design…*, ICLR 2026.

> **First time on a host? → `references/setup.md`** — full standalone setup with **no
> NIM**: install Proteina-Complexa + download weights, Python deps (`numpy gemmi
> pyyaml`), AF2 **configure-vs-bypass**, optional analyze tools (`foldseek`/`sc`/`dssp`),
> the Boltz2/OF3 validation endpoint, and every env var. Then run
> `bash scripts/check_setup.sh` for a one-shot readiness checklist.

```
Stage 1: Resolve target + hotspots            → target.pdb + hotspots.json   (no GPU)
        ┌──────────────────────────────────────────────────────────────────────┐
        │ repeat until ≥ N validated passers (or a stop cap):                    │
Stage 2 │   Generate (complexa design) → complex .pdb + AF2-reward-gated designs │
Stage 3 │   Validate (Boltz2 default; OF3 optional) → holo+apo + ipTM/ipSAE/     │
        │     pLDDT + apo↔holo RMSD + hotspot contact → passers                  │
        └──────────────────────────────────────────────────────────────────────┘
Stage 4: Report                               → REPORT_<target>_<run>.md (GO/NO-GO)
```

## Composed pieces (read on demand — do not inline)

| Step | Tool | Owns |
|---|---|---|
| Target + hotspots | vendored `science-skills` (UniProt, AFDB) + `scripts/` | structure resolution, evidence-based hotspots, ≤500 crop, preflight |
| Generation | **Proteina-Complexa** `complexa` CLI | co-designed binder seq+structure, AF2-reward gate → `references/complexa-cli.md` |
| Validate / score | `boltz2-nim` (default) or `openfold3-nim` | independent holo+apo refold, ipTM / pLDDT / PAE |
| MSA (target) | `msa-search-nim` or `scripts/fetch_target_msa_colabfold.py` | target A3M for higher-confidence refolds |

If you run inside the Proteina-Complexa repo, its bundled `.claude/skills`
(`complexa-setup`, `complexa-target`, `complexa-design`) can drive the generation
half; this skill adds the automated Stage 1, the independent validation, GO/NO-GO,
and the manifest.

## Stage 1 — resolve target and hotspots (no GPU)

The user gives a target as a **name**, **sequence**, and/or **structure file**.
Resolve exactly **one design-ready structure**, in priority order: (1) experimental
**PDB** (RCSB), (2) **AFDB** model (UniProt → `vendor/science-skills/.../fetch_structure.py`),
(3) **user-provided** file, (4) **fold de novo** (MSA-Search + OpenFold3/Boltz2).
`scripts/pipeline.py:resolve_target_spec`/`resolve_target` automate (1)–(2) from
free text.

**Hotspots** = the target residues the binder should contact — a compact,
surface-exposed, binder-accessible epitope. Resolve in evidence order
(`scripts/hotspot_strategy.py`, `scripts/pdb_interface.py`):

1. **PDB co-complex interface** (gold standard) — interface residues from a structure
   where the target contacts a protein partner.
2. **UniProt functional residues** — `Mutagenesis` + accessible `Active/Binding/Site`,
   **filtered to the extracellular/accessible range** (catalytic/cytoplasmic pockets
   are the wrong surface for a binder and are dropped).
3. **Literature (Paperclip)** — full-text mining when 1–2 are empty
   (`prompts/hotspot_paperclip.md`); structure-confirmed to auto-correct numbering.
4. **Unconditioned** (`[]`) only as a documented last resort.

Then enforce, deterministically:
- **Structure alignment** (`align_hotspots_to_structure`) — drop residues absent from
  the coordinate file; read back the real 3-letter identity (catches UniProt↔PDB
  numbering offsets — never assume equal indices or chain `A`).
- **Epitope sanity** (`_prune_hotspots`) — one compact patch: drop outliers > 30 Å
  from the cluster centroid, cap at 15 residues, prefer ≥ 2.
- **Size budget ≤ 500 residues** (`_crop_target_to_epitope`) — Complexa builds an
  O(n²) pair-feature map over the whole complex, so crop large targets to an epitope
  window (original numbering preserved).

**Preflight (no GPU):** `python3 scripts/preflight_design.py <name|accession> …`
reports the conditioned length, re-aligned hotspots + source, compactness, the ≤500
budget, and a READY / NEEDS-ATTENTION verdict. Review before spending GPU.

## Stage 2 — generate (Proteina-Complexa, open CLI)

Register the target (hotspots + binder length are target-dict-driven), then **use
`complexa generate` (NOT the full `complexa design`)** for the lean, fast path:

```bash
python scripts/complexa_design.py run --task-name <name> --run-name <run> \
    --algorithm best-of-n --num-samples <N> --seed 0 --out <run-dir>
```

`complexa_design.py run` defaults to the **`generate`** verb. With **`best-of-n` + the
AF2 reward** (AF2 params configured via `setup_af2_params.sh` + `AF2_DIR`), the search
**AF2-selects the best candidates during generation** and writes co-designed
**sequence + structure** PDBs to `inference/` — **use the sequence directly, do not
MPNN-redesign it**. Search algorithms: `best-of-n` (default) · `beam-search` ·
`fk-steering` · `mcts`. Overrides + outputs: `references/complexa-cli.md`.

> **Do NOT run the full `complexa design` for this workflow.** Its `evaluate` stage
> **re-folds every design with AF2/RF3/ESMFold (redundant** — best-of-n already
> AF2-selected during search**)** and its `analyze` stage needs `foldseek`/`sc`
> (usually not installed). It is much slower and adds a failure mode. The lean
> `generate` → independent **Boltz2** validation (Stage 3) is the intended path.
>
> No AF2 params? use `--af2-bypass` (`single-pass` + drop the AF2 reward); selection
> then falls entirely to the independent Boltz2 gate (Stage 3). Low-complexity
> (poly-X) sequences are dropped before spending Boltz2.

## Stage 3 — validate (independent refold) + gate

**Validate a capped shortlist, not the whole pool.** Best-of-n produces many
candidates; fold only ~**2× the requested N** (the top ones by the generation/AF2
reward) — validating the entire pool wastes GPU/time and (on hosted Boltz2) trips rate
limits. Point at a local Boltz2 NIM via `$BOLTZ2_URL` (`--endpoint local`) when available.

Per binder run **two** predictions with one refolder (Boltz2 default): **holo**
(binder + target; target MSA, binder single-sequence, `write_full_pae`) and **apo**
(binder alone). One command does it: **`scripts/boltz2_refold.py`** makes the holo
calls (with retry/backoff for rate limits) and chains **`scripts/validate_binders.py`**,
which runs apo + computes the metrics + applies the gate + ranks. Per-chain
conditioning + metric definitions: `references/validation.md`.

**Gate (defaults — every gate must hold):** ipTM ≥ 0.65, complex pLDDT ≥ 0.70, binder
pLDDT ≥ 0.70, apo binder pLDDT ≥ 0.70, **ipSAE_min ≥ 0.45**, apo↔holo binder RMSD
≤ 2.5 Å, ≥ 20% of conditioned hotspots contacted (CB–CB < 13 Å). Record **every**
design (pass *and* fail) with a `failure_reason`. Rank protein binders by interface
confidence (ipTM/ipSAE) + pLDDT + stability — **not** Boltz2 `affinity_pic50`
(ligand-only).

## Bounded-budget loop + report

The deliverable is **the top-N binders ranked by interface confidence** (default 10).
Aim for N that pass the full gate, but **bound the cost**: run **at most 2 generation
rounds**, then **deliver the top-N by score (ipTM, then ipSAE_min) even if fewer than N
clear the strict gate** — keep each design's `pass`/`failure_reason` flag so quality is
still visible. Do **not** keep generating just to chase N strict passes (that is the
single biggest time sink). Stop on N-passed / 2 rounds / budget / a zero-passer round.
One run dir per campaign; `manifest.json` records target, Complexa run config + seeds,
per-design lineage/scores/artifacts, gate status. The report states GO/NO-GO,
requested-vs-achieved N (passed and delivered), ranked binders, and which stop
condition fired. Layout, loop, and report sections: `references/pipeline.md`.

## Configuration

- `COMPLEXA_REPO` — path to your local Proteina-Complexa checkout (the `complexa`
  CLI runs there). Checkpoints via the pipeline YAML or `++ckpt_path=…`. Reward
  weights (`AF2_DIR`, `RF3_CKPT_PATH`/`RF3_EXEC_PATH`) via the repo's `.env`.
- Boltz2 / OpenFold3 endpoints + auth: hosted (`https://health.api.nvidia.com/v1/…`
  + `NVIDIA_API_KEY`) or local (`http://localhost:8000/…`, no auth). The validator
  takes `--endpoint hosted|local`; the key is read from `NVIDIA_API_KEY`/`NGC_API_KEY`
  (or `--env-file`). Never hardcode hosts/keys.
- `COMPLEXA_OUTPUTS` — run-output root (default `./outputs`).

## Scripts & assets

- `references/setup.md` + `scripts/check_setup.sh` — standalone (no-NIM) install guide
  and a one-shot environment readiness check.
- `scripts/pipeline.py` — orchestrator (Stage-1 resolution + open-CLI generation +
  AF2 gate + scoring); `score_existing` and `full` modes.
- `scripts/preflight_design.py` — no-GPU target/hotspot/size planner.
- `scripts/hotspot_strategy.py`, `scripts/pdb_interface.py` — evidence-based hotspots.
- `scripts/complexa_design.py` — thin `complexa design` driver + output extraction.
- `scripts/setup_af2_params.sh` — download AF2-Multimer params (public, no auth) +
  create the `params/` layout, for reward-guided search (`best-of-n`, etc.).
- `scripts/boltz2_refold.py` — Stage-3 **holo** Boltz2 refolds (retry/backoff + throttle)
  → `validation/raw/`, then chains `validate_binders.py`.
- `scripts/validate_binders.py` — apo Boltz2 + scoring, ipSAE, apo↔holo RMSD,
  hotspot contact, gating, ranking → `ranked_binders.json`. Needs the Dunbrack **ipSAE**
  script: `bash scripts/fetch_ipsae.sh` (MIT; fetched, not bundled — see `vendor/ipsae/`).
- `scripts/fetch_target_msa_colabfold.py`, `scripts/pdb_to_boltz_template_cif.py` —
  target MSA / structural-template helpers for validation.
- `vendor/science-skills/` — DeepMind UniProt + AFDB tooling (Apache-2.0) for Stage 1.
- `prompts/hotspot_paperclip.md` — literature-mining hotspot fallback.
- `assets/targets.json` — example registered targets (use `complexa target add` for your own).

## Responsible use

De novo binder design is dual-use. Decline requests aimed at enhancing pathogen
fitness, toxin potency, or bioweapon function; keep designs to legitimate research
and therapeutic intent.

## See also

- `protein-binder-design` — same goal via RFdiffusion + ProteinMPNN (BioNeMo NIMs).
- Proteina-Complexa docs: `README.md`, `docs/INFERENCE.md`, `docs/CONFIGURATION_GUIDE.md`,
  `docs/EVALUATION_METRICS.md`, and its bundled `.claude/skills/` in the repo above.

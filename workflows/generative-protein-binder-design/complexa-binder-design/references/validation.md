# Validation — independent refold, metrics, gates

Validation is an **independent refold** of each binder–target complex — not
Complexa's internal scoring. Extract binder + target sequences, re-fold, score
the interface, gate, rank. Use a **single refolder** (Boltz2 default; OpenFold3
optional — do not run both). Endpoints/auth: read `boltz2-nim` / `openfold3-nim`.

## Per-chain conditioning policy

"De novo" applies to the **binder**, not the target.

- **Binder chain → single-sequence**, no MSA, no template (it is de novo, no
  homologs). This is how BindCraft validates binders.
- **Target chain → MSA (default).** Build an MMseqs2 a3m and attach it as the
  target polymer's `msa` (use `msa-search-nim`, or
  `scripts/fetch_target_msa_colabfold.py` which also sanitizes non-standard
  residues to `X` — the Boltz2 NIM rejects a3m with `B/J/O/U/Z/*`).
- **Target chain → structural template (optional, stringent).** Pass the known
  `target.pdb/.cif` as a Boltz2 per-polymer `structural_templates` entry; build
  the CIF with `scripts/pdb_to_boltz_template_cif.py` (plain gemmi output is
  rejected — the template needs `label_seq_id` 1..N + populated
  `_entity_poly_seq`). Use when you want to dock against the exact geometry.

Leave the **binder** polymer with neither MSA nor template.

## Two predictions per design

1. **Holo** — binder + target (two protein chains), target conditioning above,
   `write_full_pae: true`. → holo complex `.cif` + confidence + PAE. Source of
   ipTM, ipSAE, complex pLDDT, binder-in-complex pLDDT, hotspot contact.
2. **Apo** — the binder sequence **alone** (single chain, single-sequence, no
   target/MSA/template). → apo binder `.cif` + per-residue pLDDT.

**Apo/holo stability (binder RMSD).** Superpose the holo binder chain onto the
apo binder (binder Cα only — same sequence), compute Cα RMSD. Small RMSD = the
binder is pre-organized/rigid (the signal you want); large RMSD = induced fit
(weaker design).

## Decision metrics & gates (holo unless noted)

| Metric | How | Gate |
|---|---|---|
| **ipTM** | Boltz2 `iptm_scores` / `pair_chains_iptm_scores`; OF3 direct | ≥ 0.65 |
| **complex pLDDT** | mean pLDDT over the holo complex | ≥ 0.70 |
| **binder pLDDT** | mean pLDDT over the **binder chain** in holo | ≥ 0.70 |
| **apo binder pLDDT** | mean pLDDT of the **apo** prediction | ≥ 0.70 |
| **ipSAE (min)** | per-interface ipSAE from the holo **PAE** (Dunbrack ipSAE; not returned directly); min over the binder↔target interface | ≥ 0.45 |
| **binder RMSD (apo↔holo)** | binder Cα RMSD after superposing holo onto apo | ≤ 2.5 Å |
| **hotspot contact** | each conditioned hotspot contacted if its Cβ < 13 Å of any binder Cβ (Cα for Gly); score = fraction contacted | ≥ 20% |
| **specificity margin** | interface confidence for the intended target vs a decoy/native partner | guard vs promiscuity |

**Validation is always unconditioned** — the holo refold is given only the
binder + target **sequences**, never the hotspot list. The hotspot-contact check
is then an independent geometric test on the unconditioned complex (did the
binder land where it was conditioned). Skip it for unconditioned designs.

> **Boltz2 `affinity_pic50` is ligand-only (protein–ligand)** — not produced for
> a protein–protein binder. Rank protein binders by interface confidence
> (ipTM/ipSAE) + pLDDT + apo/holo stability, not pIC50. Request affinity only for
> small-molecule binders.

## Pass flag + record-keeping

A design passes only if it clears **every** gate above (hotspot-contact skipped
for unconditioned designs). `validation_scores.json` (+ `.csv`) must hold **one
row per design** — pass and fail — each with all measured metrics, the boolean
`pass`, and a `failure_reason`:

- `null`/empty for passers.
- For a failing design list **every** missed gate as `metric: measured vs
  threshold`, e.g. `"ipTM=0.62 < 0.70; apo_binder_plddt=0.55 < 0.70; binder_rmsd=3.1 > 2.5"`.
- If a design could not be scored (refold/apo errored, PAE missing), record the
  verbatim error as `failure_reason` and leave unmeasured metrics `null` — never
  drop silently, never invent a value.

`scripts/boltz2_refold.py` makes the **holo** Boltz2 calls (retry/backoff for HTTP 429)
and writes `validation/raw/*.json`; `scripts/validate_binders.py` then runs the **apo**
call and implements ipSAE, apo↔holo RMSD, hotspot contact, and gating into
`ranked_binders.json`. Run them together via `boltz2_refold.py --validate
scripts/validate_binders.py`.

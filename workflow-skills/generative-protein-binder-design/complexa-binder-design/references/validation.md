# Validation - independent refold, metrics, gates

Validation is an **independent refold** of each binder-target complex - not
Complexa's internal scoring. Extract binder + target sequences, re-fold, score
the interface, gate, rank. Use a **single refolder** (Boltz2 default; OpenFold3
optional - do not run both). Endpoints/auth: read `boltz2-nim` / `openfold3-nim`.

## Per-chain conditioning policy

"De novo" applies to the **binder**, not the target.

- **Binder chain -> single-sequence**, no MSA, no template (it is de novo, no
  homologs). This is how BindCraft validates binders.
- **Target chain -> MSA (default).** Build an MMseqs2 a3m and attach it as the
  target polymer's `msa` (use `msa-search-nim`, or
  `scripts/fetch_target_msa_colabfold.py` which also sanitizes non-standard
  residues to `X` - the Boltz2 NIM rejects a3m with `B/J/O/U/Z/*`).
- **Target chain -> structural template (optional, stringent).** Pass the known
  `target.pdb/.cif` as a Boltz2 per-polymer `structural_templates` entry; build
  the CIF with `scripts/pdb_to_boltz_template_cif.py` (plain biotite output is
  rejected - the template needs `label_seq_id` 1..N + populated
  `_entity_poly_seq`). Use when you want to dock against the exact geometry.

Leave the **binder** polymer with neither MSA nor template.

## Two predictions per design

1. **Holo** - binder + target (two protein chains), target conditioning above,
   `write_full_pae: true`. -> holo complex `.cif` + confidence + PAE. Source of
   ipTM, ipSAE, complex pLDDT, binder-in-complex pLDDT, hotspot contact.
2. **Apo** - the binder sequence **alone** (single chain, single-sequence, no
   target/MSA/template). -> apo binder `.cif` + per-residue pLDDT.

**Apo/holo stability (binder RMSD).** Superpose the holo binder chain onto the
apo binder (binder CA only - same sequence), compute CA RMSD. Small RMSD = the
binder is pre-organized/rigid (the signal you want); large RMSD = induced fit
(weaker design).

## Decision metrics & gates (holo unless noted)

| Metric | How | Gate |
|---|---|---|
| **ipTM** | Boltz2 `iptm_scores` / `pair_chains_iptm_scores`; OF3 direct | >= 0.65 |
| **complex pLDDT** | mean pLDDT over the holo complex | >= 0.70 |
| **binder pLDDT** | mean pLDDT over the **binder chain** in holo | >= 0.70 |
| **apo binder pLDDT** | mean pLDDT of the **apo** prediction | >= 0.70 |
| **ipSAE (min)** | per-interface ipSAE from the holo **PAE** (Dunbrack ipSAE; not returned directly); min over the binder<->target interface | >= 0.45 |
| **binder RMSD (apo<->holo)** | binder CA RMSD after superposing holo onto apo | <= 2.5 Angstrom |
| **hotspot contact** | each conditioned hotspot contacted if its CB < 13 Angstrom of any binder CB (CA for Gly); score = fraction contacted | >= 20% |
| **specificity margin** | interface confidence for the intended target vs a decoy/native partner | guard vs promiscuity |

**Validation is always unconditioned** - the holo refold is given only the
binder + target **sequences**, never the hotspot list. The hotspot-contact check
is then an independent geometric test on the unconditioned complex (did the
binder land where it was conditioned). Skip it for unconditioned designs.

> **Boltz2 `affinity_pic50` is ligand-only (protein-ligand)** - not produced for
> a protein-protein binder. Rank protein binders by interface confidence
> (ipTM/ipSAE) + pLDDT + apo/holo stability, not pIC50. Request affinity only for
> small-molecule binders.

## Pass flag + record-keeping

A design passes only if it clears **every** gate above (hotspot-contact skipped
for unconditioned designs). `validation_scores.json` (+ `.csv`) must hold **one
row per design** - pass and fail - each with all measured metrics, the boolean
`pass`, and a `failure_reason`:

- `null`/empty for passers.
- For a failing design list **every** missed gate as `metric: measured vs
  threshold`, e.g. `"ipTM=0.62 < 0.65; apo_binder_plddt=0.55 < 0.70; binder_rmsd=3.1 > 2.5"`.
- If a design could not be scored (refold/apo errored, PAE missing), record the
  verbatim error as `failure_reason` and leave unmeasured metrics `null` - never
  drop silently, never invent a value.

`scripts/boltz2_refold.py` makes the **holo** Boltz2 calls (retry/backoff for HTTP 429)
and writes `validation/raw/*.json`; `scripts/validate_binders.py` then runs the **apo**
call and implements ipSAE, apo<->holo RMSD, hotspot contact, and gating into
`ranked_binders.json`. Run them together via `boltz2_refold.py --validate
scripts/validate_binders.py`, with explicit `--target-chain` and `--binder-chain`
from the input complexes and a ranked shortlist within `--max-designs` (default
20 for N=10). Never infer chain identity from A/B defaults. Prediction polymer
IDs retain these chain IDs; the validator uses mmCIF label IDs to match them.
The holo helper records source PDBs, the current batch ID, and remapped hotspots under `_refold` in each
raw JSON. Supply input-PDB author-numbered hotspots to the helper; it maps them
to prediction sequence positions. Missing residues/chains are explicit failures.

Failed holo calls and malformed inputs also have raw JSON records with
`failure_reason`; the validator exports them even when every holo call failed or
the ipSAE dependency is absent. No apo call is made for a failed holo. A refold
batch with any failed input returns nonzero after recording results. For legacy
raw JSON without `_refold`, pass verified chain IDs to the validator and use
prediction-numbered hotspots. Each helper invocation writes
`validation/refold_batch.json` **before predictions start**, listing the current
candidate names and a new batch ID. The validator scores only those candidates
and requires each raw response to match that ID. Missing/interrupted responses
produce failed rows; old candidate files cannot inflate the current pass count.
Starting a batch invalidates the previous JSON/CSV ranking tables until scoring
rebuilds them. Old raw files remain on disk for inspection. Use separate run/round
directories when preserving multiple batches as campaign evidence. Legacy raw
files without batch metadata retain their directory-based scoring behavior;
never mix legacy batches in one directory. A malformed batch record is an error,
and tagged responses without their batch record cannot be scored as current.

Ranking is passers first, then descending ipTM and ipSAE_min. Missing or non-finite
gate metrics never pass, and unequal apo/holo binder lengths cannot produce a
truncated RMSD. A cached apo with a different sequence also fails; regenerate it
for the current binder. The report keeps failed and unmeasured designs visible
with NO-GO.

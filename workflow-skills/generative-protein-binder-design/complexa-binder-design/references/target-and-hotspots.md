# Stage 1 — target structure + hotspots (detailed)

Automated, no-GPU. Implemented in `scripts/pipeline.py` (resolution + alignment +
prune + crop), `scripts/hotspot_strategy.py` / `scripts/pdb_interface.py` (hotspot
evidence), and surfaced by `scripts/preflight_design.py`. Always run the preflight and
review before spending GPU.

## 1. Resolve exactly one design-ready structure

Try sources **in priority order**; use the first that yields a usable structure:

| # | Source | When |
|---|---|---|
| 1 | **Experimental PDB** | a design-ready RCSB entry exists (`https://files.rcsb.org/download/XXXX.pdb`) |
| 2 | **AFDB** | no usable PDB → resolve UniProt accession → fetch the AlphaFold model |
| 3 | **User file** | the user hands you a `.pdb`/`.cif` |
| 4 | **Fold de novo** | none of the above → MSA-Search + OpenFold3/Boltz2 |

Free-text names resolve to a UniProt accession with the vendored `uniprot_database`
skill (`vendor/science-skills/uniprot_database`); AFDB fetch uses
`vendor/science-skills/alphafold_database_fetch_and_analyze/scripts/fetch_structure.py`.
Resolution prefers reviewed (Swiss-Prot) entries (which have AFDB models), human first,
but works across organisms (allergens, viral, …). A typed UniProt accession or 4-char
PDB ID is accepted directly.

## 2. Define hotspots (evidence-based, accessibility-aware)

Hotspots are the **target residues the binder should contact** — a compact,
surface-exposed, binder-accessible epitope. `hotspot_strategy.resolve_hotspots()`
resolves them in this order, every candidate restricted to the accessible surface:

1. **UniProt functional (trusted default)** — `Mutagenesis` residues with a
   binding/interaction effect, plus `Active/Binding/Site` **only when accessible**.
   A binder can only reach the **extracellular topological domain** of a membrane
   protein, so candidates are filtered to it and the target is cropped to that region.
   Catalytic/intracellular pockets (e.g. HER2 kinase ATP site, IL1R1 cytoplasmic TIR)
   are dropped — they are the wrong surface for a binder.
2. **PDB co-complex interface (fallback + review)** —
   `pdb_interface.interface_hotspots`: from the target's PDB cross-references, find a
   structure where the target chain contacts a protein partner, compute interface
   residues (≤ 5 Å heavy-atom), map PDB→UniProt by alignment. Review for crystal/
   non-biological contacts.
3. **Paperclip literature** — full-text mining (alanine scans, ΔΔG, co-crystal
   contacts) when 1–2 are empty; see `prompts/hotspot_paperclip.md`. The structure is
   the ground-truth filter (auto-corrects literature↔structure numbering offsets).
4. **No supported epitope** — stop and obtain evidence-based hotspots before a
   conditioned campaign. Unconditioned exploration does not receive READY status.

This order is for automatic name/accession resolution. A supplied co-complex with
an explicitly requested partner interface uses that structure directly after
reviewing its contacts; honor user-specified epitopes rather than replacing them
with functional annotations from another source. This matches `SKILL.md` and the
shared `prepare_design_target()` in `pipeline.py`. With multiple protein partners,
choose exactly one with `--partner-chain`; pooling contacts across partners is not
allowed. Explicit `--hotspots` bypasses automatic interface selection.

## 3. Align to the structure (the ordering guarantee)

`align_hotspots_to_structure()` keeps only residues present in the coordinate file and
fills in the actual 3-letter identity from coordinates. **Beware UniProt→PDB numbering
mismatch:** PDB constructs are often truncated/engineered with author numbering offset
from UniProt. Always express hotspots in the numbering of the coordinate file the
designer consumes, verify the residue identity there, and **use whatever chain ID the
file actually uses** (often `A`, but read it — never assume).

Hotspot format consumed by Stage 2:

```json
[ { "chain": "A", "residue": "ILE", "position": 37 },
  { "chain": "A", "residue": "TYR", "position": 39 } ]
```

## 4. Keep one compact epitope (prune)

`_prune_hotspots()` enforces (a binder grips one local patch):

- **Pairwise compactness ≤ 30 Å** — grow a patch from the densest hotspot
  neighbourhood; each Cβ (Cα fallback) must be within 30 Å of every other member.
- **Count ≤ 15** — keep the 15 closest to the centroid.
- **Count ≥ 1** — one anchor is accepted; prefer at least two supported hotspots.

If a target has two distal patches, design a **separate binder per patch**.

## 5. Size budget — binder + target ≤ 500 residues

Complexa builds an O(n²) pair-feature map over the whole complex, and the AF2-Multimer
reward (JAX) preallocates a large GPU slice. `_crop_target_to_epitope()` crops an
oversized target to a contiguous window in **observed residue order**, centered on
the epitope and **preserving original residue numbering**. Gaps in author numbers
do not consume the residue budget. The crop retains all anchors when their
observed sequence span fits; a genuinely larger span fails the retention check.
With the default binder range (64–155), the target must be ≤ 345 residues. Preparation
first extracts only the selected target protein chain and applies any accessible
segments, so partner size never changes the crop or target registration. It measures
the actual cropped file and checks that every selected hotspot survives. A failed
budget/retention check or an empty hotspot set blocks full-mode generation.

## 6. Preflight (no GPU)

```bash
python scripts/preflight_design.py <name|accession> [<name> ...]
python scripts/preflight_design.py complex.pdb --chain B --partner-chain A --out prepared
```

Per target it reports the conditioned length, re-aligned hotspots + their source,
compactness (Å), the ≤ 500 size budget, the count, and a **READY / NEEDS ATTENTION**
verdict. `--out` takes exactly one target and preserves the files after preflight
exits. Without it the command is a preview. Review here before launching generation.

**Stage 1 output:** `target_prepared.pdb` (selected target chain, actual crop),
`hotspots.json` (final residues + partner/evidence metadata), and `preflight.json`
(checks + absolute artifact paths). The same preparation runs in `pipeline.run()`;
from an original co-complex, pass the same `chain` and `partner_chain`, or pass the
saved target file and hotspot JSON together. Registration and MSA/validation
handoffs use the prepared geometry. See `pipeline.md` for the generation handoff.

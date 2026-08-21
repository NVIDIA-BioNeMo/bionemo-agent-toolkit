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
2. **PDB co-complex interface (gold standard, fallback + review)** —
   `pdb_interface.interface_hotspots`: from the target's PDB cross-references, find a
   structure where the target chain contacts a protein partner, compute interface
   residues (≤ 5 Å heavy-atom), map PDB→UniProt by alignment. Review for crystal/
   non-biological contacts.
3. **Paperclip literature** — full-text mining (alanine scans, ΔΔG, co-crystal
   contacts) when 1–2 are empty; see `prompts/hotspot_paperclip.md`. The structure is
   the ground-truth filter (auto-corrects literature↔structure numbering offsets).
4. **Unconditioned** (`[]`) — documented last resort.

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

- **Compactness ≤ 30 Å** — drop hotspots whose Cβ is > 30 Å from the densest cluster
  centroid (removes distal outliers on other domains).
- **Count ≤ 15** — keep the 15 closest to the centroid.
- **Count ≥ 2** — a single residue is too weak to define an epitope.

If a target has two distal patches, design a **separate binder per patch**.

## 5. Size budget — binder + target ≤ 500 residues

Complexa builds an O(n²) pair-feature map over the whole complex, and the AF2-Multimer
reward (JAX) preallocates a large GPU slice. `_crop_target_to_epitope()` crops an
oversized target to a contiguous window centered on the epitope, **preserving original
residue numbering** so hotspot ids and downstream Boltz2/OpenFold3 numbering stay valid.
With the default binder range (64–155), the target must be ≤ ~345 residues. With no
hotspots there is no epitope to center on (it falls back to the first N residues with a
warning) — supply hotspots.

## 6. Preflight (no GPU)

```bash
python scripts/preflight_design.py <name|accession> [<name> ...]
```

Per target it reports the conditioned length, re-aligned hotspots + their source,
compactness (Å), the ≤ 500 size budget, the count, and a **READY / NEEDS ATTENTION**
verdict. Review here before launching generation.

**Stage 1 output:** `target.pdb` (single structure, possibly `target_cropped.pdb`) +
`hotspots.json` (the residue list). For an unconditioned design, pass `[]`.

# Hotspot fallback — Paperclip full-text literature search

Use this prompt **only when UniProt has no usable hotspot features** for the
target (no `Active site` / `Binding site` / `Site` / `Mutagenesis` / disease
`Natural variant`). This is common for receptors, cytokines, and other
non-enzymes whose functional surface is a **protein–protein interaction
epitope**, not a catalytic pocket — exactly the kind of site a binder should
grip, and exactly what UniProt rarely annotates.

This is a **single, narrow job** — not bindclaw's 7-set hypothesis sweep. Produce
**one** evidence-grounded hotspot set, residue-level, and make every residue
**coordinate-valid in the structure the designer will actually consume**.

## Tool — the `paperclip` CLI (drive it exactly as bindclaw does)

Paperclip searches 8M+ full-text papers (PMC, bioRxiv, medRxiv). Its advantage
over abstract search: it can read **alanine-scanning tables, mutagenesis Results
sections, ΔΔG values, and co-crystal contact lists** where residue numbers live.
It is a **CLI** (`gxl_paperclip`); shell out to it (the `/paperclip` Claude Code
skill wraps the same commands).

**Install (one-time, Python 3.8+):**
```bash
curl -fsSL https://paperclip.gxl.ai/install.sh | bash   # → wrapper at ~/.local/bin/paperclip
# or:  pip install https://paperclip.gxl.ai/paperclip.whl && paperclip setup
paperclip login        # sign in (also happens automatically on first use)
paperclip config       # verify: Server https://paperclip.gxl.ai, Auth ✓ <you>
```

Core commands:

```bash
paperclip search "<3-6 word query>" -n 5      # → result set id  s_xxxxxxxx
paperclip map --from s_xxxxxxxx "Extract ALL specific residue numbers involved \
  in binding, mutagenesis, or hot spots; include ΔΔG values if present."
paperclip grep -i "<residue|mutagenesis|contact>" /papers/<paper_id>/content.lines
paperclip cat  /papers/<paper_id>/meta.json    # title, authors, doi for citation
```

`search` returns paper IDs (`PMC*` / `bio_*` / `med_*` / `arx_*`) and a result-set
id; `map --from <set>` extracts structured answers across the whole set; `grep`/`cat`
read individual papers' full text. If the `paperclip` CLI is unavailable or not
signed in (`paperclip login`), fall back to `WebSearch` over the same query shapes
and cite URLs instead.

## Inputs you are given

- Target name + UniProt accession.
- The resolved design structure: `target.pdb` / `target.cif`, **its chain ID**,
  and **its observed residue range** (e.g. AFDB full-length `A1-350`, or a
  cropped construct `X282-382`). Read these from the file — do not assume.

## Procedure (keep it short — ≤ ~6 searches)

1. Identify the target's known binding partner / drug / epitope from 2–3
   short `paperclip search` queries (2–4 keywords each; long queries return
   nothing):
   - `paperclip search "<name> binding site residues mutagenesis" -n 5`
   - `paperclip search "<name> alanine scanning hot spot" -n 5`
   - `paperclip search "<name> crystal structure interface contact" -n 5`
2. Extract **specific residue numbers** verbatim with `paperclip map --from
   s_xxx "..."`, then `paperclip grep`/`cat` the most promising papers to read
   the Results/Methods tables. Capture ΔΔG when given.
3. **Align every residue to the resolved structure** (this is mandatory — see
   below). Drop or remap anything outside the structure's range/chain.
4. Write the two output files. Do not narrate first; just write.

## Alignment to the structure (the "ordering" rule — do not skip)

Literature residue numbers are almost always in **UniProt canonical
numbering**. The structure the designer consumes may be renumbered or cropped:

- **AFDB model** → numbering == UniProt, full length. A literature position `N`
  maps to `chain{N}` only if `N` is within the model's range.
- **Experimental PDB / cropped construct** → author numbering (`auth_seq_id`)
  is often **offset**, with gaps. A UniProt position is **not** the same number
  in the PDB. Map by aligning the UniProt sequence to the structure's observed
  sequence (SIFTS or a pairwise alignment) — never by equal indices.

For **every** proposed residue:
- confirm `(chain, position)` exists in the coordinate file, and
- confirm the **residue identity** reads back as expected (a literature
  "Tyr123" must be `TYR` at the mapped residue, not assumed).

A low-confidence but **coordinate-valid** epitope residue beats a
high-confidence residue that is **absent** from the design structure. Mark any
off-structure evidence as such and choose a valid alternative.

> The downstream pipeline re-checks this deterministically
> (`pipeline.align_hotspots_to_structure`): residues not present in the
> structure are dropped with a warning, so off-structure positions are wasted
> work — align them here.

## Outputs (write both)

`hotspots.json` — the format the pipeline + Stage 2 consume (same as the
UniProt path), in the **structure's** numbering and chain:

```json
[
  { "chain": "A", "residue": "TYR", "position": 123,
    "source": "paperclip", "evidence": "PMC9064197: Ala scan ΔΔG 5.2 kcal/mol" },
  { "chain": "A", "residue": "LYS", "position": 124,
    "source": "paperclip", "evidence": "<PDBID> co-crystal contact" }
]
```

`hotspots.txt` — human-readable: each residue with its paper/PDB citation, the
mechanism in 1–2 sentences, and an explicit note on how numbering was mapped to
the structure. State residue count and overall confidence.

## Rules

- ≥ 3 residues with real, cited position numbers; they should form a spatial
  cluster (≤ ~15 Å span) so conditioning is geometrically meaningful.
- **Never fabricate** residue numbers, PMIDs/PMC IDs, or PDB entries. If you
  cannot find specific numbers, say so, set confidence `low`, and hand back to
  the caller (options: structural surface-patch heuristic, ask the user, or
  proceed **unconditioned** with `[]` and document it) — do not invent hotspots.

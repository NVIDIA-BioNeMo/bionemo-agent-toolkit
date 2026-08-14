# Vendored: google-deepmind/science-skills (Stage-1 target + hotspot tooling)

Two DeepMind skills are vendored to make pipeline **Stage 1** executable in this
repo: resolve a target structure from AFDB and read UniProt features for hotspots.

| | |
|---|---|
| **Source** | https://github.com/google-deepmind/science-skills |
| **Retrieved** | 2026-06-11 (raw from `main`) |
| **License** | Apache-2.0 (see `LICENSE` in this directory) |
| **Skills** | `alphafold_database_fetch_and_analyze/`, `uniprot_database/` |

## What each provides

- `alphafold_database_fetch_and_analyze/scripts/fetch_structure.py` — UniProt ID
  → AFDB model (mmCIF, pLDDT in B-factor) + PAE JSON + metadata, via the AFDB
  prediction API (`/api/prediction/<acc>`, which resolves the current model
  version — the legacy `…model_v4.cif` path is stale; models are now v6).
- `alphafold_database_fetch_and_analyze/scripts/analyze_plddt.py`,
  `analyze_pae.py` — confidence / domain-boundary analysis. **Unmodified**;
  pure stdlib (`dependencies = []`), run with `python3` directly.
- `uniprot_database/scripts/uniprot_tools.py` — `get`/`search`/`map`/`count`/
  `sparql`/`stream` over UniProtKB; `get <ACC>` returns the full entry incl.
  `features` (Active site / Binding site / Site / Mutagenesis / …) used to seed
  hotspots.

## Modifications (Apache-2.0 §4: changes are stated in-file)

The upstream scripts depend on an internal `scienceskillscommon.http_client`
package installed via `uv` inline-script metadata. To run standalone here with
**no `uv` and no extra packages**, in `fetch_structure.py` and `uniprot_tools.py`:

- the `# /// script … ///` `uv` block and the
  `from science_skills…scienceskillscommon import http_client` import were removed;
- a small **stdlib-`urllib` shim** was added (same `HttpClient.fetch` /
  `fetch_json` / `fetch_bytes` / `stream_lines`, `HttpResponse`, `HttpError`
  interface), aliased as `http_client` so the rest of each file is unchanged.

All AFDB / UniProt query logic is otherwise upstream-verbatim. Each modified file
carries a `# MODIFIED for bionemo-nim-skills` note. `analyze_*.py` are verbatim.

## Structural changes

Upstream ships each skill with a top-level `SKILL.md`. Here they are vendored as
**libraries** (only their `scripts/*.py` are imported — nothing reads the manifest),
so each `SKILL.md` was renamed to `README.md`. The skills catalog treats any
directory with a `SKILL.md` as its own skill root, and a skill may not contain
another skill; the rename keeps this directory a single atomic skill.

**When re-vendoring:** after copying from upstream, rename each nested
`SKILL.md` → `README.md` (or drop it) before committing, or the nested
resource-root check will fail again.

## Verified (2026-06-11)

- `fetch_structure.py P04637 -o …` and `P00533 -o …` → downloaded v6 cif + PAE.
- `uniprot_tools.py get P00533` → 321 features; hotspot candidates Asp837
  (Active site) + ATP-pocket Binding sites.
- AFDB numbering == UniProt numbering (AFDB res 837 = ASP837), so UniProt
  feature positions map onto the AFDB model directly; verify identity in the cif.
  Experimental PDBs (RCSB) still need SIFTS/alignment remapping.

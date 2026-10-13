---
name: protein-binder-design
description: >
  Use when designing RFdiffusion/ProteinMPNN binders or validating and resuming binder campaigns. Not for code or report review.
license: Apache-2.0
compatibility: "Python>=3.12 with requirements.txt; Bash for hosted_env.sh"
metadata:
  author: "NVIDIA BioNeMo <bionemofeedback@nvidia.com>"
  tags: [protein-design, binder-design, bionemo]
allowed-tools: Bash, Read, Write, AskUserQuestion
permissions:
  - env      # reads NVIDIA_API_KEY/NGC_API_KEY and configured NIM endpoints
  - network  # calls hosted NVIDIA APIs or user-configured local NIM endpoints
---

# Protein Binder Design (workflow)

## Purpose

Run a de novo binder design campaign by composing atomic NIM skills. This skill
owns orchestration, handoff contracts, filtering, validation, and the run
manifest. For per-NIM API details, consult the corresponding NIM skill.

Use for requests such as “design protein binders”, “run an RFdiffusion campaign”,
“validate and rank these binders”, or “resume this binder manifest”. A request to
review code, explain methods, or inspect an evaluation report does not start a
design campaign. Offline bookkeeping stays offline.

## Prerequisites

- Python 3.12+; install [requirements.txt](requirements.txt) for RMSD, mmCIF,
  cache recovery, and Python HTTP examples. Manifest and PDB-only helpers use
  the standard library. Install [requirements-dev.txt](requirements-dev.txt)
  to run `python3 -m pytest tests` with coverage.
- Live inference needs hosted NIM credentials or reachable local NIM services;
  local deployment also needs Docker, the NVIDIA Container Toolkit, and a
  supported GPU. See Configuration below and [local setup](references/local-nim-setup.md).

## Inputs

Required inputs from the user prompt or saved manifest: target structure/sequence,
target chain, epitope/hotspots, binder length range, backbone/sequence counts,
output directory, and hosted or local endpoints. Resolve the confidence
selection policy before live inference. Resume requests require the saved
manifest and artifacts; offline imports require a synthetic score fixture or
cache bindings as defined in [offline contracts](references/offline.md).
Optional inputs include a target MSA, sourced positive controls, and explicit
overrides to the default selection thresholds.

Apply the user's explicit corrections first. Otherwise preserve saved campaign
settings, then use supplied task context; ask only for unresolved inputs. Record
intentional changes to saved settings so resumed results remain interpretable.

## Data handling

Hosted mode sends target structures/sequences, candidate sequences, and any
requested alignments to the selected NVIDIA NIM endpoints under that service's
terms. Use the user's selected deployment; resolve the destination before
uploading data if it is unspecified. Local mode sends inference inputs to the
configured local service; initial image/weight downloads still contact NGC.
All modes write JSON/CSV and, when produced, PDB/mmCIF/FASTA artifacts under the
chosen run directory. Keep credentials out of those artifacts and logs.

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
scores, or an interrupted run. An empty CSV alone does not establish a completed
campaign; report which stages ran and their saved artifacts.

### Offline inputs

For a synthetic fixture with `target` and `profiles`, run
`python3 scripts/offline_bookkeeping.py /path/to/bookkeeping.json --output-dir /path/to/output`.
This saves and reloads each manifest, writes both CSVs and `summary.json`, and
reports missing scores and provisional counts in one call. For an interrupted
synthetic run with saved responses, use
`python3 scripts/refold_cache.py /path/to/manifest.json --output-dir /path/to/new-run`.
Read [offline contracts](references/offline.md) for cache bindings, sample
selection, chain confidence and blocked work. These helpers need no credentials
and make no model calls. Inspect exit status and saved artifacts before claiming
completion; a failed command followed by a successful retry is recovered
execution, with both attempts retained as evidence.

### Pipeline

1. **Target prep** — get the target PDB + epitope; map epitope/hotspot author
   residue numbers to RFdiffusion `hotspot_res` strings; optionally build a
   target MSA with `msa-search-nim`.
2. **Backbones** (`rfdiffusion-nim`) — binder contig + `hotspot_res`; N backbones.
3. **Sequences** (`proteinmpnn-nim`) — k sequences per backbone; drop the
   native/WT row from `mfasta`.
4. **Co-fold + score** (`boltz2-nim` / `openfold3-nim`) — co-fold binder+target;
   collect explicit ipTM or Boltz2 composite confidence, plus binder pLDDT.
5. **Self-consistency** — CA-RMSD between the RFdiffusion backbone and the
   predicted binder (`scripts/metrics.py`).
6. **Filter + rank** — apply the saved campaign thresholds, exclude controls,
   sort surviving designs, and export that exact list (see below).

Full handoff contracts, branching, and the cost funnel: `references/pipeline.md`.

### Filter, rank, and export

For `m` returned by `Manifest.create()` or `Manifest.load()`, use this sequence
after scoring. Keep the supplied filters, ranking metric, scores, and control
flags unchanged:

```python
from pathlib import Path

m.apply_filters()
rank_by = m.data["params"].get("rank_by", "iptm")
ranked = m.rank(by=rank_by, descending=True, passed_only=True, include_controls=False)
run_dir = Path(m.data["run_dir"])
m.to_csv(run_dir / "all_candidates.csv")       # complete audit, including controls
m.to_csv(run_dir / "candidates.csv", candidates=ranked)
print(m.summary())                           # controls excluded from candidate/pass counts
print([candidate["id"] for candidate in ranked])
```

`rank()` returns a new list; it does not reorder or shrink the manifest.
`to_csv()` without `candidates=ranked` writes **all** entries in insertion order.
Pass an empty ranked list through unchanged: zero survivors means a header-only
`candidates.csv`, while the audit CSV and manifest retain every entry. A high
ranking score cannot override a failed or missing enabled filter metric. Report
missing scores and label the passing fraction provisional when scoring is incomplete.

## Handoff contracts (the fragile glue)

- RFdiffusion `output_pdb` → ProteinMPNN `input_pdb` (inline PDB text).
- ProteinMPNN `mfasta` → Boltz2 binder polymer `sequence` (exclude the
  native/WT row; pair scores only with designed rows).
- Epitope author residue numbers → 1-based sequence indices: remap with
  `scripts/pdb_utils.py:remap_to_seq_index`. RFdiffusion `hotspot_res` uses
  chain+author strings like `"A50"`; Boltz2 pocket/contacts use 1-based indices.
  Keep insertion IDs distinct (`50` versus `50A`), select the target chain/model,
  and block absent hotspots instead of substituting nearby residues. Verify
  downstream support before requesting an insertion-coded hotspot.
- Boltz2 complex `.cif` → binder chain → self-consistency RMSD vs the backbone.
  Use the same saved sample for confidence and coordinates; mmCIF request polymer
  IDs are label chain IDs. Whole-complex pLDDT does not supply binder-only pLDDT.

## Output Format

Every campaign writes `manifest.json` (+ `candidates.csv`) under a run dir via
`scripts/manifest.py`. It records lineage, params, scores, artifacts, filter
status, and controls — enabling ranking, resumability, validation, and the
final report. Schema and usage: [manifest contract](references/manifest.md).
Keep all entries in `all_candidates.csv`; `candidates.csv` contains only ranked
survivors and retains its header when none pass. Offline helpers also write
`summary.json`. The final response identifies the mode, completed/blocked stages,
artifact paths, selection thresholds, ranked IDs, and missing scores. Report
control counts separately and mark an incomplete passing fraction provisional.

## Filters (defaults)

- ipTM ≥ 0.8, binder pLDDT ≥ 80, self-consistency RMSD ≤ 2.0 Å.
- Override per campaign and record overrides in the manifest `filters`.
- Every applicable enabled metric needs a finite score to pass. Sequence-only
  controls have no designed backbone: their RMSD is not applicable and the manifest
  records that exemption; design candidates still require RMSD. Keep a composite confidence
  value in its own field; do not substitute it for an unavailable ipTM.
- For Boltz2-only campaigns without explicit ipTM, resolve the composite
  confidence cutoff before inference. Set `iptm_min: null`, enable
  `boltz2_confidence_min` with that cutoff, retain the pLDDT/RMSD thresholds,
  and save `params.rank_by: boltz2_confidence`. Filter with `apply_filters()`,
  rank with `rank(by="boltz2_confidence", passed_only=True)`, and export that
  list with `to_csv(candidates=ranked)`. Report this as composite-confidence
  selection; it does not establish the default ipTM criterion. Complete example:
  `references/manifest.md`. **Default decision when no cutoff was supplied:** use
  a refolder that returns explicit ipTM (OpenFold3) and the default ipTM profile.
  If only composite-confidence Boltz2 is available, obtain a campaign cutoff and
  its rationale from the user or a separate same-target calibration before design
  inference. Save it in `params.confidence_selection`. Without either, stop at
  input preparation and report `selection_policy_unresolved`; do not guess 0.8
  or present unfiltered rankings as validated binders. Calibration procedure:
  `references/validation.md`.

## Validation

Run scrambled controls and report a **success rate**, not just top scores.
Negative controls via `scripts/controls.py` (scrambled sequences); positive
controls = sourced published binders re-scored through the same pipeline. The
bundled `assets/targets.json` is an empty control template, not a positive-control
dataset. Use user-provided sequences with citations, or retrieve and verify an
exact sequence from a primary publication or structure before registering it.
If none is available, record `positive_controls_unavailable`, complete the
computational screen with negatives, and label it **uncalibrated screening**;
do not claim positive-control benchmarking or calibrated binder success. A
request requiring a benchmark remains incomplete until a positive is supplied.
Methodology and
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
  Run **each delegated hosted command** through the credential wrapper:
  `bash scripts/hosted_env.sh python3 your_nim_request.py`.
  Use the helper's absolute path when running outside the skill directory.
  It exports the selected key as `NGC_API_KEY`, which the atomic NIM skills read,
  preserves an existing nonempty `NGC_API_KEY`, and stops before launching the
  child if neither key exists. The wrapper loads the key and executes the command
  in one invocation, so no exported state from a previous tool shell is needed.
  It disables shell tracing and preserves arguments and the child's exit code.
- **Local** (self-hosted NGC containers): point each NIM at its local URL
  (e.g. `http://localhost:8000/...`); local NIMs need no auth header. Follow
  [local setup](references/local-nim-setup.md) for digest-pinned images, private
  cache mounts, loopback ports, readiness checks, and GPU-specific profile selection.

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
- **Resume:** call `Manifest.load("runs/<campaign>")` and
  `missing_scores(candidate_id)`; use the artifact checklist in
  `references/manifest.md` to execute only missing stages. A finite below-threshold
  score is complete, not a reason to repeat inference. Reuse saved predictions
  for missing metrics; preserve completed candidates and explicit failure records.

## Available Scripts

Paths below are relative to this skill. Run CLIs with `python3 scripts/<name>.py`
or `bash scripts/hosted_env.sh`; import library helpers after adding the skill's
`scripts` directory to the Python import path. No harness-specific runner is required.

| Script | Purpose | Arguments |
|---|---|---|
| [offline_bookkeeping.py](scripts/offline_bookkeeping.py) | CLI: import synthetic score profiles | `input.json --output-dir DIR` |
| [refold_cache.py](scripts/refold_cache.py) | CLI: recover metrics from verified cache bindings | `manifest.json --output-dir DIR` |
| [metrics.py](scripts/metrics.py) | CLI/library: binder CA-RMSD | `backbone.pdb prediction.cif --backbone-chain A --predicted-chain B` |
| [hosted_env.sh](scripts/hosted_env.sh) | Credential wrapper | `COMMAND [ARG ...]` |
| [manifest.py](scripts/manifest.py) | Library: save, filter, rank, export | `Manifest.create(run_dir, target, mode, params, filters)` / `Manifest.load(path)` |
| [pdb_utils.py](scripts/pdb_utils.py) | Library: select chain and remap residues | `remap_to_seq_index(pdb_text, chain, author_resnums)` |
| [controls.py](scripts/controls.py) | Library: composition-preserving negative controls | `make_scrambled_controls(seqs, n=5, seed=0)` |
| [registry.py](scripts/registry.py) | Library: load a user-populated target registry | `get_target(name, path=None)`; default is the empty `assets/targets.json` template |

## Limitations

Confidence thresholds and scrambled controls provide computational screening,
not experimental proof of binding. The target registry contains no verified
positive controls. Boltz2 composite confidence is distinct from ipTM. Cached
synthetic fixtures test bookkeeping, not model performance or biological validity.

## Troubleshooting

| Error or symptom | Cause | Resolution |
|---|---|---|
| Missing NIM key | Neither supported key is set | Configure the selected hosted credential or use an available local service |
| `selection_policy_unresolved` | No explicit ipTM or calibrated composite cutoff | Resolve the refolder/cutoff before design inference |
| Absent hotspot or chain | Author numbering/chain differs from input | Inspect the selected model and insertion codes; supply the correct residue IDs |
| Cache binding/digest failure | Response identity or bytes do not match | Keep the failed candidate visible; obtain matching artifacts before retrying |
| No ranked survivors | Enabled metric missing or below threshold | Inspect the audit CSV; retain the empty ranking and disclose incomplete scoring |
| Missing Python module / tests cannot collect | Helper or test dependencies absent | Install the appropriate requirements in the same Python environment used to run the command |

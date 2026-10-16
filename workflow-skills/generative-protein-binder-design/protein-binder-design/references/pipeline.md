# Binder Design Pipeline — Orchestration & Handoff Contracts

This is the detailed orchestration for the `protein-binder-design` workflow.
The agent reasons over these steps and delegates each NIM call to the atomic
skill. Deterministic glue (parsing, remapping, RMSD, manifest) uses the bundled
`scripts/`.

## 0. Setup

- Reuse an existing hosted/local choice, or resolve it once if unspecified.
- For hosted calls, read `NGC_API_KEY` or `NVIDIA_API_KEY` from the environment
  and stop if neither is set. Do not substitute the agent's `OPENAI_API_KEY` or
  print environment variables or authorization headers.
- Wrap every hosted command:
  `bash scripts/hosted_env.sh python3 your_nim_request.py` (use the helper's
  absolute path outside the skill directory). This exports the chosen key as
  `NGC_API_KEY` for RFdiffusion, ProteinMPNN, Boltz2, OpenFold3, and optional MSA
  subprocesses. The wrapper selects credentials and launches the command together;
  it works in a fresh tool shell and disables tracing. Local
  inference uses no authentication header and does not need this helper.
- Create a run directory and manifest:

```python
import sys; sys.path.insert(0, "scripts")
from manifest import Manifest
m = Manifest.create(
    run_dir="runs/<target>_<date>",
    target={"name": "<target>", "pdb_id": "<PDBID>", "chain": "<C>"},
    mode="hosted",
    params={"n_backbones": 100, "seqs_per_backbone": 8, "binder_len": "60-90", "rank_by": "iptm"},
)
```

Before inference, select the scoring route. The default is a refolder returning
explicit ipTM (OpenFold3) with the manifest's default filters. For Boltz2-only
output without ipTM, require a user-selected or separately calibrated confidence
cutoff and its rationale first (`references/validation.md`). Save that decision:

```python
m.data["filters"].update(iptm_min=None, boltz2_confidence_min=campaign_cutoff)
m.data["params"]["rank_by"] = "boltz2_confidence"
m.data["params"]["confidence_selection"] = {"source": cutoff_source, "rationale": cutoff_rationale}
m.save()
```

This retains the pLDDT/RMSD criteria. The complete Boltz2 manifest example is in
`references/manifest.md`; reuse its saved filters and ranking metric on resume.
If no justified cutoff or explicit-ipTM refolder is available, stop before design
inference with `selection_policy_unresolved`. Never use the synthetic example's
cutoff as an implicit scientific default.

### Request failures and partial batches

Use the atomic skill's request client with an explicit per-request timeout (up
to 1200 seconds for inference), at most three retries for HTTP 429/5xx, and bounded
backoff (10, 20, 40 seconds; honor Retry-After up to 120 seconds). Count retries
against the campaign's call/time budget and stop when it is exhausted. A timed-out
generation POST may have run remotely: query its returned job ID if available;
otherwise record `outcome_unknown` and require an explicit retry decision to avoid
duplicate generation charges. Do not retry HTTP 400/401/403 unchanged.

Save each successful response and update its candidate before the next request.
On exhausted errors, set `failure_reason`, log the failed stage and attempt count
with `m.log_stage()`, and continue independent candidates within the budget. Never
fill missing scores with zeros or drop failed candidates from the denominator.
Abort the batch on missing/invalid credentials. Reuse successful artifacts on
resume; retry failed calls only after the cause or retry decision is recorded.

## 1. Target prep

- Obtain the target structure (experimental PDB, or predict with `openfold2-nim`
  / `openfold3-nim` / `boltz2-nim` if none exists).
- Identify epitope/hotspot residues (from literature, the registry, or the user)
  in **PDB author numbering**.
- Remap to 1-based sequence indices for tools that need them:

```python
from pdb_utils import remap_to_seq_index
target_pdb = open("<target>.pdb").read()
seq_idx = remap_to_seq_index(target_pdb, chain="<C>", author_resnums=[<epitope author resnums>])
```

- RFdiffusion `hotspot_res` instead uses chain+author strings, e.g.
  `["E453", "E455", "E456", "E486"]` (no remap needed there).
- Preserve insertion codes and sparse author numbering: `501` and `501A` are
  distinct residues. Missing author IDs block the handoff. Verify endpoint
  support before requesting an insertion-coded hotspot. Select the target
  chain, one model and one alternate CA location per residue.
- Optional: build a target MSA with `msa-search-nim` if you will fold/co-fold
  the target with evolutionary context.

### Human-in-the-loop gate
Before generating backbones, resolve any missing target chain, epitope/hotspot
set, binder length range, number of backbones, or sequences per backbone. Treat
the user's supplied choices as resolved; ask only for missing values or a
proposed change in campaign scope or deployment.

## 2. Backbones — `rfdiffusion-nim`

Binder design mode: pass the target `input_pdb`, a contig combining the target
segment and a generated binder segment, and `hotspot_res`.

```python
# delegate the actual request to the rfdiffusion-nim skill
payload = {
    "input_pdb": target_pdb,
    "contigs": "E1-200/0 60-90",        # keep target E1-200, chain break, generate 60-90 aa binder
    "hotspot_res": ["E453", "E455", "E456", "E486", "E489", "E493", "E501"],
    "diffusion_steps": 50,
}
# -> result["output_pdb"] is one backbone
```

Generate N backbones (loop with distinct seeds / repeated calls). Save each and
register it:

```python
m.upsert_candidate("bb003", backbone_id="bb003")
m.add_artifact("bb003", "backbone_pdb", "runs/.../backbones/bb003.pdb")
```

## 3. Sequences — `proteinmpnn-nim`

For each backbone, design k sequences. Redesign the **binder chain only**
(`input_pdb_chains=[binder_chain]`) so the target chain stays fixed. RFdiffusion
may renumber/rename chains, so re-read the backbone PDB to get the binder chain
ID and length first (`pdb_utils.py`). **Drop the native/WT row** from `mfasta`
and pair scores only with designed rows.

```python
payload = {
    "input_pdb": backbone_pdb,
    "input_pdb_chains": [binder_chain],   # redesign binder, keep target fixed
    "num_seq_per_target": 8,
    "sampling_temp": [0.1, 0.2],
    "use_soluble_model": True,            # for soluble binders
}
# parse result["mfasta"]: keep headers without 'native'/'wt'; zip with result["scores"]
m.upsert_candidate("bb003_seq02", backbone_id="bb003", sequence=designed_seq)
m.set_scores("bb003_seq02", proteinmpnn_nll=score)
```

## 4. Co-fold + score — `boltz2-nim` or `openfold3-nim`

Co-fold each designed binder **with the target** as a 2-chain complex. Use the
binder sequence + target sequence (and target MSA if built).

- `openfold3-nim` returns an explicit `iptm_score` (interface) and pLDDT.
- `boltz2-nim` returns `confidence_scores`; retain it as complex confidence.
  It is not an ipTM substitute. Populate `iptm` only from an explicitly identified
  interface metric; otherwise leave it missing and use the explicitly selected
  `boltz2_confidence_min` filter and `boltz2_confidence` ranking route from setup.
  Store the scalar confidence for the same returned sample as the saved complex.

Record the sample index, chain roles, candidate/sequence identity, and digests of
its target, response and selected complex when saving the response. Verify those
bindings before importing missing metrics on resume. A complete low score does
not need recomputation. Derive binder pLDDT only from explicitly identified
per-residue binder confidence with its scale established; a whole-complex mean
cannot substitute. Keep it missing when the response lacks that evidence.
The synthetic cache format and recovery command are in `references/offline.md`.

```python
# delegate to boltz2-nim / openfold3-nim
polymers = [
    {"id": "A", "molecule_type": "protein", "sequence": designed_seq},     # binder (single-seq MSA is standard for de novo)
    {"id": "B", "molecule_type": "protein", "sequence": target_seq},        # target (+ MSA)
]
m.set_scores("bb003_seq02", iptm=iptm, binder_plddt=plddt, boltz2_confidence=conf)
m.add_artifact("bb003_seq02", "complex_cif", "runs/.../complexes/bb003_seq02.cif")
```

### Cost funnel
Co-folding is the expensive stage. Co-fold a **capped shortlist** first (e.g.
best ProteinMPNN NLL per backbone), review, then expand. Reserve high
`diffusion_samples` / `recycling_steps` for the final survivors.

## 5. Self-consistency RMSD

Compare the RFdiffusion backbone to the predicted binder chain (from the
co-folded complex). Low RMSD = the sequence is predicted to fold back into the
designed backbone.

```python
from metrics import ca_rmsd_from_structures
rmsd = ca_rmsd_from_structures(
    backbone_pdb, predicted_complex_cif,
    backbone_chain=backbone_binder_chain,  # verified from the RFdiffusion PDB
    predicted_chain="A",                 # binder polymer ID in the request above
    predicted_format="cif",
)
m.set_scores("bb003_seq02", self_consistency_rmsd=rmsd)
```

`pdb_utils.structure_ca_coords()` reads mmCIF with biotite using label chain IDs
(the request polymer IDs). It also accepts PDB. Missing chains or unequal CA
counts fail explicitly; do not truncate structures to force an RMSD. The CLI is
`python3 scripts/metrics.py backbone.pdb complex.cif --backbone-chain <C> --predicted-chain <ID>`.
For sequence-only controls without a designed backbone, RMSD is not applicable;
`Manifest.apply_filters()` records the exemption and still tests confidence/pLDDT.

## 6. Filter + rank + report

```python
from pathlib import Path

m.apply_filters()                       # uses the saved campaign criteria
rank_by = m.data["params"].get("rank_by", "iptm")
ranked = m.rank(by=rank_by, descending=True, passed_only=True, include_controls=False)
top = ranked[:20]
run_dir = Path(m.data["run_dir"])
m.to_csv(run_dir / "all_candidates.csv") # full audit, including controls and failures
m.to_csv(candidates=ranked)              # ranked survivors; controls excluded
print(m.summary())                      # {n_candidates, n_passed, n_controls}
```

`rank()` does not modify the manifest. Always pass its returned list to the
ranked export, including when empty; `to_csv()` alone exports every entry in
insertion order. The complete audit is a separate file. All applicable enabled
filters must pass before ranking, even for a design with the highest interface
score. Disclose missing scores and a provisional passing fraction.

Produce a short report: target + epitope, params, success rate, the top
designs with their scores and artifact paths, and how they compare to controls
(`references/validation.md`).

## Branching summary

- **No target structure** → predict it first (`openfold2/3-nim` or `boltz2-nim`).
- **Target needs evolutionary context** → `msa-search-nim` before co-folding.
- **Interface metric** → prefer OpenFold3 `iptm_score`; Boltz2 `confidence_scores`
  uses its own explicit filter and ranking route. Label the selected metric and
  cutoff in the report, and compare controls under that same route.
- **Binder MSA** → keep single-sequence for de novo binders (standard); do not
  fabricate a binder MSA.

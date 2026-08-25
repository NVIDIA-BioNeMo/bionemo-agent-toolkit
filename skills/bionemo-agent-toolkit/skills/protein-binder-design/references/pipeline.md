# Binder Design Pipeline — Orchestration & Handoff Contracts

This is the detailed orchestration for the `protein-binder-design` workflow.
The agent reasons over these steps and delegates each NIM call to the atomic
skill. Deterministic glue (parsing, remapping, RMSD, manifest) uses the bundled
`scripts/`.

## 0. Setup

- Decide hosted vs local **once** (ask the user) and reuse for every NIM call.
- Create a run directory and manifest:

```python
import sys; sys.path.insert(0, "scripts")
from manifest import Manifest
m = Manifest.create(
    run_dir="runs/<target>_<date>",
    target={"name": "<target>", "pdb_id": "<PDBID>", "chain": "<C>"},
    mode="hosted",
    params={"n_backbones": 100, "seqs_per_backbone": 8, "binder_len": "60-90"},
)
```

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
- Optional: build a target MSA with `msa-search-nim` if you will fold/co-fold
  the target with evolutionary context.

### Human-in-the-loop gate
Before generating backbones, confirm with the user: target chain, epitope/
hotspot set, binder length range, number of backbones, sequences per backbone.

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
- `boltz2-nim` returns `confidence_scores`; use it as the complex confidence.

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
from metrics import ca_rmsd_from_pdb
# extract the binder chain from the predicted complex, then:
rmsd = ca_rmsd_from_pdb(predicted_binder_pdb, backbone_pdb)
m.set_scores("bb003_seq02", self_consistency_rmsd=rmsd)
```

(Convert mmCIF→PDB or parse CA atoms from the binder chain; `pdb_utils` reads
PDB ATOM records.)

## 6. Filter + rank + report

```python
m.apply_filters()                       # uses manifest filters (ipTM/pLDDT/RMSD)
top = m.rank(by="iptm", descending=True, passed_only=True)[:20]
m.to_csv()                              # candidates.csv next to manifest.json
print(m.summary())                      # {n_candidates, n_passed, n_controls}
```

Produce a short report: target + epitope, params, success rate, the top
designs with their scores and artifact paths, and how they compare to controls
(`references/validation.md`).

## Branching summary

- **No target structure** → predict it first (`openfold2/3-nim` or `boltz2-nim`).
- **Target needs evolutionary context** → `msa-search-nim` before co-folding.
- **Interface metric** → prefer OpenFold3 `iptm_score`; Boltz2 `confidence_scores`
  is the fallback complex-confidence signal.
- **Binder MSA** → keep single-sequence for de novo binders (standard); do not
  fabricate a binder MSA.

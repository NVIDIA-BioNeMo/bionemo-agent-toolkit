# Run Manifest & Directory Convention

A campaign writes one `manifest.json` (machine state) and one `candidates.csv`
(human/spreadsheet view) under a run directory. The manifest is the backbone for
ranking, resumability, validation, and the final report.

## Directory layout

```text
runs/<campaign>_<date>/
├── manifest.json          # campaign state (see schema below)
├── candidates.csv         # flat table, regenerated from the manifest
├── backbones/             # RFdiffusion output PDBs
├── sequences/             # ProteinMPNN mfasta files
└── complexes/             # Boltz2/OpenFold3 co-folded .cif files
```

## Schema (`manifest.json`)

```json
{
  "schema_version": "1.0",
  "campaign": "protein-binder-design",
  "created": "2026-06-12T18:00:00+00:00",
  "run_dir": "runs/<target>_<date>",
  "target": { "name": "<target>", "pdb_id": "<PDBID>", "chain": "<C>" },
  "mode": "hosted",
  "params": { "n_backbones": 100, "seqs_per_backbone": 8, "binder_len": "60-90" },
  "filters": { "iptm_min": 0.8, "binder_plddt_min": 80.0, "self_consistency_rmsd_max": 2.0 },
  "stages": [ { "stage": "rfdiffusion", "ts": "...", "n": 100 } ],
  "candidates": [
    {
      "id": "bb003_seq02",
      "backbone_id": "bb003",
      "sequence": "....",
      "scores": { "proteinmpnn_nll": 1.02, "iptm": 0.84, "binder_plddt": 86.2, "self_consistency_rmsd": 1.4 },
      "artifacts": { "backbone_pdb": "backbones/bb003.pdb", "complex_cif": "complexes/bb003_seq02.cif" },
      "passed_filter": true,
      "is_control": false,
      "control_type": null,
      "created": "..."
    }
  ]
}
```

## Usage (`scripts/manifest.py`)

```python
import sys; sys.path.insert(0, "scripts")
from manifest import Manifest

m = Manifest.create(run_dir="runs/demo", target={"name": "X", "chain": "A"}, mode="hosted")
m.log_stage("rfdiffusion", n=100)
m.upsert_candidate("bb003_seq02", backbone_id="bb003", sequence="MKT...")
m.set_scores("bb003_seq02", iptm=0.84, binder_plddt=86.2, self_consistency_rmsd=1.4)
m.add_artifact("bb003_seq02", "complex_cif", "complexes/bb003_seq02.cif")
m.apply_filters()
ranked = m.rank(by="iptm", passed_only=True)
m.to_csv(candidates=ranked)

# resume a campaign later
m2 = Manifest.load("runs/demo")
```

`apply_filters()` requires every applicable enabled metric to be present and finite. Missing
or invalid scores cannot pass. Set a threshold to `null` only when deliberately
disabling that criterion for the campaign, and disclose the override. A composite
confidence field does not satisfy an ipTM requirement. Sequence-only controls
without `artifacts.backbone_pdb` skip only RMSD, with the reason saved under
`filter_exemptions`. `filter_metrics` records the criteria actually evaluated.

### Boltz2-only filtering and ranking

Use a separate `boltz2_confidence_min` filter when the co-fold response has no
explicit ipTM. Resolve its cutoff with the campaign inputs before inference;
there is no default composite-confidence threshold. The numbers below are
**synthetic bookkeeping examples**, including the illustrative 0.8 cutoff.
Replace scores with values extracted from the saved prediction, and choose the
cutoff for the real campaign using `references/validation.md` and save its source
in `params.confidence_selection`. If no cutoff is supplied, the default route is
explicit ipTM from OpenFold3; if that is unavailable, record
`selection_policy_unresolved` and stop before design inference. Keep binder
pLDDT/RMSD criteria enabled for designs.

```python
m = Manifest.create(
    run_dir="runs/boltz2_demo",
    target={"name": "synthetic example"},
    params={"rank_by": "boltz2_confidence"},
    filters={
        "iptm_min": None,
        "boltz2_confidence_min": 0.8,
        "binder_plddt_min": 80.0,
        "self_consistency_rmsd_max": 2.0,
    },
)
m.set_scores("example", boltz2_confidence=0.9, binder_plddt=86.2, self_consistency_rmsd=1.4)
m.apply_filters()
ranked = m.rank(by=m.data["params"]["rank_by"], passed_only=True)
m.to_csv(candidates=ranked)
```

This candidate can pass without an `iptm` value; its composite confidence remains
in `boltz2_confidence`. A missing or non-finite enabled metric still fails.
Label the metric and cutoff in the report, and apply the same profile to controls.

`to_csv()` with no candidate list exports the full audit table in insertion
order. Pass the list returned by `rank()` to export ranked survivors, including
an empty list when none pass. The manifest always retains all candidates and
controls. `rank()` excludes missing, nonnumeric, boolean, and non-finite scores.

## Resumability

Load `Manifest.load(run_dir)` and retain its filters, mode, parameters, and ranking
metric. `m.required_metrics(cid)` lists the applicable enabled metrics;
`m.missing_scores(cid)` lists missing/non-finite values. A finite failing score is
complete and should not trigger another prediction.

| Stage | Completed evidence | Resume action when missing |
|---|---|---|
| Backbone (designs only) | nonempty `artifacts.backbone_pdb` file | resolve saved backbone by `backbone_id`; regenerate only if genuinely absent |
| Sequence | nonempty candidate `sequence` plus saved MPNN response for designs | parse saved response before making another MPNN call |
| Co-fold | nonempty `artifacts.complex_cif` or `complex_pdb`, plus saved response | reuse a saved complex/response; otherwise co-fold this candidate |
| Metrics | `missing_scores(cid) == []` | extract from saved response/structure; run `metrics.py` for design RMSD |
| Filtering/report | current `filter_metrics`, `passed_filter`, CSV | rerun deterministic filtering and export; no inference |

Resolve artifact paths as recorded (the examples include the run directory), and
verify files exist and are nonempty before skipping a stage. Sequence-only controls
do not require a designed backbone or its RMSD. An explicit `failure_reason` from
a failed request remains visible; retry only after the cause or retry decision is
recorded. Checkpoint every successful or failed expensive stage with the mutation
helpers. Preserve all candidates, including incomplete and failed ones.

# Binder Design Validation

All outputs are in-silico, so validation means computational benchmarking.
Never report only top scores — report a **success rate** and compare against
controls.

## Metrics

| Metric | Source | Pass guide | Meaning |
|---|---|---|---|
| Interface confidence (ipTM) | Explicit ipTM output, e.g. OpenFold3 `iptm_score` | ≥ 0.8 | predicted interface quality |
| Composite complex confidence | Boltz2 `confidence_scores` | campaign-selected `boltz2_confidence_min` | separate filter/ranking route when ipTM is unavailable |
| Binder pLDDT | OpenFold3 / Boltz2 | ≥ 80 | binder fold confidence |
| Self-consistency RMSD | `scripts/metrics.py` (Kabsch CA-RMSD) | ≤ 2.0 Å | designed backbone vs predicted |
| Sequence quality (NLL) | ProteinMPNN `scores` | lower better | sequence–backbone compatibility |

There is no protein–protein affinity NIM, so ipTM + self-consistency RMSD are
the binder proxy (the Bennett et al. 2023 filter pattern).

For a Boltz2-only campaign without explicit ipTM, save `iptm_min: null`, a chosen
`boltz2_confidence_min`, and `params.rank_by: boltz2_confidence` before inference.
Keep pLDDT/RMSD requirements; rank with that saved metric. This profile has its
own success rate and must be labeled as composite-confidence selection, not as
passing the default ipTM filter. `references/manifest.md` has executable usage.

## Controls

Run controls through the **same co-folding model and settings** so confidence
and pLDDT distributions are comparable. They do not need RFdiffusion/ProteinMPNN.

- **Negative controls** — scrambled binder sequences (preserve composition):

```python
import sys; sys.path.insert(0, "scripts")
from controls import make_scrambled_controls
negs = make_scrambled_controls([designed_seq], n=5, seed=42)
# co-fold each, then register with is_control=True, control_type="scrambled"
m.upsert_candidate("ctrl_neg_01", is_control=True, control_type="scrambled", sequence=negs[0])
```

- **Positive controls** — published binder sequences for the same target
  (`assets/targets.json` → `published_binders`), co-folded the same way and
  marked `control_type="published"`.

The bundled registry is a template and contains no published binder sequences.
Use cited user inputs or verify exact sequences against a primary paper/structure
and register the target, binder sequence, and source with `scripts/registry.py`.
If none can be sourced, record `positive_controls_unavailable`; return an
**uncalibrated computational screen** with negative controls and disclose that the
positive-control comparison was not performed. Do not invent a positive or label
the missing comparison as successful. If calibrated benchmarking was requested,
that portion remains blocked.

Sequence-only controls have no RFdiffusion backbone. Leave their self-consistency
RMSD absent, and do not attach a parent's backbone merely to satisfy the filter.
`apply_filters()` records `filter_exemptions.self_consistency_rmsd` for these
controls while retaining confidence and pLDDT requirements. A control with a real
reference `artifacts.backbone_pdb` is subject to the RMSD filter. Compare control
confidence/pLDDT distributions separately from the design-only RMSD distribution.

### Choosing a Boltz2 composite-confidence cutoff

The default route uses explicit ipTM and the existing ipTM threshold. Without a
composite cutoff, prefer OpenFold3; if unavailable, stop before design inference
with `selection_policy_unresolved`. No universally validated composite-confidence
cutoff is bundled here, and the synthetic 0.8 example is not a recommendation.

For a Boltz2-only campaign, reuse the user's supplied cutoff and record its source
and limitations, or perform a separate calibration with sourced positives and
scrambled negatives against the same target, model/version, and folding settings.
Plot/report both score distributions, choose a cutoff under a stated false-positive
tolerance, and assess it on held-out controls; insufficient controls or inseparable
distributions cannot establish a calibrated cutoff. Obtain the campaign decision
before screening the design pool. Save the cutoff, control IDs, settings, rationale,
and calibration limitations in `params.confidence_selection`; never tune the cutoff
on the design pool just to obtain passers. A user-selected cutoff without calibration
supports explicitly labeled exploratory screening only.

## Success rate

The metric the field actually quotes — fraction of designs passing the filter:

```python
s = m.summary()
success_rate = s["n_passed"] / s["n_candidates"] if s["n_candidates"] else None
```

Controls are excluded from both counts. A candidate needs finite values for
every enabled filter to pass. Report the number still missing required scores;
until scoring finishes, label the ratio as provisional. With no candidates,
report the rate as unavailable, not zero percent.

Use it to compare pipeline configs (diffusion steps, sampling temperature,
sequences/backbone) rather than over-interpreting any single design.

## Published comparison

Re-score literature winners through your exact pipeline and check your top
designs land in the same confidence regime. Compare RMSD only when the control has
a real reference backbone. Absolute scores are not comparable
across pipelines — only same-pipeline comparisons are meaningful.

Benchmark targets come from the target registry (`assets/targets.json`) — add your own
with `scripts/registry.py`. Always confirm epitope residues against the cited structure
before use; registry entries flag illustrative residue lists.

## Caveats

- In-silico triage, not experimental validation. Prefer relative ranking and
  distribution separation over absolute claims.
- ipTM can be optimistic; corroborate with self-consistency RMSD and ProteinMPNN
  NLL before prioritizing.
- Keep all artifacts, payloads, and the manifest together for reproducibility.

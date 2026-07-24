# Binder Design Validation

All outputs are in-silico, so validation means computational benchmarking.
Never report only top scores — report a **success rate** and compare against
controls.

## Metrics

| Metric | Source | Pass guide | Meaning |
|---|---|---|---|
| Interface confidence (ipTM) | OpenFold3 `iptm_score` · Boltz2 `confidence_scores` | ≥ 0.8 | predicted interface quality |
| Binder pLDDT | OpenFold3 / Boltz2 | ≥ 80 | binder fold confidence |
| Self-consistency RMSD | `scripts/metrics.py` (Kabsch CA-RMSD) | ≤ 2.0 Å | designed backbone vs predicted |
| Sequence quality (NLL) | ProteinMPNN `scores` | lower better | sequence–backbone compatibility |

There is no protein–protein affinity NIM, so ipTM + self-consistency RMSD are
the binder proxy (the Bennett et al. 2023 filter pattern).

## Controls

Run controls through the **identical** pipeline so score distributions are
comparable.

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

A working pipeline separates designed/published positives from scrambled
negatives in the ipTM and RMSD distributions.

## Success rate

The metric the field actually quotes — fraction of designs passing the filter:

```python
s = m.summary()
success_rate = s["n_passed"] / max(s["n_candidates"], 1)
```

Use it to compare pipeline configs (diffusion steps, sampling temperature,
sequences/backbone) rather than over-interpreting any single design.

## Published comparison

Re-score literature winners through your exact pipeline and check your top
designs land in the same ipTM/RMSD regime. Absolute scores are not comparable
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

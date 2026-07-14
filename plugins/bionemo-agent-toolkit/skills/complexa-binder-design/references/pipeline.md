# Pipeline — stages, handoffs, loop, layout

## Stage 1 — target + hotspots (automated, no GPU)

Resolve one design-ready structure (PDB → AFDB → provided file → fold), define a
**compact, surface-exposed epitope** with the evidence-based resolver, align + prune,
build a target MSA, and crop to the **binder + target ≤ ~500-residue** budget. Run the
**preflight** and review before GPU. Full detail (resolver order, numbering caveats,
crop): `target-and-hotspots.md`. Driven by `scripts/pipeline.py` +
`scripts/preflight_design.py`.

## Stage 2 — register + generate (open `complexa` CLI)

Register the target in Complexa's target dict (hotspots + binder-length range are
target-dict-driven), then **generate** with the lean path — `complexa generate` with
reward-guided `best-of-n` (NOT the full `complexa design`):

```bash
export COMPLEXA_REPO=/path/to/Proteina-Complexa
complexa target add my_target --pdb target.pdb --chain A --span 1-115 \
    --hotspots A54,A56 --binder-length 60-90      # or reuse an example (assets/targets.json)
python scripts/complexa_design.py run --task-name my_target --run-name run1 \
    --algorithm best-of-n --num-samples 8 --seed 0 --out outputs/run1
```

`complexa_design.py run` shells `complexa generate` (best-of-n), discovers the
`inference/` complex PDBs, and extracts the co-designed sequences. Overrides + outputs:
`complexa-cli.md`.

> **Avoid the full `complexa design`** for this workflow: best-of-n already AF2-selects
> during generation, so the full pipeline's `evaluate` (re-folds every design with
> AF2/RF3/ESMFold) is redundant and its `analyze` needs `foldseek`/`sc`. Generation
> alone emits the co-designed seq+structure; validate independently in Stage 3.

**AF2 quality gate.** With the AF2 reward configured, `best-of-n` keeps the
AF2-confident designs during search (i_pTM/pLDDT-guided); a persistent empty result is
a scientific signal (bad hotspots/length/algorithm), not a reason to loop harder. No
AF2 weights → `--af2-bypass` (`single-pass`) and let the Boltz2 gate (Stage 3) select.

## Stage 3 — extract + validate (independent refold)

The binder chain carries the **co-designed sequence** (read directly — no MPNN). Per
surviving binder, run **two** predictions with one refolder (`boltz2-nim` default):
holo (binder+target) and apo (binder alone) — a **different** model family than
Complexa's AF2/RF3 reward+evaluate, so the check is independent. Turnkey:

```bash
python scripts/boltz2_refold.py --run-dir <run> --pdbs <inference>/*.pdb \
    --endpoint hosted --validate scripts/validate_binders.py [--hotspots <run>/hotspots.json]
```

`boltz2_refold.py` makes the **holo** Boltz2 calls (retry/backoff + `--throttle` to
avoid HTTP 429), writes `validation/raw/*.json`, then chains `validate_binders.py`
(apo + ipSAE + apo↔holo RMSD + gate + rank). Policy + metrics: `validation.md`.

## Stage 4 — gate + rank + report

`scripts/validate_binders.py` applies the gate (`validation.md`), ranks survivors, and
writes `ranked_binders.json`/`.csv`; then write the report.

## Run-until-N-validated loop

The deliverable is **N designs that pass the full gate**, not N raw designs. Only a
fraction pass, so loop Stages 3–5 and accumulate passers:

```
N         = user-requested count (default 10)
validated = []                      # deduped by binder sequence
round     = 0
while len(validated) < N and not stop_cap():
    round  += 1
    batch   = complexa_generate(target, nsamples=k, seed=base+round)
    scored  = validate(batch)       # holo+apo, full gate
    passers = [d for d in scored if d.pass and d.seq not in seqs(validated)]
    validated += passers
return rank(validated)[:N]
```

Size each round from the measured pass rate `p = passers/generated`:
`k = ceil((N - len(validated)) / max(p, p_floor)) * safety`.

**Stop caps** (state which fired): reached N; `round ≥ max_rounds` (default 8);
sample/GPU budget exhausted; or ≥3 consecutive zero-passer rounds. A persistent 0%
pass rate is a scientific signal (bad hotspots/length/algorithm) — surface it and
propose changes instead of burning GPU.

## Output layout

```
outputs/<target>_<run_id>/          # run_id = UTC %Y-%m-%d_%H%M%S
├── target.pdb / target.cif         # from target-preparation
├── hotspots.json                   # [{chain,residue,position}, ...]
├── design/                         # Stage 3: Complexa complex PDBs + the exact command + run config
├── sequences/                      # binder sequences extracted from the complexes
├── validation/holo/ , validation/apo/ , validation/validation_scores.json(.csv)
├── ranked_binders.json / .csv      # every design (pass+fail), all metrics, pass, failure_reason
├── REPORT_<target>_<run_id>.md
└── manifest.json                   # target, Complexa run config + seeds, params, versions, paths
```

Use one `<target>_<run_id>` for the whole loop; never scatter or overwrite.

## Report sections

1. **Executive summary** — target, what was designed, requested-vs-achieved N,
   headline in 2–3 sentences.
2. **Loop provenance** — rounds, generated/round, per-round + overall pass rate,
   cumulative validated, which stop condition fired.
3. **Decision: GO / NO-GO** — did any binder clear the full gate?
4. **Target & hotspots** — `Target: NAME (UniProtID)`, structure source, hotspot
   identities + citations.
5. **Ranked binders** — table: rank, round, sequence/length, holo `.cif`, apo `.cif`,
   ipTM, ipSAE_min, complex/binder/apo pLDDT, apo↔holo RMSD, hotspot-contact, pass.
6. **Independent validation** — refolder vs Complexa's own evaluate; apo/holo
   stability.
7. **Concerns & limitations** — de-novo MSA caveats, reward-model availability,
   numbering risks, missing endpoints.
8. **Reproducibility** — Complexa run config + per-round seed/sample settings, model +
   checkpoint versions, full artifact paths.

Report only measured values — never fabricate; write `null`/`N/A` when missing. If a
stage failed, say so plainly (stage + verbatim error) and emit no scores for stages
that did not run.

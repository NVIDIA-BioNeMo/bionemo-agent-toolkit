# Pipeline — stages, handoffs, loop, layout

## Stage 1 — target + hotspots (automated, no GPU)

Resolve one design-ready structure (PDB → AFDB → provided file → fold), define a
**compact, surface-exposed epitope** with the evidence-based resolver, align + prune,
build a target MSA, and crop to the **binder + target ≤ ~500-residue** budget. Run the
**preflight** and review before GPU. Full detail (resolver order, numbering caveats,
crop): `target-and-hotspots.md`. Driven by `scripts/pipeline.py` +
`scripts/preflight_design.py`.

Save and review the actual prepared geometry before generation (chain IDs below
are examples; verify them in the supplied structure):

```bash
python scripts/preflight_design.py complex.pdb --chain B --partner-chain A --out prepared
```

`prepared/` contains `target_prepared.pdb`, `hotspots.json`, and `preflight.json`.
With more than one possible protein partner, `--partner-chain` is required unless
an explicit `--hotspots` file defines the epitope. Only the selected target chain
is conditioned on; contacts to other partners are not pooled. Preflight and full
runs call the same preparation function, and failed checks block generation.

## Stage 2 — register + generate (open `complexa` CLI)

Register the target in Complexa's target dict (hotspots + binder-length range are
target-dict-driven), then **generate** with the lean path — `complexa generate` with
reward-guided `best-of-n` (NOT the full `complexa design`):

```bash
export COMPLEXA_REPO=/path/to/Proteina-Complexa
PYTHONPATH=scripts python - <<'PY'
import json
from pathlib import Path
from pipeline import register_complexa_target
plan = json.loads(Path("prepared/preflight.json").read_text())
if not all(passed for passed, _ in plan["checks"].values()):
    raise SystemExit("Resolve preflight findings before generation")
register_complexa_target("my_target", Path(plan["prepared_target"]),
                         plan["hotspot_residues"], chain=plan["chain"])
PY
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

For compatibility, the legacy `pipeline.py --mode full` still drives
`complexa design`. Its equivalent saved-preflight handoff is
`--target-file prepared/target_prepared.pdb --hotspots prepared/hotspots.json
--run-dir outputs/run1`. From the original co-complex, supply the same `--chain`
and `--partner-chain`; full mode derives and persists the interface without a
separate hotspot file. A user-managed `target_key` must match the prepared
geometry, hotspot set, and binder lengths. Reusing binders with a changed or
unverified target/epitope fails; use a fresh run directory for another interface.

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
    --target-chain <verified-target-chain> --binder-chain <verified-binder-chain> \
    --max-designs <2-times-requested-N> \
    --endpoint hosted --validate scripts/validate_binders.py [--hotspots <run>/hotspots.json]
```

`boltz2_refold.py` makes the **holo** Boltz2 calls (retry/backoff + `--throttle` to
avoid HTTP 429), writes `validation/raw/*.json`, then chains `validate_binders.py`
(apo + ipSAE + apo↔holo RMSD + gate + rank). The glob above must contain only the
ranked shortlist, at most 2×N per round (default 20); the CLI refuses larger batches.
Input stems must be unique and become stable result IDs. Each raw JSON includes
`_refold` provenance, chain IDs, and hotspots remapped from input author numbering
to prediction sequence indices. Failed inputs/calls also produce raw JSON with
`failure_reason`; they survive into the score/ranking tables with `pass: false`.
`validation/refold_batch.json` identifies the current invocation and shortlist.
Only matching responses enter the ranking; missing or interrupted candidates get
failed rows. Starting another batch invalidates previous ranking tables until
rescoring, while retaining older raw files for inspection. Keep separate round
directories to retain complete campaign history.
Legacy raw responses without `_refold` use the validator's explicit chain flags
(A/B only when those are verified), and supplied hotspots must already use the
prediction's sequence positions. Policy + metrics: `validation.md`.

## Stage 4 — gate + rank + report

`scripts/validate_binders.py` applies the gate (`validation.md`), ranks survivors, and
writes `ranked_binders.json`/`.csv`; then write the report.

## Bounded campaign loop

Aim for N gate-passing designs, with **at most two generation rounds**. Keep all
scored rows, including failures; report fewer passers without claiming failures
were validated. This is the agent's campaign loop; a `pipeline.run()` call itself
performs at most one generation round and emits the independent-refold handoff.

```
N = user-requested count (default 10)
all_scored = []; seen_sequences = set()
for round in [1, 2]:
    if count_passers(all_scored) >= N or budget_exhausted(): break
    batch = complexa_generate(target, nsamples=agreed_batch_size, seed=base+round)
    shortlist = rank_generation_quality(batch excluding seen_sequences)[:2*N]
    scored = validate(shortlist)    # record successes AND failures; holo+apo gate
    all_scored += scored
    seen_sequences.update(sequences(shortlist))
    if count_passers(scored) == 0: break
return rank(all_scored, passers_first=True, by=[ipTM, ipSAE_min])[:N]
```

**Stop conditions** (record the first that fires): reached N passers; completed
two rounds; exhausted the agreed sample/call/GPU/time budget; or any zero-passer
round (including an empty shortlist). Persist round count and cumulative budget
use in the manifest so resume cannot reset these limits. Do not automatically
increase the generation batch, validation cap, or round count to chase N passers.
The default permits at most 4×N holo and 4×N apo predictions across two rounds,
before bounded retry attempts; retries also consume the recorded call/time budget.
Return at most N ranked candidates with explicit pass/failure flags, requested vs
delivered/pass counts, and NO-GO when the requested passing count was not achieved.

## Output layout

```
outputs/<target>_<run_id>/          # run_id = UTC %Y-%m-%d_%H%M%S
├── target.pdb / target.cif         # from target-preparation
├── hotspots.json                   # [{chain,residue,position}, ...]
├── design/                         # Stage 3: Complexa complex PDBs + the exact command + run config
├── sequences/                      # binder sequences extracted from the complexes
├── validation/raw/ , validation/apo/ , validation/validation_scores.json(.csv)
├── validation/refold_batch.json   # current shortlist + invocation ID
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

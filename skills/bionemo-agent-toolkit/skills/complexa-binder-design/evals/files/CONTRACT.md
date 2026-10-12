# Offline workflow contract

All coordinates, responses and metric values in these fixtures are synthetic.
They test software behavior on a CPU. Work from the supplied files, make no
network/model calls, preserve inputs, and identify this limited coverage in the
final response. No fixture is evidence of binding or live structural validation.
Use the bundled helpers when available; equivalent implementations are accepted.

## Target preparation

Select the requested target author chain and only the specified interface
partner. Define interface residues by a heavy-atom distance of at most 5 Angstrom
to that partner. Preserve the target coordinates, residue identities and author
numbering, excluding other chains from `target_prepared.pdb`.
An explicit patch overrides interface selection. Check its residues against the
structure; record absent residues and never invent replacements.

Write `hotspots.json` with `hotspot_residues` (objects with chain, position,
residue), `dropped_hotspots`, `target_chain` and `partner_chain`.
Write `preflight.json` with `chain`, `partner_chain`, `conditioned_length`,
`n_hotspots`, `final_hotspots` (e.g. `B10(ALA)`) and `checks`. Each check is
`[boolean, explanation]`: `size<=500` (target plus a 120-residue binder),
`compact<=30A` (maximum pairwise CA/CB hotspot distance), `>=1_hotspots`,
`<=15_hotspots`, and `crop_preserves_hotspots`. All must pass for geometry READY.
These small targets require no crop. Save failed preflights too; generation
cannot proceed without an epitope. READY says nothing about model availability.

## Saved metrics

Read `saved_scores.json`; preserve supplied values and missing scores. Apply
these gates inclusively: ipTM >= 0.65, ipSAE_min >= 0.45, complex/binder/apo
pLDDT >= 0.70, binder RMSD <= 2.5 Angstrom, hotspot contact fraction >= 0.20.
Missing, non-finite, boolean and string scores fail. An explicit execution
failure also fails, even if the record contains old high scores. Generator
reward is not independent evidence. Do not coerce or repair metrics.

Keep every candidate in `ranked_binders.json` and `ranked_binders.csv`.
Sort passers first, then descending numeric ipTM, then descending ipSAE_min,
with missing/invalid values last. Add 1-based `rank`, boolean `pass`, and
`failure_reason` (null for a passer). Missing gate metrics become null in JSON
and empty CSV cells. Retain failed candidates and describe each failed gate.
Also write `validation/validation_scores.json/.csv` with the same audit.

Write `summary.json` with `evidence_kind: synthetic`, `live_inference: false`,
SHA-256 of the input as `source_sha256`, `hotspot_conditioned`, the gate mapping
(`metric: [min|max, threshold]`), `requested`, `evaluated`, `passed`, `delivered`
(at most requested, including explicitly flagged failures), `quota_met`,
`decision` (GO only when the passing quota is met), and
`stop_reason: saved_scores_exhausted`. `REPORT.md` must name the ranked
candidates, failed gates and requested versus achieved counts. State that this
is a synthetic metric review with no generation, refolding or verification of
the upstream measurements. A NO-GO here is a fixture policy result.

## Interrupted validation

Copy the run to the requested output directory before rebuilding its exports.
`validation/refold_batch.json` identifies the current invocation and complete
candidate list. A response in `validation/raw/<candidate>.json` contributes only
when `_refold.batch_id` matches. Keep failed, stale and missing candidates as
failed rows with specific reasons and null unmeasured gate metrics. Ignore raw
files outside the batch list; preserve all raw files and the batch record.
Replace both ranking exports and write the matching validation score exports.
Equal unmeasured scores retain the batch order. Write `REPORT.md` describing
blocked candidates and zero passers, labeled synthetic offline recovery.
Do not create predictions, submit retries, or treat prior success as current.

The bundled validator supports this recovery via `--no-apo --endpoint local`;
this fixture needs neither an endpoint nor ipSAE because none of its responses
is eligible for structural scoring.

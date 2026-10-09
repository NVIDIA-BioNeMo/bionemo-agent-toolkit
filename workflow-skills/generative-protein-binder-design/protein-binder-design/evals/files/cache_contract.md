# Saved-response fixture contract
All sequences, coordinates, responses, scores, and policies here are synthetic. Work offline;
do not read credentials, call endpoints, or claim live inference or scientific validation.
This local cache metadata is a fixture/campaign format, not an extra field promised by a NIM API.

Copy each input run to its required output directory before modifying it. Preserve input files,
original candidates, target, params, filters, existing finite scores, artifacts, and failed stages.
Relative paths refer to that run directory. Save and reload the resulting manifest, apply every
enabled filter, and export all_candidates.csv (all entries) and candidates.csv (passing designs
in descending rank_by order, excluding controls). Empty rankings retain a header.

For each candidate, record cache_status as complete, recovered, or blocked. Complete means all
applicable enabled scores are finite (even if below a threshold); do not recompute or replace them.
A sequence-only control without a backbone is exempt only from RMSD. For incomplete candidates,
validate the prediction binding before importing any scores: candidate ID, SHA-256 of the exact
sequence string, target.structure bytes, response file bytes, and the selected structure text.
All digests use UTF-8 without newline normalization. Copy the complete prediction binding into
score_provenance when recovering. Keep all prediction fields as supplied. A mismatch blocks the
whole import; preserve any existing scores. Never select a different sample to get a better score.

Boltz2: structures[sample_index] pairs with confidence_scores[sample_index], in
boltz2_confidence only; the arrays must have equal length. No ipTM substitution.
OpenFold3: choose outputs by matching input_id, then structures_with_scores[sample_index];
only iptm_score supplies ipTM. confidence_score and complex_plddt_score do not supply it.
The selected structure's binder-chain CA B factors encode per-residue pLDDT here, with the
explicit prediction.plddt_scale (0-1 or 0-100). Average the binder only and report 0-100.
Use mmCIF label_asym_id, not auth_asym_id, and require both chain roles and the full binder
length. These fixture encodings do not establish B-factor semantics for arbitrary experimental PDBs.
Recover missing RMSD by aligning the full backbone binder chain and full selected predicted
binder chain with a proper rigid rotation (Kabsch); never truncate to match lengths.

Import only missing/invalid enabled metrics and only when all of them are recoverable. Save
the exact selected complex under the output run and add artifacts.complex with its relative path.
If blocked, leave scores unchanged and set cache_reason to candidate_mismatch, target_mismatch,
sequence_mismatch, artifact_digest_mismatch, sample_digest_mismatch, binder_length_mismatch,
missing_required_scores, missing_artifact, or missing_prediction as applicable. No API retry.
Existing failure_reason and stage entries remain as historical evidence, even after recovery.

Write summary.json with n_candidates (non-controls), n_passed, n_controls, ranked_ids,
missing_scores (IDs to missing/invalid required metric names), passing_fraction_provisional,
label containing 'simulated', and live_inference: false. Describe unresolved candidates and
provisional fractions in the final response. A count or score alone is not evidence of execution.

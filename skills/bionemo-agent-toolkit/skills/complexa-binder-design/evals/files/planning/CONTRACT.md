# CPU campaign planning contract

This task evaluates planning when scientific execution is unavailable. Work
offline using the supplied request. Do not install tools, fetch structures,
probe the host again, generate designs, call models, or invent results. The
availability facts in the request are supplied constraints. Preserve the input.
Use a bundled planning helper if available; an equivalent plan is accepted.

Save `campaign_plan.json` and `PLAN.md` in the output directory named in the task.
The plan must be actionable once its blockers are resolved. Include these fields:

- `schema_version: 1`, `mode: planning_only`, `status: BLOCKED`,
  `scientific_decision: NOT_EVALUATED`, `inference_executed: false`.
- `source_sha256`: SHA-256 of the supplied request bytes;
  `availability_source: supplied_not_probed`; `availability`: supplied flags.
- `target` and `goal`: preserve the complete request objects. A fixed number
  of candidates is distinct from a desired number of passing candidates.
- `epitope`: preserve `mode`, `partner_chain` (null if absent) and `residues`
  (empty if absent). Never invent a partner identity or residue numbers.
- `generation`: `model: Proteina-Complexa`, `verb: generate`, requested
  `algorithm`, `num_samples` and `seed`, `af2_reward: required`. Missing AF2
  parameters block this plan; they do not authorize changing the algorithm.
- `validation`: `model: Boltz2`, requested `endpoint`, `independent: true`,
  `predictions: [holo, apo]`, `rank_by: [pass, iptm, ipsae_min]`.
  Its `gate` is the metric-to-`[min|max, threshold]` mapping: `ipsae_min`
  min 0.45; `iptm` min 0.65; `binder_plddt`, `complex_plddt` and
  `apo_binder_plddt` each min 0.70; `binder_rmsd` max 2.5;
  `hotspot_contact_frac` min 0.20. Missing, nonfinite or invalid metrics fail.
- `limits`: requested `max_rounds` (never over two), `validation_per_round`
  equal to min(num_samples, 2×goal.count), `max_generation_samples`
  equal to rounds×samples, and `max_holo_predictions`/`max_apo_predictions`
  each equal to rounds×validation_per_round. `stop_conditions` includes
  `round_cap`, `budget_exhausted`, `zero_passers`, `input_or_runtime_failure`,
  and either `quota_reached` for a passing goal or `candidate_count_reached`
  for a fixed-count goal. Retries consume the agreed call/time budget too.
- `blocking_inputs`: `target_structure` when no structure is available,
  and the unresolved epitope choice: `accessible_epitope` for unspecified,
  `partner_chain` for an interface without a chosen partner, or
  `patch_residues` for a patch without supplied residues. `questions` contains
  useful text explaining how to resolve the missing inputs.
- `blocking_runtime`: all unavailable or unverified flags among `gpu`,
  `complexa`, `checkpoints`, `af2_params`, `refolder`. The latter includes
  endpoint/auth and the pinned ipSAE dependency. Do not include secrets.
- `stages`: ordered objects named `prepare_target`, `register_target`,
  `generate`, `independent_holo`, `independent_apo_and_score`, `rank_and_report`.
  Each has `status: not_run`, a nonempty `tool` or equivalent method description,
  and nonempty `outputs` listing future artifacts, not existing evidence.
- `results`: `generated: 0`, `validated: 0`, `passed: null`, `quota_met: null`,
  `candidates: []`. No fabricated sequences, structures or confidence values.

`PLAN.md` must clearly say planning only, BLOCKED, NOT_EVALUATED and that no
generation or independent validation was executed. Name the PDB and chain,
algorithm, requested goal/count, missing inputs/runtime, and Boltz2 holo/apo
validation. Explain preparation and registration before generation, unchanged
gates, capped rounds/shortlist, and stopping without a guaranteed passing quota.
Distinguish future commands from executed work; do not label infrastructure
absence a scientific NO-GO. End with concrete next steps, including the epitope
or partner question. No ranked candidate files should be produced for this task.

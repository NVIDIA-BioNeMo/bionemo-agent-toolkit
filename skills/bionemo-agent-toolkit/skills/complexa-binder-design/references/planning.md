# Planning without a model runtime

When the requested generation or independent validation cannot run, preserve its
requirements in a plan and state the blocker. This is a useful deliverable on a
CPU sandbox, but it is not evidence of generated or validated binders. If local
structures or saved results are available, execute those supported CPU steps
separately and retain their provenance. Do not turn missing infrastructure into
a scientific NO-GO, invent candidate metrics, or guarantee a passing quota.

`scripts/plan_campaign.py` uses only standard Python and accepts the JSON format
below for a PDB target. It writes a fresh directory containing
`campaign_plan.json` and `PLAN.md`, without probing, downloading or running any
models. A zero exit code means the plan was saved, including a BLOCKED plan.
Invalid input or an existing output directory exits 2 and preserves prior work.

```bash
python3 scripts/plan_campaign.py --request request.json --out outputs/campaign_plan
```

```json
{
  "target": {"name": "human PD-L1", "pdb_id": "5JDR", "chain": "A"},
  "epitope": {"mode": "unspecified"},
  "goal": {"kind": "candidates", "count": 8},
  "generation": {"algorithm": "beam-search", "num_samples": 8, "seed": 0},
  "validation": {"refolder": "boltz2", "endpoint": "hosted"},
  "availability": {
    "structure": false,
    "gpu": false,
    "complexa": false,
    "checkpoints": false,
    "af2_params": false,
    "refolder": false
  },
  "max_rounds": 1
}
```

Availability is **supplied evidence**, not a claim that the planner checked the
host. Use `true` only for established prerequisites, `false` for established
absence, and `null` (or omit the field) for unknown. Both false and unknown block
dependent execution. `complexa` includes the trusted installation and config;
`checkpoints` includes both required weights; `refolder` includes endpoint/auth
and the pinned ipSAE dependency. Do not put credentials into this request.

`epitope.mode` is `unspecified`, `partner_interface` (optional `partner_chain`),
or `explicit_patch` (optional `residues`: objects with `chain` and integer
`position`). Missing evidence is retained as a question. Supplied residue or
partner identities still require structural and biological review at preflight;
this planner neither selects nor verifies them. For structures requiring insertion
codes or other target formats, write an equivalent plan preserving those details
and use the target preparation workflow instead of forcing them into this format.

`goal.kind: candidates` preserves a fixed generation request: one round with
`num_samples == count`. `passing_candidates` records a desired passing quota;
it permits at most two rounds and does not promise to reach it. Omitted generation
settings are documented defaults: `best-of-n`, count samples for a fixed-count
goal or up to 2×count for a passing quota (capped at 10,000), seed 0. Omitted
validation settings are Boltz2 and the hosted endpoint.
The plan keeps the AF2 reward requirement; an unavailable reward is not permission
to switch a requested beam search to bypass/single-pass mode.

The plan includes every future stage, outputs, unexecuted status, unchanged gates,
and cumulative sample/prediction limits. Validate at most 2×count designs per
round and never more than the generation batch. Stop at the round cap, quota or
fixed count, budget exhaustion, a zero-passer round, or an input/runtime failure.
Prediction limits count logical holo/apo predictions; bounded retries also consume
the agreed call/time budget and must be recorded. Resume with a fresh round
directory, verified chain mapping and target registration using
`references/pipeline.md`. A plan alone cannot establish runtime or geometry READY.

For planning-only outputs, the scientific decision remains `NOT_EVALUATED`, with
no candidate rows, metrics, pass count or quota claim. A real scientific GO/NO-GO
requires actual generation and independent measured validation.

# Evaluation coverage and deferred live campaigns

## Active coverage: offline bookkeeping

`evals.json` runs one offline software exercise using
`files/bookkeeping.json`, explicitly staged at `/workspace/input/bookkeeping.json`
for both agent conditions. It covers manifest persistence, finite-score
filtering, control exclusion, and ranked CSV export for separate ipTM and
Boltz2 profiles. All numeric inputs and control labels are synthetic.
The active `config.yml` forwards no NIM credentials and the case makes no NIM
calls. Passing it establishes **bookkeeping coverage only**, not live model
execution, biological validity, or end-to-end campaign coverage.

Run the bundled regression tests without model access:

```bash
python -m unittest discover -s tests -v
```

## Deferred: live design, controls, and resume

The original three live cases are retained in `deferred/live-campaigns.json`,
outside the active `evals.json` dataset. **They are not runnable or counted as
covered.** Their required verified inputs are not bundled; do not activate them
with empty `files` lists or substitute synthetic scores. Each case and each
with/without-skill attempt starts independently, so cases 2 and 3 cannot reuse
outputs from case 1.

| Case | Required inputs |
| --- | --- |
| 1: PD-L1 design | Verified PD-L1 registry entry, matching target structure and chain, author-numbered epitope, binder length range, and shortlist size. |
| 2: Controls | Existing PD-L1 campaign manifest and candidate sequences, matching target structure, and published positive-control sequences with source citations. |
| 3: Resume | The interrupted campaign's manifest and referenced artifacts, including both completed candidates and candidates with missing scores. |

When restoring live cases, configure `harbor.runtime_env` to forward the
available NIM credential (`NGC_API_KEY` or `NVIDIA_API_KEY`) to both conditions.
Normalize it with `scripts/hosted_env.sh` in the same shell as each hosted
command. Forwarding a key does not supply campaign inputs or prove endpoint
access. The agent runtime's `OPENAI_API_KEY` is not a substitute for a NIM key.

## Staging inputs

Put verified fixtures under `evals/files/` and list the relevant files or
directory in each case's `files` array. SkillEvaluator 1.5.6 stages the selected
paths beneath `/workspace/input/`, preserving their paths relative to
`evals/files/`. For example, selecting `evals/files/pdl1_design/` makes its
contents available under `/workspace/input/pdl1_design/`. The same inputs must
be available to both conditions.

Point prompts at those explicit staged paths. For the resume case, either ask
the agent to resume the staged run there or copy it to `runs/rbd_binders` during
pre-agent setup, retaining its artifact paths. A directory name in a prompt
does not create that directory. Record fixture provenance and preserve the
existing completed outputs so the grader can check that they were not recomputed.

Before moving a deferred case back into `evals.json`, update its prompt to name
those staged paths and replace plan-only assertions with execution requirements:
invoke the model APIs, save actual responses,
extract metrics, and update the manifest. Empty CSVs, prepared scripts, and
synthetic confidence values do not establish successful inference. A separate
offline bookkeeping test may use explicitly synthetic data; it cannot stand in
for these live integration cases.

The workflow can be followed through `references/pipeline.md`.
Companion NIM skills are optional; include them in both evaluation conditions
if testing the workflow as a group.

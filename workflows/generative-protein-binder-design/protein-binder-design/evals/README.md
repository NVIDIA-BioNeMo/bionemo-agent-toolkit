# Live evaluation prerequisites

These cases require real campaign inputs and hosted NIM access. Each case and
each with/without-skill attempt starts independently; case 2 or 3 cannot reuse
outputs from case 1. The current dataset declares `files: []` for all three
cases, so it does not stage the inputs below.

| Case | Required inputs |
| --- | --- |
| 1: PD-L1 design | Verified PD-L1 registry entry, matching target structure and chain, author-numbered epitope, binder length range, and shortlist size. |
| 2: Controls | Existing PD-L1 campaign manifest and candidate sequences, matching target structure, and published positive-control sequences with source citations. |
| 3: Resume | The interrupted campaign's manifest and referenced artifacts, including both completed candidates and candidates with missing scores. |

`config.yml` forwards `NGC_API_KEY` from the runner to the agent sandbox. It does
not provide these input files or prove endpoint access. The agent runtime's
`OPENAI_API_KEY` is not a substitute for a NIM key.

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

Keep execution requirements: invoke the model APIs, save actual responses,
extract metrics, and update the manifest. Empty CSVs, prepared scripts, and
synthetic confidence values do not establish successful inference. A separate
offline bookkeeping test may use explicitly synthetic data; it cannot stand in
for these live integration cases.

The skill supports standalone execution through `references/pipeline.md`.
Companion NIM skills are optional; include them in both evaluation conditions
if testing the workflow as a group.

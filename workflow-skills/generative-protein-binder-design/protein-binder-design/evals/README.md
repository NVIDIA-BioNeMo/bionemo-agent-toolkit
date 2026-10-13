# Evaluation coverage and deferred live campaigns

## Active coverage: offline software workflows

`evals.json` runs eight offline exercises. The original task requests, assertions,
expected outputs and score fixtures remain unchanged. Each prompt additionally
identifies the same prepared Python interpreter for both conditions.
Four additional cases require target mapping, saved-response interpretation,
recovery decisions and provenance checks. Their output contracts and all required
inputs are staged in both conditions; equivalent implementations are accepted.

| Case | Input under `/workspace/input/` | Required result |
| --- | --- | --- |
| `offline-manifest` | `bookkeeping.json` | Persistence and ranked exports for ipTM and Boltz2 profiles. |
| `offline-boltz2-ranking` | `boltz2_only.json` | Composite confidence stays separate from ipTM; passing controls do not enter the ranked CSV. |
| `offline-mixed-threshold-ranking` | `mixed_thresholds.json` | All filters apply before sorting; a high ipTM cannot rescue another failing or invalid metric. |
| `offline-empty-ranking` | `no_survivors.json` | A header-only ranked CSV and a complete audit when no designs pass. |
| `offline-target-preparation` | `target_prep/` | Select chain/model/alternate CA; keep insertion codes distinct; block absent hotspots. |
| `offline-refold-extraction` | `raw_refolds/`, `cache_contract.md` | Bind scores to the recorded sample, separate confidence metrics, and use binder-only pLDDT. |
| `offline-cache-resume` | `resume_cache/`, `cache_contract.md` | Preserve complete scores and failure history; recover missing metrics from cache; rebuild stale exports. |
| `offline-provenance-rejection` | `provenance_cache/`, `cache_contract.md` | Reject candidate, sequence, target, sample and response-file mismatches before scoring. |

Every case stages identical inputs for the with/without-skill conditions.
`harbor.pre_agent_setup` in `config.yml` runs the staged `setup_eval_env.py` in
both conditions. It selects an installed Python 3.10-3.13, creates the writable
`/workspace/pbd-eval-venv` virtual environment, installs the same pinned NumPy
2.2.6 and Biotite 1.2.0 wheels, and checks their imports before the agent starts.
These releases provide wheels for Python 3.10 and 3.11 as well as 3.12 and 3.13;
the previous NumPy 2.5.1/Biotite 1.7.1 pins required Python 3.12+. Managed sandbox
images may provide older Python versions, so requiring 3.12 prevented preflight
from reaching dependency installation. The same pins apply to both conditions.
Every prompt specifies `/workspace/pbd-eval-venv/bin/python` for Python commands.
Setup leaves system Python packages untouched and needs no root privileges.
There is no custom `evals/environment/Dockerfile`, so Astra uses its existing
sandbox image without invoking the managed image builder or requiring its token.
The standard sandbox must provide Python 3.10-3.13 with venv/ensurepip, a writable
workspace, and package-index access
for setup. Setup downloads packages; the subsequent exercises
make no network calls. Normal sandbox and agent API access are still required.
Installation or import failures stop environment preflight before agent trials.
Setup reports the chosen interpreter and the phase that failed. Harbor may omit
healthcheck stdout/stderr from its job trace, but it logs the command's exit code
as `Healthcheck failed (rc=...)`. The setup helper uses distinct failure codes:

| Exit code | Failed phase | Check |
| --- | --- | --- |
| 10 | Interpreter selection | An installed Python 3.10-3.13 is discoverable. |
| 11 | Virtual environment creation | venv/ensurepip is installed and the workspace is writable. |
| 12 | Dependency installation | pip can reach the package index and install the pinned wheels within the timeout. |
| 13 | Import verification | The installed NumPy and Biotite versions import successfully. |

All four failures stop preflight; only verified imports return zero. These codes
identify the failing phase, not the underlying cause. The setup helper saves the
bootstrap interpreter version, phase messages, and child-process stdout/stderr
to `/logs/artifacts/pbd-eval-setup.log`. Harbor collects that directory into the
trial's `artifacts/` directory, including on preflight failure. Inspect this file
under the retained `_harbor-preflight/environment-preflight-*/<trial>/artifacts/`
directory to distinguish permissions, index access, wheel compatibility and
import errors. The CI service must retain these Harbor artifacts separately from
the summary report; the summary does not embed the setup transcript. If artifact
storage is unwritable, setup still runs with console diagnostics and the same
failure codes. A generic `rc=1` may mean the helper did not
start or an unexpected error occurred; do not infer a dependency failure from
that code alone. Changing model settings cannot repair environment setup.
These offline cases need no GPU, NIM credentials, or changes to the CI service.
The task requests and fixtures are preserved; the interpreter instruction,
environment and verifier changes must be recorded in historical comparisons.
The added prompts request campaign outputs without giving the expected order;
the assertions check saved artifacts, not use of a particular helper.
All sequences, toy coordinates, numeric inputs, saved responses and control labels are synthetic.
The active `config.yml` forwards no NIM credentials and the cases make no NIM
calls. Passing them establishes **offline software workflow coverage only**, not live model
execution, biological validity, or end-to-end campaign coverage.

Compare agents separately when rerunning: a passing best-agent summary can hide
another agent's regression. Compare the original case against its own previous
result; the expanded suite's aggregate is not directly comparable to the old
one-case score. Positive lift is an observation, not a target for the grader:
keep the baseline inputs and success criteria identical.

Run the bundled regression tests without model access:

```bash
python3 -m unittest discover -s tests -v
```

## Deterministic artifact checks

`grading.mode: aces_plus_custom` runs the existing ACES judges and the standalone
`grader.py`. `config.yml` declares its `artifact_correctness` output under
`grading.custom_metrics` so the evaluator can seal the reward contract before
starting agents. The evaluator computes the schema digest from that declaration
and the grader. The verifier reads actual manifests, CSVs, selected complex files
and summaries. It pins input digests, checks score types and absence, ranking
order, control exclusion, preserved state, source identity and artifact bytes.
It imports no skill helpers. Tests exercise all eight workflows and deliberately
corrupt their outputs to check that the verifier rejects them. The old ambiguous
phrase "ranked candidates.csv" accepts `candidates.csv`, `ranked candidates.csv`
or `ranked_candidates.csv`; new contracts specify `candidates.csv` exactly.

**SkillEvaluator 1.5.6 keeps the ACES headline score and pass@k authoritative.**
The custom binary metric `artifact_correctness` and individual failures appear
in `custom_reward.json` and the rich `aces_reward.json` custom fields. They do
not change the headline score or turn its "All Passed" label into an artifact
gate. Inspect this metric per trial alongside the judges. Do not interpret an
ACES pass with `artifact_correctness=0` as a completed artifact-producing task.

Artifact checks cannot prove an agent actually performed a save/reload step or
made no model calls; the trajectory judges retain those responsibilities. They
also do not prove biological validity. Keep recovery attempts and their tool
results in the judge evidence. To audit a suspicious grade, compare the full
trajectory, the captured judge `prompt_evidence` when available, and verifier
artifacts. Missing transcript evidence is not proof that files were never made.

The eight-case suite uses 32 runs at one trial per case, two agents and both
conditions. Compare the unchanged four-case subset separately from new cases,
and compare agents separately. A fresh live agent evaluation is needed to
measure lift; passing local tests does not predict an improved agent score.

Fixture changes require updating the corresponding `INPUT_HASHES` entries in
`grader.py` and reviewing the hand-calculated `CACHE_RUNS` outcomes. Never derive
expected truth from unverified agent-mutated inputs. The local regression suite
fails on digest drift. Keep contracts identical in both conditions and express
real workflow decisions, rather than making prompts vague or targeting one model.

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

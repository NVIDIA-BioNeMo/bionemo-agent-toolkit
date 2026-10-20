# Skill Benchmark: rfd4-proteina-nim

> ✅ **Overall verdict: PASS — Recommended for publication**

## Publication Recommendation

Recommended for publication based on the completed evaluation evidence in this report.

## Evaluation Metadata

- Skill: `rfd4-proteina-nim`
- Evaluation date: 2026-10-13
- Evaluator version: `1.5.6`
- Agents: Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`), Codex (`openai/openai/gpt-5.5`)
- Tasks: 5 evaluation tasks (5 positive)
- Dataset digest: `sha256:f0c2a36cb6f8e1c81678477d5b8b7fed33996d1a6b7f31320272009e6c953a36` (skill-evaluator-dataset-snapshot/1)
- Attempts per task: 1
- Environment: `k8s-sandbox`
- Tier 2 evidence: required for publication
- Tier 3 evidence: required for publication

Each task attempt ran in its own isolated sandbox pod.

## What This Report Answers

The three-tier evaluation checks whether the skill:

- is safe to use;
- produces correct answers;
- is discovered and activated when needed;
- helps the agent complete the user's goal and expected workflow; and
- avoids wasted skill and tool usage.

## Results at a Glance

| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | Not available | 84.1% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | Not available | 80.0% → 80.0% (±0.0 points) |
| Correctness | Not available | 32.0% → 84.0% (+52.0 points) |
| Discoverability | Not available | 89.0% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | Not available | 35.0% → 76.5% (+41.5 points) |
| Efficiency | Not available | 91.2% — baseline ran, but no comparable score was available; uplift unavailable |

**How to read this table:** baseline is the same task attempted without the target skill. Scores are rounded to one decimal; threshold-adjacent values use additional precision so their displayed band matches the verdict. Uplift is derived from those displayed scores and shown in percentage points.

Example: `47.0% → 92.0% (+45.0 points)` means the skill-assisted run scored 92.0%, 45.0 percentage points above its 47.0% no-skill baseline.

## Token Usage

Actual Tier 3 execution usage is reported for every observed agent/case pair and both conditions.

| Agent | Dataset case | With skill | Without skill | Delta | Change | Coverage |
|---|---|---:|---:|---:|---:|---|
| claude-code | All cases | 2,333,177 | 2,287,391 | +45,786 | +2.00% | skill 5/5; base 5/5 |
| claude-code | condition-spec | 647,875 | 475,447 | +172,428 | +36.27% | skill 1/1; base 1/1 |
| claude-code | local-rc-instructions | 105,080 | 347,202 | -242,122 | -69.74% | skill 1/1; base 1/1 |
| claude-code | offline-search | 783,943 | 737,343 | +46,600 | +6.32% | skill 1/1; base 1/1 |
| claude-code | oracle-and-pending | 63,527 | 347,543 | -284,016 | -81.72% | skill 1/1; base 1/1 |
| claude-code | staging-enzyme | 732,752 | 379,856 | +352,896 | +92.90% | skill 1/1; base 1/1 |
| codex | All cases | 624,263 | 3,021,821 | -2,397,558 | -79.34% | skill 5/5; base 5/5 |
| codex | condition-spec | 66,307 | 90,244 | -23,937 | -26.52% | skill 1/1; base 1/1 |
| codex | local-rc-instructions | 48,769 | 76,050 | -27,281 | -35.87% | skill 1/1; base 1/1 |
| codex | offline-search | 249,759 | 374,076 | -124,317 | -33.23% | skill 1/1; base 1/1 |
| codex | oracle-and-pending | 29,820 | 105,430 | -75,610 | -71.72% | skill 1/1; base 1/1 |
| codex | staging-enzyme | 229,608 | 2,376,021 | -2,146,413 | -90.34% | skill 1/1; base 1/1 |
| ALL AGENTS | Dataset aggregate | 2,957,440 | 5,309,212 | -2,351,772 | -44.30% | skill 10/10; base 10/10 |

Prompt tokens include cached reads, so total tokens are `prompt + completion` (cached is not added twice). The Efficiency score uses `(prompt - cached) + completion`. N/A means the relevant trajectory counters were not available; coverage is never estimated.

## Tier Status

| Tier | Purpose | Status | Evidence |
|---|---|---|---|
| Tier 1 | Static validation | **PASSED WITH OBSERVATIONS** | 11 validator(s); 4 finding(s) |
| Tier 2 | Semantic deduplication | **PASSED** | 2 validator(s); 0 finding(s) |
| Tier 3 | Live agent evaluation | **PASS** | 2 agent(s); 5 task(s) |

## Findings and Observations

<details>
<summary>Show detailed findings and successful checks</summary>

- **MEDIUM** PII/phone_numbers: International phone number (`assets/requests/25_secondary_structure_conditioning.json:8`)
- **MEDIUM** QUALITY/quality_correctness: Instructions don't mention 'run_script' (`skills/rfd4-proteina-nim/SKILL.md`)
- **MEDIUM** SECURITY/Whitespace Padding (P9): Prompt Injection: U+0020 x121 (`assets/requests/16_ppi_binder.json:8`)
- **LOW** SCRIPT_LINT/magic_numbers: design.py contains magic numbers (`skills/rfd4-proteina-nim/scripts/design.py`)

</details>

## Scoring Methodology

<details>
<summary>Show dimension definitions, source signals, and thresholds</summary>

| Dimension | Question | Scored signals |
|---|---|---|
| Security | Is it safe to use? | `security` (100%) |
| Correctness | Is the answer correct? | `accuracy` (100%) |
| Discoverability | Was the right skill loaded when needed? | `skill_execution` (100%) |
| Effectiveness | Did the skill help complete the task? | `goal_accuracy` (50%) + `behavior_check` (50%) |
| Efficiency | Did it avoid wasted tool calls and token usage? | `skill_efficiency` (50%) + `token_efficiency` (50%) |

- Dimension bands: PASS at 50% or above; NEUTRAL from 40% to below 50%; FAIL below 40%.
- Overall Tier 3 lift: PASS at +5 points or more; FAIL at -10 points or less; values between those bands are NEUTRAL.
- Overall verdict: PASS only when every configured dimension passes for at least one supported agent. Lift is reported as diagnostic evidence and does not override this gate.
- The 50% attempt pass threshold is a separate per-task gate; it is not the dimension pass threshold.
- Effectiveness is the equal-weight mean of goal completion (`goal_accuracy`) and expected workflow adherence (`behavior_check`).
- Efficiency is 50% tool-call productivity (the backward-compatible `skill_efficiency` wire id) and 50% `token_efficiency`. Positive-case skill routing is scored under Discoverability, not Efficiency; a negative case without a routing target is N/A. N/A sources are omitted, remaining weights are renormalized, and the dimension is marked partial.

Signals present in this run:

- `security` (Security): unsafe operations, secret leakage, and unauthorized access.
- `skill_execution` (Skill Execution): whether the expected skill was selected, decoys were avoided, and the workflow executed.
- `skill_efficiency` (Tool Productivity): tool-call productivity (legacy wire id; routing is scored under Discoverability).
- `accuracy` (Accuracy): final-answer correctness against the reference answer.
- `goal_accuracy` (Goal Accuracy): whether the user's goal was achieved.
- `behavior_check` (Behavior Check): whether the expected workflow behavior was followed.
- `token_efficiency` (Token Efficiency): actual uncached prompt plus completion usage (50% of Efficiency).

</details>

## Freshness

Regenerate this benchmark when the skill, evaluation dataset, target agent/model, evaluator version, environment, or scoring policy changes.

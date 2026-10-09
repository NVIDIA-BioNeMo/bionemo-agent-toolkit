# Skill Benchmark: complexa-binder-design

> **Overall verdict: NEUTRAL — One or more dimensions remain below PASS**

Live evaluation did not show a material gain or regression. Collect more evidence or improve the skill before making a publication decision.

## Evaluation Metadata

- Skill: `complexa-binder-design`
- Evaluation date: 2026-10-02
- Evaluator version: `1.5.6`
- Agents: Claude Code (`aws/anthropic/bedrock-claude-opus-5`), Codex (`openai/openai/gpt-5.5`)
- Tasks: 4 evaluation tasks (3 positive, 1 negative)
- Dataset digest: `sha256:7c04169e9e3458dcf1e5f59a6c8a6f1ce553d3c49333bb0410b0ecef7bc875c2` (skill-evaluator-dataset-snapshot/1)
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
| Overall | Not available | 56.9% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | Not available | 25.0% → 25.0% (±0.0 points) |
| Correctness | Not available | 80.0% → 80.0% (±0.0 points) |
| Discoverability | Not available | 76.7% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | Not available | 33.1% → 41.3% (+8.2 points) |
| Efficiency | Not available | 61.5% — baseline ran, but no comparable score was available; uplift unavailable |

**How to read this table:** baseline is the same task attempted without the target skill. Scores are rounded to one decimal; threshold-adjacent values use additional precision so their displayed band matches the verdict. Uplift is derived from those displayed scores and shown in percentage points.

Example: `47.0% → 92.0% (+45.0 points)` means the skill-assisted run scored 92.0%, 45.0 percentage points above its 47.0% no-skill baseline.

A partial dimension was calculated from only the available configured signals; review the detailed report before relying on it.

## Token Usage

Actual Tier 3 execution usage is reported for every observed agent/case pair and both conditions.

| Agent | Dataset case | With skill | Without skill | Delta | Change | Coverage |
|---|---|---:|---:|---:|---:|---|
| claude-code | All cases | 4,476,368 | 2,330,154 | +2,146,214 | +92.11% | skill 4/4; base 4/4 |
| claude-code | complexa-binder-design-001 | 1,019,496 | 216,947 | +802,549 | +369.93% | skill 1/1; base 1/1 |
| claude-code | complexa-binder-design-002 | 764,196 | 544,139 | +220,057 | +40.44% | skill 1/1; base 1/1 |
| claude-code | complexa-binder-design-003 | 1,868,266 | 434,440 | +1,433,826 | +330.04% | skill 1/1; base 1/1 |
| claude-code | complexa-binder-design-004 | 824,410 | 1,134,628 | -310,218 | -27.34% | skill 1/1; base 1/1 |
| codex | All cases | 2,314,039 | 1,121,319 | +1,192,720 | +106.37% | skill 4/4; base 4/4 |
| codex | complexa-binder-design-001 | 797,829 | 381,193 | +416,636 | +109.30% | skill 1/1; base 1/1 |
| codex | complexa-binder-design-002 | 763,499 | 267,435 | +496,064 | +185.49% | skill 1/1; base 1/1 |
| codex | complexa-binder-design-003 | 441,580 | 219,628 | +221,952 | +101.06% | skill 1/1; base 1/1 |
| codex | complexa-binder-design-004 | 311,131 | 253,063 | +58,068 | +22.95% | skill 1/1; base 1/1 |
| ALL AGENTS | Dataset aggregate | 6,790,407 | 3,451,473 | +3,338,934 | +96.74% | skill 8/8; base 8/8 |

Prompt tokens include cached reads, so total tokens are `prompt + completion` (cached is not added twice). The Efficiency score uses `(prompt - cached) + completion`. N/A means the relevant trajectory counters were not available; coverage is never estimated.

## Tier Status

| Tier | Purpose | Status | Evidence |
|---|---|---|---|
| Tier 1 | Static validation | **PASSED WITH OBSERVATIONS** | 11 validator(s); 84 finding(s) |
| Tier 2 | Semantic deduplication | **PASSED** | 2 validator(s); 0 finding(s) |
| Tier 3 | Live agent evaluation | **NEUTRAL** | 2 agent(s); 4 task(s) |

## Findings and Observations

<details>
<summary>Show detailed findings and successful checks</summary>

- **MEDIUM** QUALITY/quality_correctness: No documented scripts in table format (`skills/bionemo-agent-toolkit/skills/complexa-binder-design/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: Instructions don't mention 'run_script' (`skills/bionemo-agent-toolkit/skills/complexa-binder-design/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: SKILL_SPEC recommended field missing: 'metadata.author' (`skills/bionemo-agent-toolkit/skills/complexa-binder-design/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: SKILL_SPEC recommended field missing: 'metadata.tags' (`skills/bionemo-agent-toolkit/skills/complexa-binder-design/SKILL.md`)
- **MEDIUM** SCHEMA/folder_hierarchy: Unexpected nesting depth for general skill (`skills/bionemo-agent-toolkit/skills/complexa-binder-design`)
- 79 additional finding(s) are available in the full evaluation artifacts.

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

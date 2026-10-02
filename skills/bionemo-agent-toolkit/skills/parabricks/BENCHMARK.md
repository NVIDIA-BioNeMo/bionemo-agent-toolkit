# Skill Benchmark: parabricks

> ✅ **Overall verdict: PASS — Recommended for publication**

## Publication Recommendation

Recommended for publication based on the completed evaluation evidence in this report.

## Evaluation Metadata

- Skill: `parabricks`
- Evaluation date: 2026-10-02
- Evaluator version: `1.5.6`
- Agents: Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`), Codex (`openai/openai/gpt-5.5`)
- Tasks: 7 evaluation tasks (6 positive, 1 negative)
- Dataset digest: `sha256:23088600f666e241635d67155f709ac6a3b62ee4705f6b793e39fe5421955b6b` (skill-evaluator-dataset-snapshot/1)
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
| Overall | 97.5% — baseline ran, but no comparable score was available; uplift unavailable | 92.1% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | 100.0% → 100.0% (±0.0 points) | 100.0% → 100.0% (±0.0 points) |
| Correctness | 97.1% → 100.0% (+2.9 points) | 100.0% → 100.0% (±0.0 points) |
| Discoverability | 100.0% — baseline ran, but no comparable score was available; uplift unavailable | 82.5% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | 86.8% → 95.7% (+8.9 points) | 90.0% → 93.9% (+3.9 points) |
| Efficiency | 91.9% — baseline ran, but no comparable score was available; uplift unavailable | 84.2% — baseline ran, but no comparable score was available; uplift unavailable |

**How to read this table:** baseline is the same task attempted without the target skill. Scores are rounded to one decimal; threshold-adjacent values use additional precision so their displayed band matches the verdict. Uplift is derived from those displayed scores and shown in percentage points.

Example: `47.0% → 92.0% (+45.0 points)` means the skill-assisted run scored 92.0%, 45.0 percentage points above its 47.0% no-skill baseline.

A partial dimension was calculated from only the available configured signals; review the detailed report before relying on it.

## Token Usage

Actual Tier 3 execution usage is reported for every observed agent/case pair and both conditions.

| Agent | Dataset case | With skill | Without skill | Delta | Change | Coverage |
|---|---|---:|---:|---:|---:|---|
| claude-code | All cases | 901,674 | 457,228 | +444,446 | +97.20% | skill 7/7; base 7/7 |
| claude-code | parabricks-001 | 147,576 | 165,887 | -18,311 | -11.04% | skill 1/1; base 1/1 |
| claude-code | parabricks-002 | 108,530 | 32,270 | +76,260 | +236.32% | skill 1/1; base 1/1 |
| claude-code | parabricks-003 | 152,794 | 36,382 | +116,412 | +319.97% | skill 1/1; base 1/1 |
| claude-code | parabricks-004 | 89,616 | 88,911 | +705 | +0.79% | skill 1/1; base 1/1 |
| claude-code | parabricks-005 | 109,503 | 33,880 | +75,623 | +223.21% | skill 1/1; base 1/1 |
| claude-code | parabricks-006 | 153,772 | 32,885 | +120,887 | +367.61% | skill 1/1; base 1/1 |
| claude-code | parabricks-007 | 139,883 | 67,013 | +72,870 | +108.74% | skill 1/1; base 1/1 |
| codex | All cases | 417,884 | 436,055 | -18,171 | -4.17% | skill 7/7; base 7/7 |
| codex | parabricks-001 | 95,609 | 218,063 | -122,454 | -56.16% | skill 1/1; base 1/1 |
| codex | parabricks-002 | 73,412 | 25,418 | +47,994 | +188.82% | skill 1/1; base 1/1 |
| codex | parabricks-003 | 50,587 | 51,362 | -775 | -1.51% | skill 1/1; base 1/1 |
| codex | parabricks-004 | 29,832 | 31,402 | -1,570 | -5.00% | skill 1/1; base 1/1 |
| codex | parabricks-005 | 92,578 | 46,987 | +45,591 | +97.03% | skill 1/1; base 1/1 |
| codex | parabricks-006 | 26,754 | 42,274 | -15,520 | -36.71% | skill 1/1; base 1/1 |
| codex | parabricks-007 | 49,112 | 20,549 | +28,563 | +139.00% | skill 1/1; base 1/1 |
| ALL AGENTS | Dataset aggregate | 1,319,558 | 893,283 | +426,275 | +47.72% | skill 14/14; base 14/14 |

Prompt tokens include cached reads, so total tokens are `prompt + completion` (cached is not added twice). The Efficiency score uses `(prompt - cached) + completion`. N/A means the relevant trajectory counters were not available; coverage is never estimated.

## Tier Status

| Tier | Purpose | Status | Evidence |
|---|---|---|---|
| Tier 1 | Static validation | **PASSED WITH OBSERVATIONS** | 11 validator(s); 21 finding(s) |
| Tier 2 | Semantic deduplication | **PASSED** | 2 validator(s); 0 finding(s) |
| Tier 3 | Live agent evaluation | **PASS** | 2 agent(s); 7 task(s) |

## Findings and Observations

<details>
<summary>Show detailed findings and successful checks</summary>

- **MEDIUM** QUALITY/quality_correctness: No documented scripts in table format (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: Instructions don't mention 'run_script' (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_efficiency: Deeply nested references in command-conventions.md (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** SCHEMA/folder_hierarchy: Unexpected nesting depth for general skill (`skills/bionemo-agent-toolkit/skills/parabricks`)
- **MEDIUM** SECURITY/Skill Enumeration (AS3): Agent Snooping: skills/parabricks/SKILL.md (`BENCHMARK.md:85`)
- 16 additional finding(s) are available in the full evaluation artifacts.

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

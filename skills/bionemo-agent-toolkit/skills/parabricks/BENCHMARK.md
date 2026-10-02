# Skill Benchmark: parabricks

> **Overall verdict: NEUTRAL — One or more dimensions remain below PASS**

Live evaluation did not show a material gain or regression. Collect more evidence or improve the skill before making a publication decision.

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
| Overall | 97.7% — baseline ran, but no comparable score was available; uplift unavailable | 90.4% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | 92.9% → 100.0% (+7.1 points) | 100.0% → 85.7% (-14.3 points) |
| Correctness | 100.0% → 100.0% (±0.0 points) | 100.0% → 97.1% (-2.9 points) |
| Discoverability | 100.0% — baseline ran, but no comparable score was available; uplift unavailable | 90.8% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | 90.7% → 95.7% (+5.0 points) | 92.5% → 91.8% (-0.7 points) |
| Efficiency | 92.6% — baseline ran, but no comparable score was available; uplift unavailable | 86.5% — baseline ran, but no comparable score was available; uplift unavailable |

**How to read this table:** baseline is the same task attempted without the target skill. Scores are rounded to one decimal; threshold-adjacent values use additional precision so their displayed band matches the verdict. Uplift is derived from those displayed scores and shown in percentage points.

Example: `47.0% → 92.0% (+45.0 points)` means the skill-assisted run scored 92.0%, 45.0 percentage points above its 47.0% no-skill baseline.

A partial dimension was calculated from only the available configured signals; review the detailed report before relying on it.

## Token Usage

Actual Tier 3 execution usage is reported for every observed agent/case pair and both conditions.

| Agent | Dataset case | With skill | Without skill | Delta | Change | Coverage |
|---|---|---:|---:|---:|---:|---|
| claude-code | All cases | 899,318 | 797,018 | +102,300 | +12.84% | skill 7/7; base 7/7 |
| claude-code | parabricks-001 | 189,916 | 94,442 | +95,474 | +101.09% | skill 1/1; base 1/1 |
| claude-code | parabricks-002 | 108,275 | 32,520 | +75,755 | +232.95% | skill 1/1; base 1/1 |
| claude-code | parabricks-003 | 110,319 | 35,593 | +74,726 | +209.95% | skill 1/1; base 1/1 |
| claude-code | parabricks-004 | 89,508 | 89,759 | -251 | -0.28% | skill 1/1; base 1/1 |
| claude-code | parabricks-005 | 109,141 | 475,722 | -366,581 | -77.06% | skill 1/1; base 1/1 |
| claude-code | parabricks-006 | 150,542 | 33,876 | +116,666 | +344.39% | skill 1/1; base 1/1 |
| claude-code | parabricks-007 | 141,617 | 35,106 | +106,511 | +303.40% | skill 1/1; base 1/1 |
| codex | All cases | 497,020 | 404,474 | +92,546 | +22.88% | skill 7/7; base 7/7 |
| codex | parabricks-001 | 72,578 | 180,556 | -107,978 | -59.80% | skill 1/1; base 1/1 |
| codex | parabricks-002 | 94,556 | 26,238 | +68,318 | +260.38% | skill 1/1; base 1/1 |
| codex | parabricks-003 | 94,784 | 65,847 | +28,937 | +43.95% | skill 1/1; base 1/1 |
| codex | parabricks-004 | 35,579 | 32,844 | +2,735 | +8.33% | skill 1/1; base 1/1 |
| codex | parabricks-005 | 92,357 | 38,840 | +53,517 | +137.79% | skill 1/1; base 1/1 |
| codex | parabricks-006 | 51,100 | 39,778 | +11,322 | +28.46% | skill 1/1; base 1/1 |
| codex | parabricks-007 | 56,066 | 20,371 | +35,695 | +175.22% | skill 1/1; base 1/1 |
| ALL AGENTS | Dataset aggregate | 1,396,338 | 1,201,492 | +194,846 | +16.22% | skill 14/14; base 14/14 |

Prompt tokens include cached reads, so total tokens are `prompt + completion` (cached is not added twice). The Efficiency score uses `(prompt - cached) + completion`. N/A means the relevant trajectory counters were not available; coverage is never estimated.

## Tier Status

| Tier | Purpose | Status | Evidence |
|---|---|---|---|
| Tier 1 | Static validation | **PASSED WITH OBSERVATIONS** | 11 validator(s); 23 finding(s) |
| Tier 2 | Semantic deduplication | **PASSED** | 2 validator(s); 0 finding(s) |
| Tier 3 | Live agent evaluation | **NEUTRAL** | 2 agent(s); 7 task(s) |

## Findings and Observations

<details>
<summary>Show detailed findings and successful checks</summary>

- **MEDIUM** QUALITY/quality_correctness: No documented scripts in table format (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: Instructions don't mention 'run_script' (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_efficiency: Deeply nested references in command-conventions.md (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** SCHEMA/folder_hierarchy: Unexpected nesting depth for general skill (`skills/bionemo-agent-toolkit/skills/parabricks`)
- **MEDIUM** SECURITY/Skill Enumeration (AS3): Agent Snooping: skills/parabricks/SKILL.md (`BENCHMARK.md:90`)
- 18 additional finding(s) are available in the full evaluation artifacts.

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

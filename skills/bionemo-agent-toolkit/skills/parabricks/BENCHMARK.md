# Skill Benchmark: parabricks

> ✅ **Overall verdict: PASS — Recommended for publication**

## Publication Recommendation

Recommended for publication based on the completed evaluation evidence in this report.

## Evaluation Metadata

- Skill: `parabricks`
- Evaluation date: 2026-10-02
- Evaluator version: `1.5.6`
- Agents: Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`), Codex (`openai/openai/gpt-5.5`)
- Tasks: 4 evaluation tasks (3 positive, 1 negative)
- Dataset digest: `sha256:0869b17117b1efb7db74851dc63388a08da9e8de96f68b0dd2dfddd8d3f33848` (skill-evaluator-dataset-snapshot/1)
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
| Overall | 90.5% — baseline ran, but no comparable score was available; uplift unavailable | 83.0% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | 100.0% → 100.0% (±0.0 points) | 50.0% → 100.0% (+50.0 points) |
| Correctness | 85.0% → 100.0% (+15.0 points) | 100.0% → 90.0% (-10.0 points) |
| Discoverability | 93.3% — baseline ran, but no comparable score was available; uplift unavailable | 88.3% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | 58.8% → 75.6% (+16.8 points) | 61.3% → 77.5% (+16.2 points) |
| Efficiency | 83.4% — baseline ran, but no comparable score was available; uplift unavailable | 58.9% — baseline ran, but no comparable score was available; uplift unavailable |

**How to read this table:** baseline is the same task attempted without the target skill. Scores are rounded to one decimal; threshold-adjacent values use additional precision so their displayed band matches the verdict. Uplift is derived from those displayed scores and shown in percentage points.

Example: `47.0% → 92.0% (+45.0 points)` means the skill-assisted run scored 92.0%, 45.0 percentage points above its 47.0% no-skill baseline.

A partial dimension was calculated from only the available configured signals; review the detailed report before relying on it.

## Token Usage

Actual Tier 3 execution usage is reported for every observed agent/case pair and both conditions.

| Agent | Dataset case | With skill | Without skill | Delta | Change | Coverage |
|---|---|---:|---:|---:|---:|---|
| claude-code | All cases | 1,825,378 | 1,863,825 | -38,447 | -2.06% | skill 4/4; base 4/4 |
| claude-code | parabricks-001 | 144,138 | 375,756 | -231,618 | -61.64% | skill 1/1; base 1/1 |
| claude-code | parabricks-002 | 162,784 | 31,774 | +131,010 | +412.32% | skill 1/1; base 1/1 |
| claude-code | parabricks-003 | 318,565 | 98,924 | +219,641 | +222.03% | skill 1/1; base 1/1 |
| claude-code | parabricks-004 | 1,199,891 | 1,357,371 | -157,480 | -11.60% | skill 1/1; base 1/1 |
| codex | All cases | 900,320 | 965,760 | -65,440 | -6.78% | skill 4/4; base 4/4 |
| codex | parabricks-001 | 88,500 | 187,235 | -98,735 | -52.73% | skill 1/1; base 1/1 |
| codex | parabricks-002 | 92,879 | 52,380 | +40,499 | +77.32% | skill 1/1; base 1/1 |
| codex | parabricks-003 | 302,112 | 245,674 | +56,438 | +22.97% | skill 1/1; base 1/1 |
| codex | parabricks-004 | 416,829 | 480,471 | -63,642 | -13.25% | skill 1/1; base 1/1 |
| ALL AGENTS | Dataset aggregate | 2,725,698 | 2,829,585 | -103,887 | -3.67% | skill 8/8; base 8/8 |

Prompt tokens include cached reads, so total tokens are `prompt + completion` (cached is not added twice). The Efficiency score uses `(prompt - cached) + completion`. N/A means the relevant trajectory counters were not available; coverage is never estimated.

## Tier Status

| Tier | Purpose | Status | Evidence |
|---|---|---|---|
| Tier 1 | Static validation | **PASSED WITH OBSERVATIONS** | 11 validator(s); 17 finding(s) |
| Tier 2 | Semantic deduplication | **PASSED WITH OBSERVATIONS** | 2 validator(s); 1 finding(s) |
| Tier 3 | Live agent evaluation | **PASS** | 2 agent(s); 4 task(s) |

## Findings and Observations

<details>
<summary>Show detailed findings and successful checks</summary>

- **HIGH** DUPLICATE/duplicate: Duplicate content found across SKILL.md and references/tool-index.md:
  "## Key References" in SKILL.md (lines 157-166)
  vs "## Key References" in references/tool-index.md (lines 36-42) (`SKILL.md:157`)
- **MEDIUM** QUALITY/quality_correctness: No documented scripts in table format (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: Instructions don't mention 'run_script' (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_efficiency: Deeply nested references in command-conventions.md (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** SCHEMA/folder_hierarchy: Unexpected nesting depth for general skill (`skills/bionemo-agent-toolkit/skills/parabricks`)
- 13 additional finding(s) are available in the full evaluation artifacts.

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

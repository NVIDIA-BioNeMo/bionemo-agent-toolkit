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
| Overall | 97.7% — baseline ran, but no comparable score was available; uplift unavailable | 96.5% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | 92.9% → 100.0% (+7.1 points) | 100.0% → 100.0% (±0.0 points) |
| Correctness | 100.0% → 100.0% (±0.0 points) | 100.0% → 100.0% (±0.0 points) |
| Discoverability | 100.0% — baseline ran, but no comparable score was available; uplift unavailable | 95.0% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | 92.1% → 97.1% (+5.0 points) | 92.5% → 98.6% (+6.1 points) |
| Efficiency | 91.1% — baseline ran, but no comparable score was available; uplift unavailable | 88.9% — baseline ran, but no comparable score was available; uplift unavailable |

**How to read this table:** baseline is the same task attempted without the target skill. Scores are rounded to one decimal; threshold-adjacent values use additional precision so their displayed band matches the verdict. Uplift is derived from those displayed scores and shown in percentage points.

Example: `47.0% → 92.0% (+45.0 points)` means the skill-assisted run scored 92.0%, 45.0 percentage points above its 47.0% no-skill baseline.

A partial dimension was calculated from only the available configured signals; review the detailed report before relying on it.

## Token Usage

Actual Tier 3 execution usage is reported for every observed agent/case pair and both conditions.

| Agent | Dataset case | With skill | Without skill | Delta | Change | Coverage |
|---|---|---:|---:|---:|---:|---|
| claude-code | All cases | 807,129 | 551,867 | +255,262 | +46.25% | skill 7/7; base 7/7 |
| claude-code | parabricks-001 | 108,772 | 63,115 | +45,657 | +72.34% | skill 1/1; base 1/1 |
| claude-code | parabricks-002 | 108,969 | 32,360 | +76,609 | +236.74% | skill 1/1; base 1/1 |
| claude-code | parabricks-003 | 154,654 | 37,221 | +117,433 | +315.50% | skill 1/1; base 1/1 |
| claude-code | parabricks-004 | 30,832 | 59,817 | -28,985 | -48.46% | skill 1/1; base 1/1 |
| claude-code | parabricks-005 | 109,717 | 291,536 | -181,819 | -62.37% | skill 1/1; base 1/1 |
| claude-code | parabricks-006 | 153,958 | 33,819 | +120,139 | +355.24% | skill 1/1; base 1/1 |
| claude-code | parabricks-007 | 140,227 | 33,999 | +106,228 | +312.44% | skill 1/1; base 1/1 |
| codex | All cases | 558,018 | 520,851 | +37,167 | +7.14% | skill 7/7; base 7/7 |
| codex | parabricks-001 | 196,199 | 223,790 | -27,591 | -12.33% | skill 1/1; base 1/1 |
| codex | parabricks-002 | 73,991 | 43,882 | +30,109 | +68.61% | skill 1/1; base 1/1 |
| codex | parabricks-003 | 78,929 | 116,728 | -37,799 | -32.38% | skill 1/1; base 1/1 |
| codex | parabricks-004 | 35,458 | 24,484 | +10,974 | +44.82% | skill 1/1; base 1/1 |
| codex | parabricks-005 | 73,270 | 38,564 | +34,706 | +90.00% | skill 1/1; base 1/1 |
| codex | parabricks-006 | 51,157 | 44,121 | +7,036 | +15.95% | skill 1/1; base 1/1 |
| codex | parabricks-007 | 49,014 | 29,282 | +19,732 | +67.39% | skill 1/1; base 1/1 |
| ALL AGENTS | Dataset aggregate | 1,365,147 | 1,072,718 | +292,429 | +27.26% | skill 14/14; base 14/14 |

Prompt tokens include cached reads, so total tokens are `prompt + completion` (cached is not added twice). The Efficiency score uses `(prompt - cached) + completion`. N/A means the relevant trajectory counters were not available; coverage is never estimated.

## Tier Status

| Tier | Purpose | Status | Evidence |
|---|---|---|---|
| Tier 1 | Static validation | **PASSED WITH OBSERVATIONS** | 11 validator(s); 21 finding(s) |
| Tier 2 | Semantic deduplication | **PASSED** | 2 validator(s); 0 finding(s) |
| Tier 3 | Live agent evaluation | **NEUTRAL** | 2 agent(s); 7 task(s) |

## Findings and Observations

<details>
<summary>Show detailed findings and successful checks</summary>

- **MEDIUM** QUALITY/quality_correctness: No documented scripts in table format (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: Instructions don't mention 'run_script' (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_efficiency: Deeply nested references in command-conventions.md (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** SCHEMA/folder_hierarchy: Unexpected nesting depth for general skill (`skills/bionemo-agent-toolkit/skills/parabricks`)
- **MEDIUM** SECURITY/Skill Enumeration (AS3): Agent Snooping: skills/parabricks/SKILL.md (`BENCHMARK.md:88`)
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

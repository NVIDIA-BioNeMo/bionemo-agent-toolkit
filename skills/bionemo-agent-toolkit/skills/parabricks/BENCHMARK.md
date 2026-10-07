# Skill Benchmark: parabricks

> **Overall verdict: NEUTRAL — One or more dimensions remain below PASS**

Live evaluation did not show a material gain or regression. Collect more evidence or improve the skill before making a publication decision.

## Evaluation Metadata

- Skill: `parabricks`
- Evaluation date: 2026-10-07
- Evaluator version: `1.5.6`
- Agents: Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`), Codex (`openai/openai/gpt-5.5`)
- Tasks: 18 evaluation tasks (17 positive, 1 negative)
- Dataset digest: `sha256:6e9efe466a1409e4cbcd58924a921028b12d3af7cce343c86b975cfbf78f9f1b` (skill-evaluator-dataset-snapshot/1)
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
| Overall | Not available | 92.9% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | Not available | 100.0% → 100.0% (±0.0 points) |
| Correctness | Not available | 98.9% → 98.9% (±0.0 points) |
| Discoverability | Not available | 93.5% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | Not available | 84.7% → 92.2% (+7.5 points) |
| Efficiency | Not available | 79.8% — baseline ran, but no comparable score was available; uplift unavailable |

**How to read this table:** baseline is the same task attempted without the target skill. Scores are rounded to one decimal; threshold-adjacent values use additional precision so their displayed band matches the verdict. Uplift is derived from those displayed scores and shown in percentage points.

Example: `47.0% → 92.0% (+45.0 points)` means the skill-assisted run scored 92.0%, 45.0 percentage points above its 47.0% no-skill baseline.

A partial dimension was calculated from only the available configured signals; review the detailed report before relying on it.

## Token Usage

Actual Tier 3 execution usage is reported for every observed agent/case pair and both conditions.

| Agent | Dataset case | With skill | Without skill | Delta | Change | Coverage |
|---|---|---:|---:|---:|---:|---|
| claude-code | All cases | 3,438,952 | 7,250,306 | N/A | N/A | skill 18/18; base 17/18 |
| claude-code | parabricks-001 | 150,107 | 95,083 | +55,024 | +57.87% | skill 1/1; base 1/1 |
| claude-code | parabricks-002 | 111,652 | 31,916 | +79,736 | +249.83% | skill 1/1; base 1/1 |
| claude-code | parabricks-003 | 155,299 | 36,848 | +118,451 | +321.46% | skill 1/1; base 1/1 |
| claude-code | parabricks-004 | 31,052 | 89,036 | -57,984 | -65.12% | skill 1/1; base 1/1 |
| claude-code | parabricks-005 | 251,751 | 728,795 | -477,044 | -65.46% | skill 1/1; base 1/1 |
| claude-code | parabricks-006 | 112,288 | 29,045 | +83,243 | +286.60% | skill 1/1; base 1/1 |
| claude-code | parabricks-007 | 140,862 | 425,184 | -284,322 | -66.87% | skill 1/1; base 1/1 |
| claude-code | parabricks-008 | 108,679 | 32,043 | +76,636 | +239.17% | skill 1/1; base 1/1 |
| claude-code | parabricks-009 | 159,806 | N/A | N/A | N/A | skill 1/1; base 0/1 |
| claude-code | parabricks-010 | 201,640 | 161,491 | +40,149 | +24.86% | skill 1/1; base 1/1 |
| claude-code | parabricks-011 | 109,303 | 221,441 | -112,138 | -50.64% | skill 1/1; base 1/1 |
| claude-code | parabricks-012 | 108,819 | 256,318 | -147,499 | -57.55% | skill 1/1; base 1/1 |
| claude-code | parabricks-013 | 117,842 | 425,822 | -307,980 | -72.33% | skill 1/1; base 1/1 |
| claude-code | parabricks-014 | 109,132 | 309,748 | -200,616 | -64.77% | skill 1/1; base 1/1 |
| claude-code | parabricks-015 | 156,365 | 74,473 | +81,892 | +109.96% | skill 1/1; base 1/1 |
| claude-code | parabricks-016 | 235,192 | 1,752,549 | -1,517,357 | -86.58% | skill 1/1; base 1/1 |
| claude-code | parabricks-017 | 865,406 | 385,643 | +479,763 | +124.41% | skill 1/1; base 1/1 |
| claude-code | parabricks-018 | 313,757 | 2,194,871 | -1,881,114 | -85.70% | skill 1/1; base 1/1 |
| codex | All cases | 1,677,233 | 1,107,638 | +569,595 | +51.42% | skill 18/18; base 18/18 |
| codex | parabricks-001 | 69,575 | 216,141 | -146,566 | -67.81% | skill 1/1; base 1/1 |
| codex | parabricks-002 | 100,363 | 26,376 | +73,987 | +280.51% | skill 1/1; base 1/1 |
| codex | parabricks-003 | 92,668 | 51,074 | +41,594 | +81.44% | skill 1/1; base 1/1 |
| codex | parabricks-004 | 18,363 | 17,901 | +462 | +2.58% | skill 1/1; base 1/1 |
| codex | parabricks-005 | 112,733 | 45,513 | +67,220 | +147.69% | skill 1/1; base 1/1 |
| codex | parabricks-006 | 115,310 | 31,950 | +83,360 | +260.91% | skill 1/1; base 1/1 |
| codex | parabricks-007 | 48,871 | 41,965 | +6,906 | +16.46% | skill 1/1; base 1/1 |
| codex | parabricks-008 | 49,862 | 36,559 | +13,303 | +36.39% | skill 1/1; base 1/1 |
| codex | parabricks-009 | 63,065 | 54,894 | +8,171 | +14.89% | skill 1/1; base 1/1 |
| codex | parabricks-010 | 65,027 | 32,702 | +32,325 | +98.85% | skill 1/1; base 1/1 |
| codex | parabricks-011 | 50,512 | 33,697 | +16,815 | +49.90% | skill 1/1; base 1/1 |
| codex | parabricks-012 | 64,253 | 49,168 | +15,085 | +30.68% | skill 1/1; base 1/1 |
| codex | parabricks-013 | 95,233 | 39,435 | +55,798 | +141.49% | skill 1/1; base 1/1 |
| codex | parabricks-014 | 50,246 | 32,054 | +18,192 | +56.75% | skill 1/1; base 1/1 |
| codex | parabricks-015 | 65,798 | 40,876 | +24,922 | +60.97% | skill 1/1; base 1/1 |
| codex | parabricks-016 | 182,971 | 156,538 | +26,433 | +16.89% | skill 1/1; base 1/1 |
| codex | parabricks-017 | 310,033 | 111,002 | +199,031 | +179.30% | skill 1/1; base 1/1 |
| codex | parabricks-018 | 122,350 | 89,793 | +32,557 | +36.26% | skill 1/1; base 1/1 |
| ALL AGENTS | Dataset aggregate | 5,116,185 | 8,357,944 | N/A | N/A | skill 36/36; base 35/36 |

Prompt tokens include cached reads, so total tokens are `prompt + completion` (cached is not added twice). The Efficiency score uses `(prompt - cached) + completion`. N/A means the relevant trajectory counters were not available; coverage is never estimated.

## Tier Status

| Tier | Purpose | Status | Evidence |
|---|---|---|---|
| Tier 1 | Static validation | **PASSED WITH OBSERVATIONS** | 11 validator(s); 24 finding(s) |
| Tier 2 | Semantic deduplication | **PASSED WITH OBSERVATIONS** | 2 validator(s); 1 finding(s) |
| Tier 3 | Live agent evaluation | **NEUTRAL** | 2 agent(s); 18 task(s) |

## Findings and Observations

<details>
<summary>Show detailed findings and successful checks</summary>

- **CRITICAL** CONTENT_DEDUP/llm_prompt_size_limit: A Tier 2 cluster exceeds the LLM prompt character limit. (`skills/bionemo-agent-toolkit/skills/parabricks`)
- **MEDIUM** QUALITY/quality_correctness: No documented scripts in table format (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_correctness: Instructions don't mention 'run_script' (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** QUALITY/quality_efficiency: Deeply nested references in command-conventions.md (`skills/bionemo-agent-toolkit/skills/parabricks/SKILL.md`)
- **MEDIUM** SCHEMA/folder_hierarchy: Unexpected nesting depth for general skill (`skills/bionemo-agent-toolkit/skills/parabricks`)
- 20 additional finding(s) are available in the full evaluation artifacts.

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

## Description: <br>
Route NVIDIA Parabricks pbrun tools, assess GPU/runtime readiness, and provide version-aware command guidance for FASTQ/BAM processing, RNA-seq, variant calling, BAM QC, and GVCF workflows. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
CC-BY-4.0 AND Apache-2.0 <br>
## Use Case: <br>
Developers and bioinformatics engineers use this skill to identify the right NVIDIA Parabricks pbrun command, check GPU/runtime readiness, and generate version-aware command guidance for genomics workloads including FASTQ/BAM processing, RNA-seq, variant calling, and GVCF workflows. <br>

### Deployment Geography for Use: <br>
Global <br>

## Requirements / Dependencies: <br>
**Requires API Key or External Credential:** [Not Specified] <br>
**Credential Type(s):** [None identified] <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

## Known Risks and Mitigations: <br>
Risk: Review before execution as proposals could introduce incorrect or misleading guidance into skills. <br>
Mitigation: Review and scan skill before deployment. <br>

## Reference(s): <br>
- [Parabricks Tool Reference](https://docs.nvidia.com/clara/parabricks/latest/toolreference.html) <br>
- [Output Accuracy and Compatible CPU Software Versions](https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/outputaccuracyandcompatiblecpusoftwareversions.html) <br>
- [Getting Started](https://docs.nvidia.com/clara/parabricks/latest/gettingstarted.html) <br>
- [Parabricks Overview](https://docs.nvidia.com/clara/parabricks/latest/overview.html) <br>
- [Tool Index](references/tool-index.md) <br>
- [Runtime Environment](references/runtime-environment.md) <br>
- [Command Conventions](references/command-conventions.md) <br>
- [Shared Options](references/shared-options.md) <br>
- [Performance](references/performance.md) <br>


## Skill Output: <br>
**Output Type(s):** [Shell commands, Configuration instructions, Analysis] <br>
**Output Format:** [Markdown with inline bash code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [None] <br>

## Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
4 evaluation tasks (3 positive, 1 negative), each in an isolated k8s-sandbox pod. Evaluator version 1.5.6. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Is it safe to use? Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Is the answer correct? Validates final-answer correctness against the reference answer. <br>
- Discoverability: Was the right skill loaded when needed? Checks whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- Effectiveness: Did the skill help complete the task? Equal-weight mean of goal completion and expected workflow adherence. <br>
- Efficiency: Did it avoid wasted tool calls and token usage? 50% tool-call productivity and 50% token efficiency. <br>

Underlying evaluation signals used in this run: <br>
- `security`: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- `skill_execution`: Whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `skill_efficiency`: Tool-call productivity (routing is scored under Discoverability). <br>
- `token_efficiency`: Actual uncached prompt plus completion token usage. <br>



## Evaluation Results: <br>
| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | 90.5% | 83.0% |
| Security | 100.0% → 100.0% (±0.0 pts) | 50.0% → 100.0% (+50.0 pts) |
| Correctness | 85.0% → 100.0% (+15.0 pts) | 100.0% → 90.0% (-10.0 pts) |
| Discoverability | 93.3% | 88.3% |
| Effectiveness | 58.8% → 75.6% (+16.8 pts) | 61.3% → 77.5% (+16.2 pts) |
| Efficiency | 83.4% | 58.9% |

## Skill Version(s): <br>
1.1.0 (source: frontmatter) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>

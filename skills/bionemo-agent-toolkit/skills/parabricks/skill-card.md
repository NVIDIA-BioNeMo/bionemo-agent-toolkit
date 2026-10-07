## Description: <br>
Select NVIDIA Parabricks pbrun tools, assess GPU/runtime readiness, and provide version-aware commands for FASTQ/BAM processing, RNA-seq, variant calling, BAM QC, and GVCF workflows. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
CC-BY-4.0 AND Apache-2.0 <br>
## Use Case: <br>
Developers and bioinformatics engineers who need to select the right Parabricks pbrun tool, check GPU and container runtime readiness, and generate version-aware Docker commands for genomics workflows. <br>

### Deployment Geography for Use: <br>
Global <br>

## Requirements / Dependencies: <br>
**Requires API Key or External Credential:** [Optional] <br>
**Credential Type(s):** [API key] <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

## Known Risks and Mitigations: <br>
Risk: Review before execution as proposals could introduce incorrect or misleading guidance into skills. <br>
Mitigation: Review and scan skill before deployment. <br>

## Reference(s): <br>
- [tool-index.md](references/tool-index.md) <br>
- [runtime-environment.md](references/runtime-environment.md) <br>
- [command-conventions.md](references/command-conventions.md) <br>
- [performance.md](references/performance.md) <br>
- [Parabricks Release Notes](https://docs.nvidia.com/clara/parabricks/about-parabricks/release-notes) <br>


## Skill Output: <br>
**Output Type(s):** [Shell commands, Configuration instructions, Analysis] <br>
**Output Format:** [Markdown with inline bash code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [None] <br>

## Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
18 evaluation tasks (17 positive, 1 negative) run in isolated sandbox pods; dataset digest sha256:6e9efe466a1409e4cbcd58924a921028b12d3af7cce343c86b975cfbf78f9f1b. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Whether the skill avoids unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Final-answer correctness against the reference answer. <br>
- Discoverability: Whether the expected skill was selected and decoys were avoided. <br>
- Effectiveness: Whether the skill helped complete the user's goal (50% goal completion + 50% expected workflow adherence). <br>
- Efficiency: Tool-call productivity (50%) and token efficiency (50%). <br>

Underlying evaluation signals used in this run: <br>
- `security`: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `skill_execution`: Whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `skill_efficiency`: Tool-call productivity. <br>
- `token_efficiency`: Actual uncached prompt plus completion token usage. <br>



## Evaluation Results: <br>
| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | Not available | 92.9% — baseline ran, but no comparable score was available; uplift unavailable |
| Security | Not available | 100.0% → 100.0% (±0.0 points) |
| Correctness | Not available | 98.9% → 98.9% (±0.0 points) |
| Discoverability | Not available | 93.5% — baseline ran, but no comparable score was available; uplift unavailable |
| Effectiveness | Not available | 84.7% → 92.2% (+7.5 points) |
| Efficiency | Not available | 79.8% — baseline ran, but no comparable score was available; uplift unavailable |

## Skill Version(s): <br>
1.2.1 (source: frontmatter) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>

## Description: <br>
Generate novel drug-like molecules using the GenMol NIM microservice. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
Apache-2.0 AND CC-BY-4.0 <br>
## Use Case: <br>
Developers and computational chemists who need to generate novel drug-like molecules for de novo molecular design, scaffold decoration, motif extension, or lead optimization using the GenMol NIM microservice. <br>

### Deployment Geography for Use: <br>
Global <br>

## Requirements / Dependencies: <br>
**Requires API Key or External Credential:** [Yes] <br>
**Credential Type(s):** [API key] <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

## Known Risks and Mitigations: <br>
Risk: Review before execution as proposals could introduce incorrect or misleading guidance into skills. <br>
Mitigation: Review and scan skill before deployment. <br>

## Reference(s): <br>
- [GenMol NIM Full API Reference](references/api.md) <br>
- [GenMol Examples](references/examples.md) <br>
- [GenMol Parameter Guidance](references/parameters.md) <br>
- [GenMol Science Notes](references/science.md) <br>
- [GenMol Validation](references/validation.md) <br>


## Skill Output: <br>
**Output Type(s):** [API Calls, Code, Files] <br>
**Output Format:** [Python code blocks with JSON API responses and .smi tabular output] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [None] <br>

## Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
1 evaluation task (1 positive), 3 attempts per task, evaluated in isolated k8s-sandbox pods. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Final-answer correctness against the reference answer. <br>
- Discoverability: Whether the expected skill was selected and activated when needed. <br>
- Effectiveness: Goal completion (50%) combined with expected workflow adherence (50%). <br>
- Efficiency: Tool-call productivity (50%) combined with token efficiency (50%). <br>

Underlying evaluation signals used in this run: <br>
- `security`: Unsafe operations, secret leakage, and unauthorized access. <br>
- `skill_execution`: Whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- `skill_efficiency`: Tool-call productivity relative to expected tool usage. <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `token_efficiency`: Actual uncached prompt plus completion token usage. <br>



## Evaluation Results: <br>
| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | 86.2% | 86.5% |
| Security | 100.0% → 100.0% (±0.0 pts) | 100.0% → 50.0% (-50.0 pts) |
| Correctness | 60.0% → 100.0% (+40.0 pts) | 100.0% → 100.0% (±0.0 pts) |
| Discoverability | 100.0% | 95.0% |
| Effectiveness | 77.9% → 57.9% (-20.0 pts) | 62.9% → 100.0% (+37.1 pts) |
| Efficiency | 73.1% | 87.7% |

## Skill Version(s): <br>
0.1.0 (source: pyproject.toml) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>

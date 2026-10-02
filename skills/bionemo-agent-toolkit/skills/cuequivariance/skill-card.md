## Description: <br>
Build and debug cuEquivariance irreps, custom Irrep subclasses, Clebsch-Gordan tensor products, and equivariant or segmented polynomials. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
Apache 2.0 <br>
## Use Case: <br>
Developers and engineers building equivariant neural networks use this skill to construct, inspect, and debug cuEquivariance group representations, tensor-product descriptors, and segmented polynomials. <br>

### Deployment Geography for Use: <br>
Global <br>

## Requirements / Dependencies: <br>
**Requires API Key or External Credential:** [No] <br>
**Credential Type(s):** [None] <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

## Known Risks and Mitigations: <br>
Risk: Review before execution as proposals could introduce incorrect or misleading guidance into skills. <br>
Mitigation: Review and scan skill before deployment. <br>

## Reference(s): <br>
- [Custom Irrep subclasses](references/custom-irreps.md) <br>
- [Irrep dictionaries and IrDictPolynomial](references/ir-dict.md) <br>
- [Segmented tensor products and polynomials](references/segmented-polynomials.md) <br>
- [cuEquivariance official documentation](https://docs.nvidia.com/cuda/cuequivariance/) <br>
- [cuEquivariance 0.12.0 source](https://github.com/NVIDIA/cuEquivariance/tree/v0.12.0) <br>


## Skill Output: <br>
**Output Type(s):** [Code, Analysis] <br>
**Output Format:** [Markdown with inline Python code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [None] <br>

## Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
6 evaluation tasks (5 positive, 1 negative) in isolated k8s-sandbox pods, 1 attempt per task. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Whether the skill is safe to use — checks for unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Whether the final answer is correct against the reference answer. <br>
- Discoverability: Whether the right skill was loaded when needed — skill selection, decoy avoidance, and workflow execution. <br>
- Effectiveness: Whether the skill helped complete the task — goal completion (50%) and expected workflow adherence (50%). <br>
- Efficiency: Whether the skill avoided wasted tool calls and token usage — tool-call productivity (50%) and token efficiency (50%). <br>

Underlying evaluation signals used in this run: <br>
- `security`: Unsafe operations, secret leakage, and unauthorized access. <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `skill_execution`: Whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `skill_efficiency`: Tool-call productivity (legacy wire id; routing is scored under Discoverability). <br>
- `token_efficiency`: Actual uncached prompt plus completion usage. <br>



## Evaluation Results: <br>
| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | 85.8% | 91.1% |
| Security | 100.0% → 66.7% (-33.3 pts) | 100.0% → 83.3% (-16.7 pts) |
| Correctness | 100.0% → 100.0% (±0.0 pts) | 100.0% → 100.0% (±0.0 pts) |
| Discoverability | 88.0% | 94.0% |
| Effectiveness | 88.2% → 97.1% (+8.9 pts) | 78.3% → 83.9% (+5.6 pts) |
| Efficiency | 77.3% | 94.1% |

## Skill Version(s): <br>
0.1.0 (source: pyproject.toml) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>

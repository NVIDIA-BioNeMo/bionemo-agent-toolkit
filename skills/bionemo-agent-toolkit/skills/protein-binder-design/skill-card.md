## Description: <br>
Orchestrate an end-to-end de novo protein binder design campaign against a protein target by composing BioNeMo NIM skills. <br>

The published evaluation of revision `1213167` has a **NEUTRAL** verdict; readiness for deployment has not been established. The [benchmark](BENCHMARK.md) covers one offline bookkeeping task, not a live binder-design campaign. Gather further evidence or improve and re-evaluate the skill before a publication or deployment decision. License terms below describe permitted use, not validation readiness. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
Apache 2.0 <br>
## Use Case: <br>
Developers and computational biologists designing de novo protein binders against protein targets using agent-orchestrated BioNeMo NIM pipelines (RFdiffusion, ProteinMPNN, Boltz2/OpenFold3). <br>

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
- [pipeline.md](references/pipeline.md) <br>
- [validation.md](references/validation.md) <br>
- [manifest.md](references/manifest.md) <br>
- [local-nim-setup.md](references/local-nim-setup.md) <br>
- [NVIDIA BioNeMo NIMs](https://build.nvidia.com) <br>


## Skill Output: <br>
**Output Type(s):** [Shell commands, Files, Analysis] <br>
**Output Format:** [Markdown with inline bash code blocks, JSON manifest, CSV ranking] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Produces manifest.json, candidates.csv, and PDB artifact files per campaign run] <br>

## Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-5`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
1 evaluation task (1 positive) executed in isolated k8s-sandbox pods; evaluator version 1.5.6. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Final-answer correctness against the reference answer. <br>
- Discoverability: Whether the expected skill was selected and activated when needed. <br>
- Effectiveness: Whether the skill helped complete the user's goal (50% goal_accuracy + 50% behavior_check). <br>
- Efficiency: Tool-call productivity and token usage efficiency (50% skill_efficiency + 50% token_efficiency). <br>

Underlying evaluation signals used in this run: <br>
- `security`: Unsafe operations, secret leakage, and unauthorized access. <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `skill_execution`: Whether the expected skill was selected, decoys avoided, and workflow executed. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `skill_efficiency`: Tool-call productivity (routing scored under Discoverability). <br>
- `token_efficiency`: Actual uncached prompt plus completion token usage. <br>



## Evaluation Results: <br>
| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | 83.8% — uplift unavailable | 85.5% — uplift unavailable |
| Security | 100.0% → 100.0% (±0.0 pts) | 100.0% → 100.0% (±0.0 pts) |
| Correctness | 100.0% → 100.0% (±0.0 pts) | 100.0% → 100.0% (±0.0 pts) |
| Discoverability | 35.0% — uplift unavailable | 85.0% — uplift unavailable |
| Effectiveness | 100.0% → 100.0% (±0.0 pts) | 100.0% → 58.3% (-41.7 pts) |
| Efficiency | 83.9% — uplift unavailable | 84.2% — uplift unavailable |

## Skill Version(s): <br>
1213167 (source: git SHA, committed 2026-10-01) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>

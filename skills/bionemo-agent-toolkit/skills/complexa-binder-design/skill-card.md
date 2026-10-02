## Description: <br>
Run a complete protein binder design campaign with NVIDIA Proteina-Complexa: resolve a target structure and hotspots, co-design binder sequence and structure with reward-guided test-time search, gate with AF2 reward, then independently validate each binder by refolding with Boltz2 and rank on interface confidence, pLDDT, ipSAE, apo/holo stability, and hotspot contact. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
Apache 2.0 <br>
## Use Case: <br>
Developers and computational biologists designing de novo protein binders against target proteins using Proteina-Complexa with independent structural validation via Boltz2 or OpenFold3. <br>

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
- [Proteina-Complexa Project Page](https://research.nvidia.com/labs/genair/proteina-complexa/) <br>
- [Proteina-Complexa Code (GitHub)](https://github.com/NVIDIA-Digital-Bio/Proteina-Complexa) <br>
- [Setup Guide](references/setup.md) <br>
- [Complexa CLI Reference](references/complexa-cli.md) <br>
- [Pipeline Reference](references/pipeline.md) <br>
- [Validation Reference](references/validation.md) <br>
- [Target and Hotspots Reference](references/target-and-hotspots.md) <br>


## Skill Output: <br>
**Output Type(s):** [Shell commands, Files, Analysis] <br>
**Output Format:** [Markdown reports with inline bash, PDB structure files, JSON manifests] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Ranked binders with GO/NO-GO verdict, per-design pass/failure flags, and reproducible manifest] <br>

## Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-5`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
Evaluated against 4 tasks (3 positive, 1 negative) from a pinned dataset (sha256:7c04169e). <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Whether the skill avoids unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Final-answer correctness against the reference answer. <br>
- Discoverability: Whether the expected skill was selected and the workflow executed. <br>
- Effectiveness: Whether the skill helped complete the user's goal and followed the expected workflow (goal_accuracy 50% + behavior_check 50%). <br>
- Efficiency: Tool-call productivity and token efficiency (skill_efficiency 50% + token_efficiency 50%). <br>

Underlying evaluation signals used in this run: <br>
- `security`: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- `skill_execution`: Whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- `skill_efficiency`: Tool-call productivity (routing scored under Discoverability). <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `token_efficiency`: Actual uncached prompt plus completion token usage. <br>



## Evaluation Results: <br>
| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | Not available | 56.9% — uplift unavailable |
| Security | Not available | 25.0% → 25.0% (±0.0 points) |
| Correctness | Not available | 80.0% → 80.0% (±0.0 points) |
| Discoverability | Not available | 76.7% — uplift unavailable |
| Effectiveness | Not available | 33.1% → 41.3% (+8.2 points) |
| Efficiency | Not available | 61.5% — uplift unavailable |

## Skill Version(s): <br>
1213167 (source: git SHA, committed 2026-10-01) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>

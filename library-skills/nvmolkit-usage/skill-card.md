## Description: <br>
Write code that calls the installed nvMolKit Python API for GPU-accelerated, batched RDKit-style operations — Morgan fingerprints, Tanimoto/cosine similarity, ETKDG conformer embedding, MMFF/UFF optimization, TFD, conformer RMSD, Butina clustering, substructure search, and maximum common substructure (MCS) search. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
Apache-2.0 <br>
## Use Case: <br>
Developers and computational chemists writing Python code that calls the nvMolKit API for GPU-accelerated, batched cheminformatics operations such as fingerprinting, similarity search, conformer generation, force-field optimization, clustering, substructure search, and MCS search. <br>

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
- [nvMolKit Documentation](https://nvidia-bionemo.github.io/nvMolKit/) <br>
- [nvMolKit Changelog](https://nvidia-bionemo.github.io/nvMolKit/changelog.html) <br>


## Skill Output: <br>
**Output Type(s):** [Code, Configuration instructions] <br>
**Output Format:** [Markdown with inline Python code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [None] <br>

## Evaluation Agents Used: <br>
- Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`) <br>
- Codex (`openai/openai/gpt-5.5`) <br>



## Evaluation Tasks: <br>
12 evaluation tasks (12 positive), each run in an isolated sandbox pod. Dataset digest: sha256:16ead845d201c386f3f059697aff38c0e6978ce5e90370c6548d7bade427c6fb. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Security: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- Correctness: Checks final-answer correctness against the reference answer. <br>
- Discoverability: Checks whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- Effectiveness: Equal-weight mean of goal completion (goal_accuracy) and expected workflow adherence (behavior_check). <br>
- Efficiency: 50% tool-call productivity (skill_efficiency) and 50% token efficiency. <br>

Underlying evaluation signals used in this run: <br>
- `security`: Checks for unsafe operations, secret leakage, and unauthorized access. <br>
- `skill_execution`: Whether the expected skill was selected, decoys were avoided, and the workflow executed. <br>
- `skill_efficiency`: Tool-call productivity (routing scored under Discoverability, not Efficiency). <br>
- `accuracy`: Final-answer correctness against the reference answer. <br>
- `goal_accuracy`: Whether the user's goal was achieved. <br>
- `behavior_check`: Whether the expected workflow behavior was followed. <br>
- `token_efficiency`: Actual uncached prompt plus completion token usage. <br>



## Evaluation Results: <br>
| Measure | Claude Code (Baseline → Skill Uplift) | Codex (Baseline → Skill Uplift) |
|---|---:|---:|
| Overall | 92.9% | 93.2% |
| Security | 79.2% → 100.0% (+20.8 points) | 100.0% → 100.0% (±0.0 points) |
| Correctness | 100.0% → 96.7% (-3.3 points) | 90.0% → 100.0% (+10.0 points) |
| Discoverability | 98.3% | 94.6% |
| Effectiveness | 90.9% → 86.5% (-4.4 points) | 74.8% → 91.6% (+16.8 points) |
| Efficiency | 82.9% | 79.7% |

## Skill Version(s): <br>
0.6.0 (source: pyproject.toml, CHANGELOG, released 2026-08-13) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail). <br>

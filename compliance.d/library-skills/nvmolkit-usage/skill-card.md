## Description: <br>
Guides an agent to write correct code against the installed nvMolKit Python API for GPU-accelerated, batched RDKit-style cheminformatics — Morgan fingerprints, Tanimoto/cosine similarity, ETKDG conformer embedding, MMFF/UFF optimization, TFD, conformer RMSD, Butina clustering, and substructure search. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (Kevin Boyd, @scal444) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
Cheminformaticians and ML engineers importing `nvmolkit.*`, debugging an nvMolKit call, deciding between nvMolKit and RDKit for a batched workflow, or wiring nvMolKit results into a torch/numpy pipeline. Out of scope: building nvMolKit from source. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* An existing nvMolKit installation (`uv pip install --torch-backend=cu128 nvmolkit`) <br>
* CUDA-capable NVIDIA GPU <br>
* Python with RDKit available for interoperation <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill emits code for the agent or user to execute; incorrect API usage could produce silently wrong cheminformatics results — for example mismatched fingerprint parameters yielding similarity scores that are not comparable across runs. <br>
Mitigation: The skill documents result types and the asynchronous execution model (`AsyncGpuResult`, `Device3DResult`) explicitly, and includes a verification step to run against the install before writing real code. Users should review generated code before executing it. <br>

Risk: nvMolKit and RDKit can differ numerically for the same nominal operation (conformer generation and force-field optimization are stochastic and hardware-sensitive), so results may not reproduce bit-for-bit across backends. <br>
Mitigation: The skill covers where nvMolKit is and is not an appropriate substitute for RDKit, so users choose the backend deliberately rather than assuming equivalence. <br>

Risk: Batched GPU operations on large molecule libraries can exhaust GPU memory mid-run. <br>
Mitigation: The skill documents `HardwareOptions` configuration for batch and device control. <br>

Risk: Asynchronous result handles can be read before completion if the execution model is misunderstood, yielding empty or partial data. <br>
Mitigation: The skill's result-type documentation is explicit about when a result must be awaited or materialized. <br>

## Reference(s): <br>
- [nvMolKit repository](https://github.com/NVIDIA-BioNeMo/nvMolKit) <br>
- [RDKit documentation](https://www.rdkit.org/docs/) — the API surface nvMolKit mirrors <br>
- `SKILL.md` in this skill directory — result types, `HardwareOptions` / `SubstructSearchConfig`, and worked recipes <br>

## Skill Output: <br>
**Output Type(s):** [Code, Analysis] <br>
**Output Format:** [Markdown with inline Python code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [The skill produces code and guidance; it does not itself execute cheminformatics workloads. Generated code should be reviewed before execution.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
11 functional evaluation tasks in `evals/evals.json` covering fingerprinting, similarity, conformer generation, optimization, clustering, and substructure search, plus 2 trigger-activation cases in `evals/trigger_evals.json`. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
ea68428 (source: git SHA, committed 2026-08-03) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

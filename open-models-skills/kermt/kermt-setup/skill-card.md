## Description: <br>
Bootstraps the KERMT agent environment — verifies host Docker and the NVIDIA Container Toolkit, builds the `kermt:latest` image from the repository Dockerfile if absent, and runs a GPU smoke test inside the container. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
Computational chemists and ML engineers preparing a workstation or GPU node to run any `kermt-*` skill. Every other KERMT skill depends on this one; it is the first skill to invoke on a fresh clone. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* Docker <br>
* NVIDIA Container Toolkit <br>
* CUDA-capable NVIDIA GPU <br>
* A local clone of the KERMT repository (supplies the Dockerfile) <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill builds a container image and runs GPU workloads, which consumes significant local disk and can take tens of minutes on a cold cache. <br>
Mitigation: The skill checks for an existing `kermt:latest` image and skips the build when one is present; the smoke test is short and read-only. <br>

Risk: Docker commands require elevated host privileges, and an agent running them has broad access to the host container runtime. <br>
Mitigation: The skill issues only build, run, and inspect commands against the KERMT image; users should keep their agent's command-approval gate enabled and review commands before execution. <br>

Risk: A partially configured host (driver/toolkit mismatch) can produce a container that starts but cannot see the GPU, causing confusing downstream failures in training skills. <br>
Mitigation: The GPU smoke test runs inside the container and fails loudly at setup time rather than deferring the error to a long-running job. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- [NVIDIA Container Toolkit documentation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/) <br>
- `agent/scripts/kermt_container.sh` — container entry points used by this skill <br>

## Skill Output: <br>
**Output Type(s):** [Analysis, Configuration instructions] <br>
**Output Format:** [Markdown status report with inline bash commands] <br>
**Output Parameters:** [1D — pass/fail status per environment check] <br>
**Other Properties Related to Output:** [Side effect: builds the `kermt:latest` Docker image on the host if it does not already exist] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
4 evaluation tasks defined in `evals/evals.json`, covering environment verification, image build, and GPU smoke test paths. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
b1c082c (source: git SHA, committed 2026-07-17) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

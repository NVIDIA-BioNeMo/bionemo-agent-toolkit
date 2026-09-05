## Description: <br>
Reports progress for a detached KERMT run by reading `run.json`, querying Docker for container state, tailing the pretrain/finetune log, and parsing progress lines (epoch, step, validation loss). <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
ML engineers running long KERMT pretraining or finetuning jobs who need to check status, spot divergence early, and decide whether to let a run continue or terminate it. This is the companion skill to every detached `kermt-*` training invocation. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* Docker <br>
* `jq` <br>
* A prior detached KERMT run that produced a `run.json` <br>

Note: unlike the training skills, this skill does not require a GPU. <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: A stale or missing `run.json` can cause the skill to report on the wrong run, or to report nothing while a job is in fact still consuming GPU-hours. <br>
Mitigation: The skill refuses to proceed when `run.json` is missing, and reports container identifiers so the user can verify the run directly. Because `run.json` does not record a container name, pass `--container <name-or-id>` when monitoring a specific run. <br>

Risk: Log tailing surfaces run output into the agent transcript, which may include file paths or environment details. <br>
Mitigation: The skill reads only the pretrain/finetune log; users should treat agent transcripts as sensitive and avoid pasting credentials into run configuration. <br>

Risk: This skill is read-only and cannot stop a runaway job, so a user may assume monitoring implies control. <br>
Mitigation: The skill reports container identifiers so the user can terminate the run directly via Docker if needed. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- `agent/scripts/kermt_container.sh` — defines `kermt_run_detached`, the wrapper whose runs this skill observes <br>
- Related skills: `kermt-pretrain-scratch`, `kermt-continue-pretrain`, `kermt-finetune` <br>

## Skill Output: <br>
**Output Type(s):** [Analysis] <br>
**Output Format:** [Markdown status report] <br>
**Output Parameters:** [1D — container state, current epoch, current step, latest validation loss] <br>
**Other Properties Related to Output:** [Read-only; the skill makes no changes to the run or the host] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
4 evaluation tasks defined in `evals/evals.json`, covering run discovery, container-state reporting, and log progress parsing. <br>

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

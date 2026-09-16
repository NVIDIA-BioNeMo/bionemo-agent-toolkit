## Description: <br>
Continues pretraining from an existing KERMT checkpoint — validating the checkpoint and corpus, preparing shard/vocab/feature artifacts, and launching `pretrain_ddp.py` inside the KERMT container with `--pretrain_mode` auto-dispatched from the checkpoint type. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
ML engineers adapting a KERMT foundation model to a domain-specific molecular corpus — for example an in-house compound collection — before task finetuning, without discarding the representations already learned. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: Optional <br>
Credential Type(s): API key — `WANDB_API_KEY` for optional Weights & Biases run tracking <br>

* `kermt-setup` completed (supplies the `kermt:latest` image) <br>
* Docker, NVIDIA Container Toolkit, CUDA-capable NVIDIA GPU (multi-GPU supported via DDP) <br>
* An existing KERMT checkpoint (grover_base vocab-only, cmim, or hybrid) <br>
* A pretraining corpus CSV <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Continued pretraining is a long-running, multi-GPU workload that a single agent instruction can start, potentially consuming days of GPU time and substantial cloud spend. <br>
Mitigation: Runs launch detached with a run manifest; `kermt-monitor` provides progress visibility and the container identifiers needed to terminate early. <br>

Risk: Selecting the wrong `--pretrain_mode` for a checkpoint would train against the wrong objective and silently waste the entire run. <br>
Mitigation: The skill auto-dispatches `--pretrain_mode` from the detected checkpoint type rather than relying on the user to specify it. <br>

Risk: Data preparation writes shard, vocabulary, and feature artifacts that can be large and can overwrite prior preparation output. <br>
Mitigation: Preparation writes under an explicit run/output path supplied by the user. <br>

Risk: Continued pretraining on a narrow corpus can degrade general-purpose representations (catastrophic forgetting) in ways not visible until downstream finetuning. <br>
Mitigation: The original checkpoint is not modified in place; users should retain it and compare downstream task performance before adopting the continued-pretrain checkpoint. <br>

Risk: When Weights & Biases tracking is enabled, run metadata is transmitted to a third-party service. <br>
Mitigation: W&B tracking is optional and off unless the user supplies `WANDB_API_KEY`. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- `agent/scripts/run_pretrain_local.py` — extended usage examples <br>
- Related skills: `kermt-setup`, `kermt-monitor`, `kermt-pretrain-scratch`, `kermt-add-cmim-pretrain`, `kermt-finetune` <br>

## Skill Output: <br>
**Output Type(s):** [Files, Analysis] <br>
**Output Format:** [Model checkpoint files; shard/vocab/feature artifacts; training logs; `run.json` manifest; Markdown launch summary] <br>
**Output Parameters:** [1D — run identifier, container id, resolved pretrain mode, output paths] <br>
**Other Properties Related to Output:** [Detached execution: the skill returns after launch, not after training completes.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
5 evaluation tasks defined in `evals/evals.json`, covering checkpoint validation, corpus validation, data preparation, pretrain-mode dispatch, and detached launch. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
b1c082c (source: git SHA, committed 2026-07-17) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Models produced by this skill inherit the composition and biases of the user's pretraining corpus. Downstream predictions are research hypotheses and must not be used as the sole basis for clinical, safety, or regulatory decisions. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

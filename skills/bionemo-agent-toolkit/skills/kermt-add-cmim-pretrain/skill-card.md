## Description: <br>
Converts a grover_base checkpoint into a hybrid checkpoint by adding a randomly-initialized cMIM decoder and latent distribution, then continues pretraining on the user's corpus in hybrid (vocab + contrast) mode. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
ML research engineers who want the cMIM contrastive objective on top of an existing grover_base KERMT checkpoint without retraining from scratch. Functionally `kermt-continue-pretrain` with a one-time checkpoint-conversion step prepended. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: Optional <br>
Credential Type(s): API key — `WANDB_API_KEY` for optional Weights & Biases run tracking <br>

* `kermt-setup` completed (supplies the `kermt:latest` image) <br>
* Docker, NVIDIA Container Toolkit, CUDA-capable NVIDIA GPU (multi-GPU supported via DDP) <br>
* A grover_base checkpoint (encoder-only, or encoder + vocab heads) <br>
* A pretraining corpus CSV <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The newly added cMIM decoder and latent distribution are randomly initialized, so the converted checkpoint performs worse than its source until sufficient hybrid pretraining has run — a checkpoint taken too early is silently degraded. <br>
Mitigation: The conversion step is explicitly separated from the training step, and `kermt-monitor` exposes validation loss so users can confirm convergence before adopting the result. <br>

Risk: Continued pretraining is a long-running, multi-GPU workload that a single agent instruction can start, potentially consuming days of GPU time. <br>
Mitigation: Runs launch detached with a run manifest; `kermt-monitor` provides progress visibility and the container identifiers needed to terminate early. <br>

Risk: Supplying a checkpoint that is not grover_base (e.g. already cmim or hybrid) would produce an invalid conversion. <br>
Mitigation: The skill validates the source checkpoint type before conversion. <br>

Risk: Conversion and data preparation write new checkpoint and shard/vocab/feature artifacts that can overwrite prior output. <br>
Mitigation: Artifacts are written under an explicit run/output path; the source checkpoint is not modified in place. <br>

Risk: When Weights & Biases tracking is enabled, run metadata is transmitted to a third-party service. <br>
Mitigation: W&B tracking is optional and off unless the user supplies `WANDB_API_KEY`. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- `agent/scripts/run_pretrain_local.py` — extended usage examples <br>
- Related skills: `kermt-setup`, `kermt-monitor`, `kermt-continue-pretrain`, `kermt-pretrain-scratch` <br>

## Skill Output: <br>
**Output Type(s):** [Files, Analysis] <br>
**Output Format:** [Converted hybrid checkpoint; subsequent training checkpoints; shard/vocab/feature artifacts; training logs; `run.json` manifest; Markdown launch summary] <br>
**Output Parameters:** [1D — run identifier, container id, converted checkpoint path, output paths] <br>
**Other Properties Related to Output:** [Detached execution: the skill returns after launch, not after training completes.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
4 evaluation tasks defined in `evals/evals.json`, covering source-checkpoint validation, cMIM conversion, corpus preparation, and detached launch. <br>

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

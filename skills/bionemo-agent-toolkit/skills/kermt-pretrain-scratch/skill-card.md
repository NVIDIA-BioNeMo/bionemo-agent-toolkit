## Description: <br>
Pretrains a fresh KERMT model from scratch on a user-provided corpus — building a new vocabulary, instantiating the model architecture from defaults, and launching `pretrain_ddp.py` inside the KERMT container with no starting checkpoint loaded. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
ML research engineers training a KERMT model from random initialization on a corpus sufficiently large and distinct that continued pretraining from an existing checkpoint is not appropriate. For most users, `kermt-continue-pretrain` is the better starting point. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: Optional <br>
Credential Type(s): API key — `WANDB_API_KEY` for optional Weights & Biases run tracking <br>

* `kermt-setup` completed (supplies the `kermt:latest` image) <br>
* Docker, NVIDIA Container Toolkit, CUDA-capable NVIDIA GPU (multi-GPU strongly recommended; DDP supported) <br>
* A large pretraining corpus CSV <br>
* Substantial disk for shard, vocabulary, and feature artifacts <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: This is the most expensive skill in the KERMT family — training from random initialization can consume days to weeks of multi-GPU time, and a single agent instruction can start it. <br>
Mitigation: Runs launch detached with a run manifest; `kermt-monitor` provides progress visibility and the container identifiers needed to terminate early. Users should confirm corpus scale justifies from-scratch training before invoking. <br>

Risk: Training from scratch on an insufficiently large corpus produces a model materially worse than the available pretrained checkpoints, with the cost discovered only after the run. <br>
Mitigation: The skill is documented as the exception path, with `kermt-continue-pretrain` as the recommended default; users should benchmark against an existing checkpoint before committing. <br>

Risk: A vocabulary built from the user's corpus is not interchangeable with vocabularies from other checkpoints, so resulting models are incompatible with checkpoints trained elsewhere. <br>
Mitigation: The new vocabulary is written alongside the checkpoint in the run directory, making the pairing explicit and auditable. <br>

Risk: Data preparation writes large shard/vocab/feature artifacts and can overwrite prior preparation output. <br>
Mitigation: Preparation writes under an explicit run/output path supplied by the user. <br>

Risk: When Weights & Biases tracking is enabled, run metadata is transmitted to a third-party service. <br>
Mitigation: W&B tracking is optional and off unless the user supplies `WANDB_API_KEY`. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- `agent/scripts/run_pretrain_local.py` — extended usage examples <br>
- Related skills: `kermt-setup`, `kermt-monitor`, `kermt-continue-pretrain`, `kermt-finetune` <br>

## Skill Output: <br>
**Output Type(s):** [Files, Analysis] <br>
**Output Format:** [Model checkpoint files; new vocabulary; shard/feature artifacts; training logs; `run.json` manifest; Markdown launch summary] <br>
**Output Parameters:** [1D — run identifier, container id, vocabulary path, model configuration, output paths] <br>
**Other Properties Related to Output:** [Detached execution: the skill returns after launch, not after training completes.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
4 evaluation tasks defined in `evals/evals.json`, covering corpus validation, vocabulary construction, architecture instantiation, and detached launch. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
b1c082c (source: git SHA, committed 2026-07-17) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Models produced by this skill inherit the composition and biases of the user's pretraining corpus entirely, with no counterbalancing from prior pretraining. Downstream predictions are research hypotheses and must not be used as the sole basis for clinical, safety, or regulatory decisions. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

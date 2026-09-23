## Description: <br>
Finetunes a pretrained KERMT encoder on a labeled CSV — validating the input checkpoint and dataset, preparing features and optional splits, then launching `main.py finetune` inside the KERMT container as a detached, hours-scale run. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
Computational chemists and ML engineers adapting a pretrained KERMT encoder (grover_base / cmim / hybrid) to their own labeled molecular property dataset — for example an in-house ADMET assay panel — before running predictions with `kermt-infer`. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: Optional <br>
Credential Type(s): API key — `WANDB_API_KEY` for optional Weights & Biases run tracking <br>

* `kermt-setup` completed (supplies the `kermt:latest` image) <br>
* Docker, NVIDIA Container Toolkit, CUDA-capable NVIDIA GPU <br>
* A pretrain checkpoint (grover_base, cmim, or hybrid) <br>
* A labeled CSV with SMILES and one or more target columns <br>
* Hyperparameters default from `agent/config/defaults_finetune.json`, overridable per flag <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Finetuning is an hours-scale GPU workload that a single agent instruction can start, consuming substantial GPU-hours or cloud spend. <br>
Mitigation: Runs launch detached with a run manifest, and `kermt-monitor` gives the user continuous visibility and the container identifiers needed to terminate early. <br>

Risk: Supplying a finetuned checkpoint instead of a pretrain checkpoint would produce an invalid training configuration. <br>
Mitigation: The skill validates the checkpoint type before launching and rejects non-pretrain checkpoints. <br>

Risk: A poorly split dataset (e.g. random splits on congeneric series) yields optimistic validation metrics that do not generalize. <br>
Mitigation: The skill exposes explicit split handling rather than defaulting silently; users remain responsible for choosing a split strategy appropriate to their chemistry. <br>

Risk: Training writes checkpoints and logs into a user-specified directory and can overwrite artifacts from a previous run. <br>
Mitigation: Outputs are written under an explicit run directory; users should use distinct output paths per experiment. <br>

Risk: When Weights & Biases tracking is enabled, run metadata is transmitted to a third-party service. <br>
Mitigation: W&B tracking is optional and off unless the user supplies `WANDB_API_KEY`; users should confirm their data-handling policy before enabling it. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- `agent/config/defaults_finetune.json` — default hyperparameters <br>
- Related skills: `kermt-setup`, `kermt-monitor`, `kermt-infer`, `kermt-embed` <br>

## Skill Output: <br>
**Output Type(s):** [Files, Analysis] <br>
**Output Format:** [Model checkpoint files; training logs; `run.json` manifest; Markdown launch summary] <br>
**Output Parameters:** [1D — run identifier, container id, configured hyperparameters, output paths] <br>
**Other Properties Related to Output:** [Detached execution: the skill returns after launch, not after training completes. Use `kermt-monitor` for progress.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
5 evaluation tasks defined in `evals/evals.json`, covering checkpoint validation, dataset validation, data preparation, and detached launch. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
b1c082c (source: git SHA, committed 2026-07-17) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Models finetuned with this skill inherit the biases and coverage limits of the user's training data. Resulting predictions are research hypotheses and must not be used as the sole basis for clinical, safety, or regulatory decisions. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

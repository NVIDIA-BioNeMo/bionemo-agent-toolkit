## Description: <br>
Runs molecular property predictions with a finetuned KERMT checkpoint on a SMILES-only CSV, validating that the checkpoint carries task FFN heads, preparing rdkit_2d features, and launching `main.py predict` inside the KERMT container. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
Computational chemists and drug-discovery teams scoring a library of candidate molecules for ADMET or other molecular properties using a KERMT model they have already finetuned. Not for use with pretrain checkpoints — the skill refuses those and redirects to `kermt-finetune`. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* `kermt-setup` completed (supplies the `kermt:latest` image) <br>
* Docker, NVIDIA Container Toolkit, CUDA-capable NVIDIA GPU <br>
* A finetuned KERMT checkpoint containing task FFN heads <br>
* A SMILES-only input CSV <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Predictions are computational estimates and may be applied outside the chemical space the model was finetuned on, producing confidently wrong property values for novel scaffolds. <br>
Mitigation: Users must treat outputs as hypotheses requiring experimental validation, and should check that input chemistry resembles the finetuning set before acting on predictions. <br>

Risk: Supplying a pretrain checkpoint instead of a finetuned one would yield meaningless outputs. <br>
Mitigation: The skill validates the checkpoint for task FFN heads before running and refuses pretrain checkpoints with an explicit redirect to `kermt-finetune`. <br>

Risk: Malformed or non-parseable SMILES silently reduce the effective prediction set. <br>
Mitigation: The skill runs a data-preparation and cleaning step that reports invalid rows before inference. <br>

Risk: The skill writes prediction outputs into a user-specified directory and can overwrite prior results. <br>
Mitigation: Outputs are written under an explicit output path supplied by the user; no files outside that path are modified. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- [RDKit documentation](https://www.rdkit.org/docs/) — `rdkit_2d` descriptor featurization <br>
- Related skills: `kermt-finetune` (produces the required checkpoint), `kermt-embed` <br>

## Skill Output: <br>
**Output Type(s):** [Analysis, Files] <br>
**Output Format:** [CSV of per-molecule predictions; Markdown summary] <br>
**Output Parameters:** [2D — one row per valid input molecule after cleaning and canonicalization, one column per predicted task] <br>
**Other Properties Related to Output:** [Predictions are model estimates, not measurements, and are not calibrated probabilities of experimental outcome. Runs blocking, on a minutes-scale timeframe.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
4 evaluation tasks defined in `evals/evals.json`, covering checkpoint validation, CSV validation, feature preparation, and the predict invocation. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
b1c082c (source: git SHA, committed 2026-07-17) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Molecular property predictions produced by this skill are computational hypotheses for research and development workflows. They must not be used as the sole basis for clinical, safety, or regulatory decisions. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

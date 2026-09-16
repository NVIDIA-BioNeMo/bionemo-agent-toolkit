## Description: <br>
Performs first-time setup for Proteina-Complexa — driving `complexa init`, `complexa download`, and `complexa validate env` end to end, editing required `.env` keys, selecting the UV or Docker runtime, and emitting a replayable setup artifact. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
This repository contains multiple components under different licenses; see the [`LICENSE`](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/blob/HEAD/LICENSE) in the source repository. <br>

## Use Case: <br>
Protein designers and computational biologists making a fresh Proteina-Complexa checkout runnable — verifying GPU preflight, configuring `.env`, and installing model weights (Complexa, AF2, RF3, ProteinMPNN, LigandMPNN, ESM2, ESMFold). This is the first skill to run on a new clone; every other `complexa-*` skill depends on it. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: Optional <br>
Credential Type(s): Credentials for model-weight sources, as required by the individual checkpoints being downloaded <br>

* `complexa` CLI installed (`pip install -e .`) <br>
* bash 4+ <br>
* `nvidia-smi` optional at setup time; a CUDA GPU is required for the design and evaluation skills <br>
* Substantial disk for model checkpoints <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill edits the user's `.env` file, which holds paths and may hold credentials; a mis-edit could break the environment or expose values in an agent transcript. <br>
Mitigation: The skill edits only the required keys and reports what changed; `.env` is git-ignored in this repository and must never be committed. Users should treat agent transcripts as sensitive. <br>

Risk: Model-weight downloads are large and fetch third-party checkpoints (AF2/ColabDesign, RF3, ESMFold, ProteinMPNN, LigandMPNN) whose licenses differ from this repository's. <br>
Mitigation: `complexa download --status` reports what is present before fetching; users are responsible for reviewing and complying with each checkpoint's upstream license terms. <br>

Risk: A partially completed setup produces confusing failures much later, inside long-running design jobs. <br>
Mitigation: `complexa validate env` runs as an explicit final step so environment problems surface at setup time. <br>

## Reference(s): <br>
- [Proteina-Complexa repository](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa) <br>
- Related skills: `complexa-target`, `complexa-design`, `complexa-evaluate-pdbs`, `complexa-sweep` <br>

## Skill Output: <br>
**Output Type(s):** [Analysis, Files, Configuration instructions] <br>
**Output Format:** [Markdown setup report; edited `.env`; downloaded checkpoint files; replayable setup artifact] <br>
**Output Parameters:** [1D — per-check pass/fail status, resolved runtime, installed model inventory] <br>
**Other Properties Related to Output:** [Side effects: writes `.env`, downloads model weights to disk] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
Not yet present on this branch. A co-located `evals/evals.json` with 4 tasks — covering init, weight download and status reporting, `.env` configuration, and environment validation — is introduced by [PR #57](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/pull/57) (branch `aggregator-compat`) and lands on `dev` when that merges. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
5391310 (source: git SHA, committed 2026-07-16) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

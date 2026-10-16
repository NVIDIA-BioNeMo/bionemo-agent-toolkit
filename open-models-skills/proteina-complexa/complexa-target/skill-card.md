## Description: <br>
Adds, registers, edits, lists, shows, and validates Proteina-Complexa design targets — protein binder, ligand binder, and AME / enzyme-scaffolding — and is the only skill that writes the three target dictionary files. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
This repository contains multiple components under different licenses; see the [`LICENSE`](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/blob/HEAD/LICENSE) in the source repository. <br>

## Use Case: <br>
Protein designers defining what to design against — registering a target structure, chain specification, hotspot residues, and binder length range before running `complexa-design`. Also covers `complexa validate target` and questions about chain-spec syntax and where hotspots live. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* `complexa` CLI installed (`pip install -e .`) <br>
* `complexa-setup` completed <br>
* A target structure (PDB/mmCIF) or SMILES for ligand-binder targets <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: This skill has exclusive write access to `configs/targets/{,ligand_}targets_dict.yaml` and `configs/design_tasks/ame_dict_v2.yaml`; a malformed edit could corrupt target definitions shared across a team's design runs. <br>
Mitigation: `complexa validate target` runs as an explicit validation path, and the skill is the single documented owner of those files so edits are not made ad hoc from multiple places. <br>

Risk: Incorrect hotspot residue numbering — a common failure when structure numbering differs from sequence numbering — silently redirects design to the wrong surface, wasting an entire downstream design campaign. <br>
Mitigation: The skill validates targets before use and supports structure-confirmed hotspot specification rather than accepting bare residue indices without checking. <br>

Risk: Target definitions may be derived from third-party structures (e.g. RCSB PDB entries) whose terms of use apply to downstream work. <br>
Mitigation: Users are responsible for confirming the provenance and licensing of any structure they register. <br>

## Reference(s): <br>
- [Proteina-Complexa repository](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa) <br>
- [RCSB Protein Data Bank](https://www.rcsb.org/) — common source of target structures <br>
- Related skills: `complexa-setup`, `complexa-design`, `complexa-sweep` <br>

## Skill Output: <br>
**Output Type(s):** [Files, Analysis] <br>
**Output Format:** [YAML target dictionary entries; Markdown summary of registered targets] <br>
**Output Parameters:** [1D — target identifier, chain spec, hotspot residues, binder length range] <br>
**Other Properties Related to Output:** [Side effect: writes to the repository's target dictionary configuration files] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
Not yet present on this branch. A co-located `evals/evals.json` with 4 tasks — covering target registration, listing/showing, chain and hotspot specification, and validation — is introduced by [PR #57](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/pull/57) (branch `aggregator-compat`) and lands on `dev` when that merges. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
5391310 (source: git SHA, committed 2026-07-16) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Target selection determines what a downstream design campaign is aimed at. Users are responsible for ensuring their design targets are consistent with applicable biosecurity norms and export-control obligations. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

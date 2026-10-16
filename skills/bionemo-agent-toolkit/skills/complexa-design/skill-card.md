## Description: <br>
Drives the end-to-end Proteina-Complexa design pipeline — `complexa design <pipeline>` from target selection through manifest emission — for protein binder, ligand binder, and AME / motif-scaffolding tasks, and reports how many designs passed. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
This repository contains multiple components under different licenses; see the [`LICENSE`](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/blob/HEAD/LICENSE) in the source repository. <br>

## Use Case: <br>
Protein designers and computational biologists running de novo binder design against a registered target — generating candidate binders with reward-guided flow matching, refolding them with an independent structure predictor (AF2 or RF3), and ranking by interface metrics (success rate, interface pAE, scRMSD, FoldSeek diversity). This is the scientific anchor of the `complexa-*` skill set. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* `complexa` CLI installed (`pip install -e .`) <br>
* `.env` populated (`complexa-setup`) and a target registered (`complexa-target`) <br>
* 1× CUDA GPU with ≥40 GB VRAM (A100 / H100 / L40S) <br>
* 24 CPUs, ~50 GB disk <br>
* Folding backend weights: AF2 (ColabDesign) or RF3 <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Designed binders are computational predictions. Reported success rates, interface pAE, and scRMSD are in-silico metrics that correlate imperfectly with experimental binding; treating them as validated hits wastes wet-lab resources. <br>
Mitigation: The pipeline refolds designs with a structure predictor independent of the generator and reports pass rates against explicit thresholds rather than a single score. All outputs require experimental validation. <br>

Risk: A full design campaign is a long, GPU-intensive workload that a single agent instruction can start, consuming substantial GPU-hours or cloud spend. <br>
Mitigation: The skill runs a pre-flight validation step before launching and emits a replayable manifest, so configuration errors surface before the expensive stage. <br>

Risk: Incorrect target or hotspot configuration directs the entire campaign at the wrong surface, with the error invisible until results are inspected. <br>
Mitigation: The skill validates the target as an explicit pipeline step and refuses to proceed on an invalid target. <br>

Risk: Generation is stochastic — repeated runs with identical inputs produce different binders unless a seed is fixed, which can confound comparisons between configurations. <br>
Mitigation: The emitted manifest records the run configuration for replay; use `complexa-sweep` for controlled comparisons across configurations. <br>

Risk: The skill writes design outputs and can overwrite results from a previous campaign in the same directory. <br>
Mitigation: Outputs are written under explicit per-run output paths. <br>

## Reference(s): <br>
- [Proteina-Complexa repository](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa) <br>
- La-Proteina — the flow-based generative model this work builds on <br>
- [ColabDesign / AlphaFold2](https://github.com/sokrypton/ColabDesign) and RF3 — independent refolding backends <br>
- [Foldseek](https://github.com/steineggerlab/foldseek) — structural diversity metric <br>
- Related skills: `complexa-setup`, `complexa-target`, `complexa-evaluate-pdbs`, `complexa-sweep` <br>

## Skill Output: <br>
**Output Type(s):** [Files, Analysis] <br>
**Output Format:** [PDB structures of designed binders; result CSV of per-design metrics; replayable JSON manifest; Markdown summary] <br>
**Output Parameters:** [3D for atomic coordinates; 2D for the per-design metric table; 1D for campaign-level pass rates] <br>
**Other Properties Related to Output:** [Outputs are computational predictions, not measurements. Confidence and interface metrics are model-reported and are not calibrated probabilities of experimental binding. Generation is stochastic unless seeded.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
Not yet present on this branch. A co-located `evals/evals.json` with 4 tasks — covering pipeline selection, pre-flight validation, design execution, and result collection with manifest emission — is introduced by [PR #57](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/pull/57) (branch `aggregator-compat`) and lands on `dev` when that merges. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
5391310 (source: git SHA, committed 2026-07-16) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

This skill generates novel protein sequences and structures. Users are responsible for screening designed sequences before synthesis, and for using the skill consistent with applicable biosecurity norms, biosafety review processes, and export-control obligations. Designed binders are research hypotheses and must not be used for clinical decision-making, diagnosis, or treatment selection. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

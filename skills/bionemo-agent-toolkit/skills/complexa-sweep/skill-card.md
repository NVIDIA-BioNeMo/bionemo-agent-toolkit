## Description: <br>
Runs parameter sweeps over a Proteina-Complexa design pipeline — authoring sweeper YAML, expanding cartesian-product configurations, and ranking per-configuration results for hyperparameter scans and Pareto search over generation, reward, and evaluation knobs. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
This repository contains multiple components under different licenses; see the [`LICENSE`](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/blob/HEAD/LICENSE) in the source repository. <br>

## Use Case: <br>
Protein designers and method developers tuning a design pipeline — scanning beam width, step count, temperature, or reward weights; ablating reward components; or trading binder quality against wall-clock. This is the only skill that owns sweeper YAML authoring and per-configuration result ranking. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* `complexa` CLI installed (`pip install -e .`) <br>
* `complexa-setup` completed and a target registered (`complexa-target`) <br>
* CUDA GPU meeting the `complexa-design` requirements, for each configuration in the sweep <br>
* Disk and GPU-hours proportional to the size of the cartesian product <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: This is the highest-cost skill in the family. A cartesian product expands multiplicatively, so a sweep specified in one short instruction can launch dozens of full design campaigns and consume very large amounts of GPU time or cloud spend. <br>
Mitigation: The skill expands and reports the configuration list before execution, so the user sees the run count before committing. Users should start with a small grid and confirm cost before widening. <br>

Risk: Ranking configurations on a stochastic pipeline can select a configuration that merely got a lucky seed rather than one that is genuinely better. <br>
Mitigation: Results are reported per configuration rather than as a single winner, so users can judge whether differences exceed run-to-run variance. Seeds should be fixed for like-for-like comparison. <br>

Risk: Sweeping on a small or unrepresentative target set overfits hyperparameters to that target, and the choice may not transfer. <br>
Mitigation: Per-configuration results are retained so users can re-examine the ranking against a held-out target. <br>

Risk: A large sweep writes many output directories and can exhaust disk mid-run, losing partially completed configurations. <br>
Mitigation: Outputs are written under explicit per-configuration paths; users should size storage against the expanded run count. <br>

## Reference(s): <br>
- [Proteina-Complexa repository](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa) <br>
- `reference/sweep_axes.md` in this skill directory — the sweepable parameter axes <br>
- `configs/sweeps/` — example sweep definitions <br>
- Related skills: `complexa-design`, `complexa-target`, `complexa-evaluate-pdbs` <br>

## Skill Output: <br>
**Output Type(s):** [Files, Analysis] <br>
**Output Format:** [Sweeper YAML; per-configuration design outputs and result CSVs; Markdown ranking table] <br>
**Output Parameters:** [2D — one row per configuration, columns for the swept parameters and resulting metrics] <br>
**Other Properties Related to Output:** [Rankings reflect in-silico metrics on a stochastic pipeline; differences within run-to-run variance should not be treated as meaningful.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
Not yet present on this branch. A co-located `evals/evals.json` with 4 tasks — covering sweeper YAML authoring, cartesian-product expansion, sweep execution, and per-configuration ranking — is introduced by [PR #57](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/pull/57) (branch `aggregator-compat`) and lands on `dev` when that merges. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
5391310 (source: git SHA, committed 2026-07-16) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Sweeps generate novel protein sequences and structures at scale. Users are responsible for screening designed sequences before synthesis, and for using the skill consistent with applicable biosecurity norms, biosafety review processes, and export-control obligations. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

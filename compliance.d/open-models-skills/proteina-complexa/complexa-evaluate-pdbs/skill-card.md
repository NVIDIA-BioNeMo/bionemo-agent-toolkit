## Description: <br>
Evaluates an existing directory of PDB files with Proteina-Complexa — selecting the correct `evaluate_*.yaml` config and folding backend, running the `complexa analysis` evaluate-then-analyze chain, parsing the result CSV, reporting pass rates against `result_type` thresholds, and emitting a replayable `eval_manifest.json`. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA <br>

### License/Terms of Use: <br>
This repository contains multiple components under different licenses; see the [`LICENSE`](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/blob/HEAD/LICENSE) in the source repository. <br>

## Use Case: <br>
Protein designers scoring binder candidates that already exist as structures — refolding designs, computing interface pAE, i_pLDDT, scRMSD, and motif RMSD, and assessing designability. Works on Proteina-Complexa output and equally on third-party outputs (BindCraft, AlphaProteo, RFdiffusion, hand-curated decoys), so it serves as a common yardstick across design methods. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* `complexa` CLI installed (`pip install -e .`) <br>
* CUDA GPU <br>
* A folding backend: `AF2_DIR` (ColabDesign) or `RF3_CKPT_PATH` + `RF3_EXEC_PATH` (rf3_latest) <br>
* ESMFold weights for monomer evaluation paths <br>
* A directory of input PDB files <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Pass rates are only meaningful relative to the thresholds of the selected `result_type`; comparing numbers produced under different configs or folding backends is misleading. <br>
Mitigation: The skill emits a replayable `eval_manifest.json` recording the config, backend, and thresholds used, so comparisons can be checked for like-for-like. <br>

Risk: Evaluating designs with the same model family that generated them inflates apparent quality. <br>
Mitigation: The skill supports independent folding backends (AF2/ColabDesign, RF3, ESMFold) and is documented for use as an independent check; users should choose a backend distinct from the generator. <br>

Risk: Refolding a large PDB directory is GPU-intensive and can run far longer than a user expects from a single instruction. <br>
Mitigation: The skill selects the appropriate config up front and reports the input set size before running. <br>

Risk: Malformed or non-standard PDB inputs — particularly third-party outputs with unusual chain or numbering conventions — can be silently skipped or misparsed. <br>
Mitigation: The skill parses the result CSV and reports counts, so a shortfall between inputs and scored designs is visible. <br>

## Reference(s): <br>
- [Proteina-Complexa repository](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa) <br>
- [ColabDesign / AlphaFold2](https://github.com/sokrypton/ColabDesign), RF3, and [ESMFold](https://github.com/facebookresearch/esm) — supported folding backends <br>
- Related skills: `complexa-setup`, `complexa-design`, `complexa-sweep` <br>

## Skill Output: <br>
**Output Type(s):** [Analysis, Files] <br>
**Output Format:** [Result CSV of per-design metrics; `eval_manifest.json`; Markdown pass-rate report] <br>
**Output Parameters:** [2D — one row per evaluated design, columns for interface pAE, i_pLDDT, scRMSD, motif RMSD; 1D for aggregate pass rates] <br>
**Other Properties Related to Output:** [Metrics are model-reported in-silico estimates, not measurements, and are not calibrated probabilities of experimental binding.] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
Not yet present on this branch. A co-located `evals/evals.json` with 4 tasks — covering config selection, backend wiring, evaluation execution, and pass-rate reporting with manifest emission — is introduced by [PR #57](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/pull/57) (branch `aggregator-compat`) and lands on `dev` when that merges. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
5391310 (source: git SHA, committed 2026-07-16) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Evaluation results are computational hypotheses. A high in-silico pass rate is not evidence of experimental binding, and must not be used for clinical decision-making, diagnosis, or treatment selection. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

## Description: <br>
Extracts per-molecule embeddings from any encoder-bearing KERMT checkpoint (grover_base / cmim / hybrid / finetuned), writing one `.npy` per readout type plus `canonical_smiles.npy` and `validity.npy`. <br>

This skill is ready for commercial/non-commercial use. <br>

## Owner
NVIDIA (evax@nvidia.com) <br>

### License/Terms of Use: <br>
Apache-2.0 <br>

## Use Case: <br>
ML engineers and cheminformaticians who need fixed-length molecular representations from a KERMT encoder to feed a downstream model, clustering step, or similarity search, without training a task head. <br>

### Requirements/Dependencies: <br>
Requires API Key or External Credential: No <br>
Credential Type(s): None <br>

* `kermt-setup` completed (supplies the `kermt:latest` image) <br>
* Docker, NVIDIA Container Toolkit, CUDA-capable NVIDIA GPU <br>
* Any encoder-bearing KERMT checkpoint <br>
* A SMILES input CSV (featurization happens on the fly — no precomputed features required) <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Embeddings from different checkpoints or readout types are not comparable, and mixing them in a downstream model produces silently meaningless results. <br>
Mitigation: The skill writes each readout type to a separately named `.npy` and emits `canonical_smiles.npy` alongside, so provenance and row alignment are explicit. <br>

Risk: Invalid SMILES rows would misalign embeddings against the caller's original input ordering. <br>
Mitigation: The skill emits `validity.npy`, letting the caller filter or realign rows deterministically. <br>

Risk: Large input libraries can produce embedding arrays of substantial size and consume significant disk. <br>
Mitigation: Outputs are written to a user-specified directory; users should size storage for the molecule count and embedding dimensionality before running. <br>

## Reference(s): <br>
- [KERMT repository](https://github.com/NVIDIA-BioNeMo/KERMT) <br>
- `task/extract_embeddings.py` — the underlying extraction entry point <br>
- Related skills: `kermt-setup`, `kermt-finetune`, `kermt-infer` <br>

## Skill Output: <br>
**Output Type(s):** [Files] <br>
**Output Format:** [NumPy `.npy` arrays — one per readout type (atom_from_atom, bond_from_atom, atom_from_bond, bond_from_bond), plus `canonical_smiles.npy` and `validity.npy`] <br>
**Output Parameters:** [2D — one row per input molecule, one column per embedding dimension] <br>
**Other Properties Related to Output:** [Row order corresponds to the input CSV; `validity.npy` identifies rows whose SMILES failed to parse] <br>

## Evaluation Agents Used: <br>
Target agents: `claude-code`, `codex`. NVSkills-Eval has not yet been run against this skill — see Evaluation Results. <br>

## Evaluation Tasks: <br>
5 evaluation tasks defined in `evals/evals.json`, covering checkpoint compatibility, readout selection, and output artifact production. <br>

## Evaluation Metrics Used: <br>
Planned NVSkills-Eval dimensions: Security, Correctness, Discoverability, Effectiveness, Efficiency. <br>

## Evaluation Results: <br>
Pending. NVSkills-Eval has not been run for this skill; results and a `BENCHMARK.md` will be published when the evaluation pipeline runs. <br>

## Skill Version(s): <br>
b1c082c (source: git SHA, committed 2026-07-17) <br>

## Ethical Considerations: <br>
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/). <br>

# Skill Card

## Description

`rfd4-proteina-search` runs reward-guided **beam search** for RFD4-Proteína (RFD4-Proteína): instead of sampling once, it explores multiple generation trajectories, scores candidates with a reward (by default an AF3 refolding oracle), and keeps the highest-scoring designs. It runs through the same `generate.py` entry point as generation, selected by a search `inference_experiment` config that adds one `search:` block (beam settings and a `checkpoints` mapping with explicit metrics and rewards).

This skill is for research and development only.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository. Skill text and documentation follow the NVIDIA agent-skills documentation convention (CC-BY-4.0); helper scripts follow the repository's source license.

## Use Case

Researchers who want the best designs per candidate — optimizing monomers or binders by refolding confidence (pLDDT / ipTM / ipAE), interface interactions, or another configured metric — and are willing to spend extra compute for it. Requires `rfd4-proteina-setup` complete and the selected reward dependencies. For cheap unguided sampling use `rfd4-proteina-generate`; for post-hoc scoring use `rfd4-proteina-evaluate`.

## Deployment Geography for Use

Global, subject to the repository license and export/compliance constraints on the model weights.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None (checkpoints download over public HTTPS; supported refolding backends use locally configured runtimes).

Hardware/software: Linux with an NVIDIA GPU (>=40 GB VRAM recommended); `rfd4-proteina-setup` complete; for refolding rewards, a configured AF2, AF3, or OpenFold3 backend that supports the selected providers and design case. High compute cost — many reward evaluations per run.

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate.

## Known Risks and Mitigations

Risk: Search is compute-intensive (many reward evaluations, roughly `beam_width x n_branch x checkpoints` per input) — it can consume large GPU budgets.
Mitigation: The skill documents the cost model and urges starting small (low `beam_width`/`n_branch`, few `search.checkpoints`, small `nsteps`) and using plain `rfd4-proteina-generate` for cheap baselines. See references/cost.md.

Risk: Invalid checkpoint steps or missing metric providers can fail a search run.
Mitigation: The skill requires positive steps no greater than the actual schedule length, with every provider listed explicitly. Zero is implicit and the schedule-end checkpoint is optional. Validate configuration before submission.

Risk: The reward optimizes a proxy (refolding confidence, interface metrics, or another configured score), not experimental success — high-reward designs are not guaranteed to work in the lab.
Mitigation: The skill frames reward as a proxy and advises experimental validation of any design.

## References

- `docs/workflow/search.md`, `docs/workflow/running.md` ("Search Strategies", "Evaluating Results")
- `configs/inference_experiment/inference_beam_example.yaml`, `configs/inference_experiment/sm_binder_hbond_search.yaml`
- `src/rfproteina/search/beam_search.py`, `src/rfproteina/metrics/oracles/pass_criterion_metric.py`, `src/rfproteina/metrics/oracles/oracle_metric.py`
- `scripts/launch_generate.sh`
- rfd4-proteina-setup skill (`https://github.com/RosettaCommons/RFD4-Proteina/blob/main/docs/installation.rst` for refolding backends)
- RFD4-Proteína website: https://rosettacommons.github.io/RFD4-Proteina/
- NVIDIA agent skills: https://docs.nvidia.com/skills

## Skill Output

Output type(s): files — annotated `.cif` designs (the final beam, plus any intermediate candidates retained by `save_rollouts` and optional `save_criteria`) and a `per_example_metrics.csv`.

Output format: CIF structures with per-atom annotations; CSV metrics table; outputs scored at checkpoints carry `search.reward`. Final designs finished without an end checkpoint receive ordinary metrics without a final search reward.

Output parameters: `out_dir/` (e.g. `outputs/beam_example/`), containing design CIFs and `per_example_metrics.csv`.

Other properties: search runs through `generate.py`; oracle results are cached during scoring and reused by the epoch-end metrics loop. Refolding rewards require the selected backend's runtime.

## Skill Version

0.1.0 (initial authoring, 2026-07).

## Ethical Considerations

RFD4-Proteína is a de novo protein/complex design model with dual-use potential. Reward-guided search actively optimizes designs toward an objective, which sharpens both benefit and misuse potential; use is governed by the repository's usage terms. Do not use to design hazardous biomolecules. Reward is a computational proxy — validate designs experimentally and follow applicable biosafety and export/compliance requirements.

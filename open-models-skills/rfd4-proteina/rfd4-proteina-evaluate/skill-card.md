# Skill Card

## Description

`rfd4-proteina-evaluate` computes post-hoc evaluation metrics on already-generated RFD4-Proteína structures via `rfd4-evaluate` (Hydra config `configs/evaluate.yaml`), then aggregates the per-job CSVs into `aggregated_metrics.csv` / `per_task_metrics.csv` with `rfproteina.inference_utils.aggregate_metrics`, optionally clustering designs structurally with FoldSeek.

This skill is for research and development only.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository. Skill text and documentation follow the NVIDIA agent-skills documentation convention (CC-BY-4.0); the underlying scripts follow the repository's source license.

## Use Case

Anyone who has generated RFD4-Proteína designs and needs to score them — designability (scRMSD/pLDDT/ipAE via AF3 refolding), design-quality checks (clash, bond length, SSE, motif RMSD), pass/fail criteria, structural-diversity clustering, or a bespoke custom metric — either inline during generation (see `rfd4-proteina-generate`) or offline over an existing folder of CIFs. Consumes the output of `rfd4-proteina-generate` / `rfd4-proteina-search`.

## Deployment Geography for Use

Global, subject to the repository license.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None. AF3 refolding runs inside a locally configured apptainer/docker container (no external API); FoldSeek clustering uses a local executable at `FOLDSEEK_EXEC`.

Depends on: a completed `rfd4-proteina-setup` (venv + `atomworks` + `DATA_PATH`). A GPU is required for refolding oracles and GPU metrics; plain design metrics are light. The AF3 container is required for any `*_refolding` metric or refolding oracle; `FOLDSEEK_EXEC` in `.env.local` is required for `--cluster_with_foldseek`.

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate.

## Known Risks and Mitigations

Risk: Refolding metrics and refolding oracles require the AF3 container; without it those metrics silently do not run (no oracle columns, no error), so a run can look "done" while measuring nothing about designability.
Mitigation: The skill flags the container requirement up front, documents which tags need it, and points to `launch_evaluate.sh` / `rfd4-proteina-setup` https://github.com/RosettaCommons/RFD4-Proteina/blob/main/docs/installation.rst for container setup.

Risk: Metrics are proxies for designability, not experimental validation. A design that passes scRMSD/pLDDT/ipAE thresholds is not guaranteed to fold, bind, or function in the lab.
Mitigation: The skill and card state this explicitly; pass criteria are labeled as thresholds on proxy metrics, not certifications.

Risk: FoldSeek diversity clustering needs `save_chain_of_interest=true` at generation time (and `FOLDSEEK_EXEC` set) or it has nothing to cluster.
Mitigation: The skill documents both prerequisites and the TM-score-0.5, chain-of-interest scoping; clustering is optional and additive (a missing `foldseek_cluster_id` column, not a crash).

## References

- `docs/workflow/metrics.md`, `docs/workflow/custom-metrics.md`, `docs/workflow/running.md` (Evaluating Results)
- `configs/evaluate.yaml`, `configs/metrics/all_metrics.yaml`
- `src/rfproteina/evaluate.py`, `src/rfproteina/inference_utils/aggregate_metrics.py`, `scripts/launch_evaluate.sh`
- NVIDIA agent skills: https://docs.nvidia.com/skills

## Skill Output

Output type(s): CSV metric tables (files on disk) plus console progress.

Output format: `per_example_metrics.csv` (one row per design), `aggregated_metrics.csv`, `per_task_metrics.csv`; individual job CSVs moved into `individual_job_results/`.

Output parameters: written under `out_dir/evaluation_metrics/`; metric columns prefixed by config key (e.g. `refolded_backbone_rmsd.rmsd`, `oracle.min_ipae_coi`, `unconditional.pass`); optional `foldseek_cluster_id` column.

Other properties: `evaluate.py` reads structures and writes only under `out_dir`; `aggregate_metrics` rewrites/moves CSVs within the metrics directory. Neither modifies model code or tracked configs.

## Skill Version

0.1.0 (initial authoring, 2026-07).

## Ethical Considerations

Evaluation of de novo protein/complex designs. The metrics score design quality and self-consistency; they do not certify safety, and passing them does not authorize any downstream wet-lab use. The same dual-use considerations as generation apply — do not use these metrics to select or promote designs intended as hazardous biomolecules. Metrics are computational proxies, not experimental validation.

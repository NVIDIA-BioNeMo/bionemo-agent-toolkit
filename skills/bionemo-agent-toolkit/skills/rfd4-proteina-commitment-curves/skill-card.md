# Skill Card

## Description

`rfd4-proteina-commitment-curves` measures **where along the flow-matching trajectory RFD4-Proteína decides a property**. It generates both phases' configs from one spec, runs phase 1 (make the parent designs, or score a curated set offline with `rfd4-evaluate`), sweeps `generation.args.partial_trajectory_fraction_steps` through `scripts/launch_sweep.sh` to partially re-diffuse each parent at a grid of restart steps, and plots the Spearman correlation between each child's metric and its own parent's. Alongside it, always and without configuration, it plots the two fidelity curves — sequence identity and CA RMSD to the parent structure — which give the scale the correlations are read on.

Between the two phases it also asks how *rare* each metric is: one histogram per metric over the phase-1 parents, cut by the thresholds in the run's pass-criteria config, with the observed pass rate per cut and — where too few designs passed for that to have resolution — a named extrapolation (a generalised-Pareto tail fit, or the best-AIC density fit) of how many designs one passer costs. That is a difficulty question the correlation curve cannot answer, and it is cheap enough to run before the sweep is paid for.

This skill is for research and development only.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository. Skill text and documentation follow the NVIDIA agent-skills documentation convention (CC-BY-4.0); the underlying scripts follow the repository's source license.

## Use Case

Anyone who wants to know how early a design property is fixed — "is the dock decided by step 25?", "can I screen on this metric at half the trajectory?", "is partial diffusion from step 60 worth running as a refinement?" — or how hard it is to hit at all: "what fraction of my designs pass this criterion?", "how many do I have to sample for one passer?". Consumes the output of `rfd4-proteina-generate` (or any curated set of designs) and reuses `rfd4-proteina-evaluate`'s metric set.

## Deployment Geography for Use

Global, subject to the repository license.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None. AF3 refolding, when a tracked metric needs it, runs inside a locally configured apptainer/docker container (no external API).

Depends on: a completed `rfd4-proteina-setup` (venv + `atomworks` + `DATA_PATH`); one CUDA GPU per sweep point; SLURM via `scripts/launch_generate.sh` / `scripts/launch_sweep.sh`. An AF3 container is required only if `metrics_tags` includes a `*_refolding` tag.

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate.

## Known Risks and Mitigations

Risk: Spearman across too few parents produces a smooth-looking curve that means nothing — 4 parents give a confidence interval near ±0.9.
Mitigation: The skill asks for the parent count up front and states the 40+ budget; phase 2 is pinned to one child per parent so replicates are spent on parents instead; the bootstrap resamples parents rather than rows.

Risk: A metric with a low reproducibility ceiling (stochastic relax, sampled oracle) never reaches ρ = 1 even when the child is structurally its parent, and can be misread as "the model never commits".
Mitigation: The skill and `references/method.md` require reading each curve against its own ceiling — the value at the highest restart step — and suggest pinning stochastic inputs.

Risk: A falling ρ has two indistinguishable causes — a metric sensitive to small changes in an otherwise unchanged design, and a model genuinely rebuilding a different protein — and reporting the wrong one inverts the conclusion.
Mitigation: Sequence identity and CA RMSD to the parent are computed and plotted on every run, with no flag to forget; `references/method.md` gives the four-way reading of ρ against them, and both are a hard clean-end control (100%, 0 Å) with no reproducibility ceiling to excuse a shortfall.

Risk: The sweep is expensive (one full generation per parent per grid point, plus metrics) and a misconfigured run wastes it silently — e.g. aggregation jobs that fail to submit on a GPU partition, or a time limit that kills the metric stage and leaves designs with no metrics that `skip_existing` will then skip.
Mitigation: `references/gotchas.md` documents `CPU_PARTITION` and the `skip_existing` interaction, and recommends piloting a coarse grid and confirming both controls before densifying.

Risk: The pass-rate extrapolations are models, not data. A tail estimate off a bimodal metric (refolding confidence metrics especially) can be wrong by orders of magnitude, and a number like "1 in 4,000" reads far more authoritative than it is.
Mitigation: The figure quotes an extrapolation only where fewer than 10 designs passed, always names the model it came from, marks a density fit that fails a KS test as *poor fit*, and prints the second estimate whenever the two disagree by more than 10x. `references/method.md` states what each assumes and its three limits; the CSV carries both estimates, the fit's KS p-value and the GPD's fitted shape so the choice can be re-examined.

Risk: The distribution figure defaults to the repository's pass-criteria config, which may not be the one the run scored against — plausible-looking cuts at the wrong thresholds.
Mitigation: `--pass_criteria` takes the config the run actually composed; `references/gotchas.md` calls out the git-ignored `configs/metrics/custom_metrics/` case specifically.

Risk: Metrics are computational proxies. A commitment point is a statement about a proxy's ranking, not about experimental behaviour.
Mitigation: Stated in the skill and here; `references/method.md` requires validating the scorer (spread, correct ranking of a known-good structure) before drawing conclusions.

## References

- `docs/workflow/running.md` (partial diffusion), `configs/generation/inference_base.yaml`
- `src/rfproteina/search/vanilla.py` (`resolve_partial_t`, `build_partial_schedule`), `src/rfproteina/flow_matching/product_space_flow_matcher.py` (`partial_simulation`)
- `scripts/launch_sweep.sh`, `src/script_utils/sweep.py`, `src/script_utils/concatenate_sweep_results.py`
- `src/rfproteina/evaluate.py`, `src/rfproteina/inference_utils/aggregate_metrics.py`
- Sibling skills: `rfd4-proteina-generate`, `rfd4-proteina-evaluate`
- NVIDIA agent skills: https://docs.nvidia.com/skills

## Skill Output

Output type(s): Hydra config files, CSV metric tables, and PNG figures (files on disk).

Output format: `configs/inference_experiment/<name>_phase1.yaml`, `configs/inference_experiment/<name>_sweep.yaml`, `configs/sweeps/<name>.yaml`; `sweep_per_example_metrics.csv` (one row per child, carrying `task` as the parent key and `generation.args.partial_trajectory_fraction_steps` as the restart step); `analysis/commitment_curve.csv` (one row per metric x restart step, with bootstrap CIs) and `analysis/commitment_curve{,_dark}.png`; `analysis/fidelity_curve.csv` (one row per fidelity series x restart step) and `analysis/fidelity_curve{,_dark}.png`; `analysis/metric_distributions.csv` (one row per metric x pass-criteria cut, with observed rate and Wilson interval, both extrapolated rates and their fitted parameters) and `analysis/metric_distributions{,_dark}.png`.

Output parameters: run outputs under `<out_root>/<name>_phase1` and `<out_root>/<name>_sweep`; parent symlinks under the spec's `parents_dir`; the distribution figure under `<out_root>/<name>_phase1/analysis` and the curve figures under `<out_root>/<name>_sweep/analysis`.

Other properties: `make_configs.py` writes into the repository's `configs/` tree — review before committing. `commitment_curve.py` and `metric_distributions.py` read CSVs (and, for the latter, a pass-criteria YAML) and write only under their `--out_dir`.

## Skill Version

0.3.0 (2026-08) — add the phase-1 metric-distribution analysis: per-metric histograms cut by the pass criteria, with observed and extrapolated pass rates. 0.2.0 (2026-08) — always plot sequence identity and CA RMSD to the parent alongside the ρ curves. 0.1.0 (initial authoring, 2026-08).

## Ethical Considerations

Analysis of de novo protein/complex design trajectories. The curve characterises when a model fixes a property; it does not certify that any design is safe, functional, or suitable for use. The same dual-use considerations as generation apply — do not use it to accelerate selection of designs intended as hazardous biomolecules. Commitment points are properties of computational proxies, not experimental validation.

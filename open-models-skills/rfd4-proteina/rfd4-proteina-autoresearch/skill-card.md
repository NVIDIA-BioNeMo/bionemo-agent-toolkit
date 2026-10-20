# Skill Card

## Description

`rfd4-proteina-autoresearch` orchestrates an iterative, inspectable RFD4-Proteína design campaign — a design -> score -> iterate loop over multiple waves that composes `rfd4-proteina-annotated-cif`, `rfd4-proteina-generate`, `rfd4-proteina-search`, and `rfd4-proteina-evaluate`, with explicit composite-reward engineering and freeze/promote/allocate branch rules.

This skill is for research and development only.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository. Skill text follows the NVIDIA agent-skills documentation convention (CC-BY-4.0). The autoresearch methodology is adapted from muni's public write-ups (see References) and Karpathy's autoresearch framing.

## Use Case

Researchers running a multi-round optimization campaign (e.g. binder or enzyme design) who want a reproducible loop: define a reward, sweep RFD4-Proteína's knobs, prune/promote branches, and keep the whole trajectory on disk. It adds no model capability; it is a strategy layer over the other RFD4-Proteína skills.

## Deployment Geography for Use

Global, subject to the repository license.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None. Reward-guided waves require the AF3 oracle container (configured via cluster env files, see `rfd4-proteina-search`); FoldSeek diversity requires `FOLDSEEK_EXEC`.

Depends on: `rfd4-proteina-setup`, `rfd4-proteina-annotated-cif`, `rfd4-proteina-generate`, `rfd4-proteina-search`, `rfd4-proteina-evaluate`. Multi-GPU or SLURM strongly recommended for real campaigns.

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate.

## Known Risks and Mitigations

Risk: The reward optimizes a proxy (AF3 confidence / interface metrics), not experimental success; a campaign can converge on designs that score well but do not work in the lab.
Mitigation: The skill frames the reward as a replaceable hypothesis, recommends diversity tracking, and states that downstream experimental validation is required.

Risk: Refolding-guided campaigns are compute-intensive and can consume large GPU budgets.
Mitigation: The skill documents the cost model and the explore/exploit allocation, and points at `rfd4-proteina-search` cost guidance; stop conditions are explicit.

Risk: Transplanting external (Proteina-Complexa / TREM2) hyperparameters as if they were RFD4-Proteína defaults, or assuming search algorithms RFD4-Proteína lacks (MCTS/best-of-n).
Mitigation: The skill labels all muni numbers as illustrative and restricts the sweep axes to RFD4-Proteína's real knobs (beam search only).

## References

- muni: Do Agents Discover Scoring-Function-Dependent Strategies? https://muni.bio/research/scoring-function-dependent-strategies
- muni: Autoresearch and muni CLI. https://www.muni.bio/research/muni-makeover-cli-autoresearch
- Didi, K., Zhang, Z., Zhou, G., Reidenbach, D., Cao, Z., Cha, S., Geffner, T., Dallago, C., Tang, J., Bronstein, M. M., Steinegger, M., Kucukbenli, E., Vahdat, A., & Kreis, K. Scaling Atomistic Protein Binder Design with Generative Pretraining and Test-Time Compute. ICLR 2026.
- `docs/workflow/search.md`, `docs/workflow/running.md`, `docs/workflow/metrics.md`
- Sibling skills: rfd4-proteina-annotated-cif, rfd4-proteina-search, rfd4-proteina-evaluate, rfd4-proteina-generate

## Skill Output

Output type(s): a replayable campaign directory (objective/rules, per-wave branch payloads, decisions, results) plus the per-branch design CIFs and metrics CSVs produced by the underlying skills.

Output format: Markdown/JSON/TSV campaign records; annotated CIFs and CSVs from the composed skills.

Output parameters: `campaign/program.md`, `campaign/wave{N}.json`, `campaign/decisions.md`, `campaign/results.tsv`, plus per-branch run outputs.

Other properties: this skill writes campaign bookkeeping and invokes the other skills; it does not modify model code.

## Skill Version

0.1.0 (initial authoring, 2026-07).

## Ethical Considerations

Automated, reward-driven de novo design amplifies both throughput and dual-use risk. Do not run campaigns aimed at hazardous biomolecules. Keep the loop inspectable (record decisions and rewards) so choices are auditable, and treat computational scores as proxies pending experimental validation.

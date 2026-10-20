# Skill Card

## Description

`rfd4-proteina-generate` drives single-shot generation for RFD4-Proteína
(RFD4-Proteína) across every design task — unconditional monomers and complexes,
folding / inverse folding, motif scaffolding, enzyme design, small-molecule
binders, protein binders, and DNA binders. It preflights the environment,
routes the request to the correct benchmark example and Hydra overrides, runs
`rfd4-generate`, and hands off to sibling skills for input
construction (`rfd4-proteina-annotated-cif`), reward-guided search (`rfd4-proteina-search`),
and oracle metrics (`rfd4-proteina-evaluate`).

This skill is for research and development only.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository. Skill text and documentation follow the NVIDIA
agent-skills documentation convention (CC-BY-4.0); helper scripts follow the
repository's source license.

## Use Case

Researchers running RFD4-Proteína to generate protein designs after
`rfd4-proteina-setup` is complete. Covers the full design-task matrix via one entry
point plus per-task references; the scientific anchor of the RFD4-Proteína skill
set.

## Deployment Geography for Use

Global, subject to the repository license and export/compliance constraints on
the model weights.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None (runs locally against downloaded checkpoints).

Hardware/software: `rfd4-proteina-setup` complete (uv/Python-3.12 venv, `atomworks`
package, checkpoints in `$DATA_PATH`, green preflight); 1x CUDA GPU for
generation. An apptainer/docker container is required only for `*_refolding`
metrics tags (AF3 oracle) — plain generation needs none.

Do not include secrets in prompts/logs/output; use least-privilege credentials;
rotate keys as appropriate.

## Known Risks and Mitigations

Risk: Generates unvalidated de novo designs; sequence/structure quality is not
guaranteed and outputs can be non-functional or misleading.
Mitigation: Treat all output as hypotheses; wet-lab and/or oracle (AF3 refolding)
validation is required before any downstream use.

Risk: Default `batch_size` (1) and `num_replicates` (1) are rarely right — the
former can OOM on large inputs when raised naively, the latter wastes a run by
producing a single design.
Mitigation: The skill documents starting at `batch_size=8` after confirming the
longest input fits at 1, and setting `num_replicates` to a real count; a
troubleshooting row covers OOM.

Risk: A user-supplied checkpoint override or stale local checkpoint can fail a
run, or silently run a different model than intended.
Mitigation: Preflight reports the release pair selected by `configs/inference.yaml`
and which `.ckpt` files exist; one-off overrides are explicit.

Risk: Passing `--key value` instead of Hydra `key=value` fails confusingly.
Mitigation: Stated prominently and in the troubleshooting table.

## References

- `docs/workflow/running.md`, `docs/workflow/running.md`, `configs/inference.yaml`
- `docs/examples.rst` and `open-models-skills/rfd4-proteina/rfd4-proteina-generate/references/tasks/`
- Example inputs: `data/benchmarks/`
- Sibling skills: `rfd4-proteina-setup`, `rfd4-proteina-annotated-cif`, `rfd4-proteina-search`, `rfd4-proteina-evaluate`
- RFD4-Proteína website: https://rosettacommons.github.io/RFD4-Proteina/
- NVIDIA agent skills: https://docs.nvidia.com/skills

## Skill Output

Output type(s): generated design files (+ optional inline metrics).

Output format: one annotated CIF per design under `out_dir`, with per-atom
provenance columns (`SA_SRC`, `SA_CRDSRC`, `SA_IDXGRPSRC`, `SA_UII`); optional
`per_example_metrics.csv` when `metrics_tags` is set.

Output parameters: `out_dir` (design CIFs), `per_example_metrics.csv`, optional
per-design chain-of-interest CIFs (with `save_chain_of_interest=true`).

Other properties: generation is compute-heavy (GPU); refolding metrics require an
AF3 container. The skill itself writes only under `out_dir` and does not modify
model code under `src/`.

## Skill Version

0.1.0 (initial authoring, 2026-07).

## Ethical Considerations

RFD4-Proteína is a de novo protein/complex design model with dual-use potential.
This skill actively generates designs, so it is the primary point where dual-use
risk is realized. Do not use it to design hazardous biomolecules (e.g. toxins,
pathogen-enhancing sequences); comply with the repository's usage terms and
applicable biosecurity regulations. Generated designs are unvalidated hypotheses
and must be reviewed and experimentally validated before any real-world use.

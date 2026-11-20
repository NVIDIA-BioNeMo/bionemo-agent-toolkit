# Skill Card

## Description

`rfd4-proteina-setup` prepares a Linux + NVIDIA-GPU host to run RFD4-Proteína by installing its Python environment and dependencies, resolving data/cache paths, downloading the configured model weights, and running preflight and a generation smoke test. Studio requests use the plugin's pinned runtime setup command; standalone requests use the selected upstream revision's installer.

This skill is for research and development only.

## Owner

RFD4-Proteína maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteína repository. Skill text and documentation follow the NVIDIA agent-skills documentation convention (CC-BY-4.0); helper scripts follow the repository's source license.

## Use Case

Anyone standing up RFD4-Proteína on a new machine or cluster before generating, evaluating, or searching. Run this first; it is a prerequisite for `rfd4-proteina-generate`, `rfd4-proteina-search`, and `rfd4-proteina-evaluate`.

## Deployment Geography for Use

Global, subject to the repository license and export/compliance constraints on the model weights.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None for public source and model downloads over HTTPS. Studio execution on a user-chosen host uses that user's existing SSH access.

Hardware/software: Linux with an NVIDIA GPU compatible with the selected model revision, `git`, Python 3.12, and storage for dependencies, model weights, caches and outputs. Studio's pinned profile requires Linux x86_64, Python 3.12.10, a compatible CUDA 13 driver and a GPU with at least 75 GiB; setup verifies these requirements. Optional refolding/search dependencies are separate.

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate.

## Known Risks and Mitigations

Risk: Download and generation can use different model revisions or caches.
Mitigation: Read `hf_ckpt_path` and `hf_ckpt_revision` from `configs/inference.yaml` and keep the Hub cache consistent. Standalone preflight checks that configured bundle, or the legacy pair only when bundle loading is disabled. Studio setup verifies its pinned local bundle and revision receipt with SHA-256 hashes.

Risk: Running the model before its environment and AtomWorks are installed produces confusing import errors.
Mitigation: Preflight checks imports through the configured runtime and exits non-zero before any run.

Risk: Confusing the skill catalog with the model checkout can cause failed
installation attempts or destructive workspace cleanup.
Mitigation: Resolve the model source and installed skill separately, preserve
existing files and Git metadata, and clone only into an unused destination.
Preflight accepts native model environments without requiring a dispatcher.

## References

- `docs/workflow/running.md`, `docs/workflow/inputs.md`
- `setup.sh`, `scripts/download_assets.sh`, `configs/inference.yaml`
- RFD4-Proteína website: https://rosettacommons.github.io/RFD4-Proteina/
- NVIDIA agent skills: https://docs.nvidia.com/skills

## Skill Output

Output type(s): environment changes + files (venv, downloaded checkpoints, env file), and a preflight report.

Output format: console PASS/FAIL report; created files on disk.

Output parameters: `.venv/`, the configured local bundle or Hub cache, ancillary `DATA_PATH`, and preserved environment settings. Legacy native weights use `$DATA_PATH/{flow_checkpoints,ae_checkpoints}/`. Studio uses `runtime-root/model`, `runtime-root/model-bundle`, and a separate smoke-output directory.

Other properties: `preflight.sh` checks the selected checkout without replacing
or deleting its files, and exits non-zero on failed checks. `setup.sh` and the
download step modify the model environment and data directory according to that
revision's installer. Successful installation still requires the GPU smoke test.

## Skill Version

0.1.0 (initial authoring, 2026-07).

## Ethical Considerations

RFD4-Proteína is a de novo protein/complex design model with dual-use potential. Setup does not itself design anything, but it enables generation; downstream use is governed by the design-task skills' ethical notes and the repository's usage terms. Do not use to design hazardous biomolecules.

# Skill Card

## Description

`rfd4-proteina-setup` prepares a Linux + NVIDIA-GPU host to run RFD4-Proteina (RFD4-Proteina) by installing the uv/Python-3.12 environment and AtomWorks dependency, wiring `DATA_PATH` and optional runtime settings, downloading the model checkpoints, and running a GPU/checkpoint preflight.

This skill is for research and development only.

## Owner

RFD4-Proteina maintainers — Baker Lab x NVIDIA GenAI collaboration.

## License/Terms of Use

See the RFD4-Proteina repository. Skill text and documentation follow the NVIDIA agent-skills documentation convention (CC-BY-4.0); helper scripts follow the repository's source license.

## Use Case

Anyone standing up RFD4-Proteina on a new machine or cluster before generating, evaluating, or searching. Run this first; it is a prerequisite for `rfd4-proteina-generate`, `rfd4-proteina-search`, and `rfd4-proteina-evaluate`.

## Deployment Geography for Use

Global, subject to the repository license and export/compliance constraints on the model weights.

### Requirements / Dependencies

Requires API Key or External Credential: No

Credential Type(s): None (checkpoints download over public HTTPS; no credentials).

Hardware/software: Linux with an NVIDIA GPU (>=40 GB VRAM recommended), `git`, `curl`, Python 3.12, ~10 GB disk for checkpoints. Optional apptainer/docker for AF3-backed refolding metrics and reward-guided search.

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate.

## Known Risks and Mitigations

Risk: Inference and the download script can drift to different checkpoint releases.
Mitigation: Keep the downloader aligned with `configs/inference.yaml`; preflight reports which `.ckpt` files are actually present, and `ckpt_path=`/`ckpt_name=` override either.

Risk: Running the model before its environment and AtomWorks are installed produces confusing import errors.
Mitigation: Preflight checks imports through the configured runtime and exits non-zero before any run.

Risk: Private setup can edit the user's shell rc file.
Mitigation: Private setup appends a marked block only when absent and offers an "other / set manually" choice. Public setup does not edit shell startup files.

## References

- `docs/how-to/run-the-model.md`, `docs/how-to/input_prep/index.md`
- `setup.sh`, `scripts/download_assets.sh`, `configs/inference.yaml`
- RFD4-Proteina website: https://rosettacommons.github.io/RFD4-Proteina/
- NVIDIA agent skills: https://docs.nvidia.com/skills

## Skill Output

Output type(s): environment changes + files (venv, downloaded checkpoints, env file), and a preflight report.

Output format: console PASS/FAIL report; created files on disk.

Output parameters: `.venv/`, `$DATA_PATH/{flow_checkpoints,ae_checkpoints}/`, `.env.local` or the selected cluster profile.

Other properties: `preflight.sh` is read-only (no writes); exits non-zero on any failed check. `setup.sh` and the download step modify the filesystem. Only private setup may modify the shell rc.

## Skill Version

0.1.0 (initial authoring, 2026-07).

## Ethical Considerations

RFD4-Proteina is a de novo protein/complex design model with dual-use potential. Setup does not itself design anything, but it enables generation; downstream use is governed by the design-task skills' ethical notes and the repository's usage terms. Do not use to design hazardous biomolecules.

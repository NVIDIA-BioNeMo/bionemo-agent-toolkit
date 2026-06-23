# Proteina-Complexa Skills

Six project-local Claude Code skills covering setup, target configuration, design, evaluation, sweeps, and SLURM submission. Each skill picks the cheapest tool for its job — the `complexa` CLI where it adds real value (pipeline orchestration, weight downloads, Hydra-defaults validation), and direct file edits / Python module calls where the CLI would just be a thin wrapper.

## The three design pipelines

Complexa runs one of three pipelines. **Protein binder is the default**; the other two are extensions for ligand pockets and enzyme scaffolding. Pick the pipeline by picking the `configs/search_*_pipeline.yaml` file — each one pins its own model checkpoint, autoencoder, targets dict, reward, and refold backend, so switching pipelines is "swap the config + change the target name".

| Pipeline (intent) | Config YAML | Model ckpt | Targets dict | Task-name pattern | Download flag |
|---|---|---|---|---|---|
| **Protein binder (default)** | `configs/search_binder_local_pipeline.yaml` | `complexa.ckpt` + `complexa_ae.ckpt` | `configs/targets/targets_dict.yaml` | `02_PDL1`, `22_DerF21`, … | `--complexa --all` |
| Ligand binder (small-molecule pocket) | `configs/search_ligand_binder_local_pipeline.yaml` | `complexa_ligand.ckpt` + `complexa_ligand_ae.ckpt` | `configs/targets/ligand_targets_dict.yaml` | `39_7V11_LIGAND`, `41_7BKC_LIGAND`, … | `--complexa-ligand --all` |
| AME (motif + ligand, enzyme scaffolding) | `configs/search_ame_local_pipeline.yaml` | `complexa_ame.ckpt` + `complexa_ame_ae.ckpt` | `configs/design_tasks/ame_dict_v2.yaml` | `M0024_1nzy`, `M0096_1chm`, … | `--complexa-ame --all` |

**If the user doesn't specify a pipeline, default to protein binder.** Switch to one of the others only when the request explicitly names a ligand pocket / SMILES / enzyme / `M####_<pdb>` task. See [`complexa-design/SKILL.md`](./complexa-design/SKILL.md) Step 2 for the full "what changes when you switch pipeline" cheat sheet and [`complexa-design/reference/pipelines.md`](./complexa-design/reference/pipelines.md) for the deep dive (reward weights, success thresholds, LoRA, `USE_V2_COMPLEXA_ARCH`).

## Skills

Each skill picks the cheapest tool for the job — sometimes the `complexa` CLI,
sometimes a direct file edit or Python module call. The "primary tool" column
is the default the skill recommends; the alternatives are still documented
inside each `SKILL.md` for cases where they fit better.

| Skill | Primary tool | CLI / alternative paths | When to use it |
|---|---|---|---|
| [`complexa-setup`](./complexa-setup/) | **CLI** (`complexa init` for `.env`, `complexa download` for weights) + **file-edit** of machine-specific `.env` paths | Use `complexa init` (not a bare `cp .env_example .env`) — it is the supported entry point. `preflight.sh` is the real readiness check; `complexa validate env` is only a shallow `.env`+`DATA_PATH`-exists smoke test | Fresh checkout, verifying an existing install, configuring `.env` |
| [`complexa-target`](./complexa-target/) | **File-edit** of `configs/targets/{,ligand_}targets_dict.yaml` | `complexa target add/list/show` (CLI is a thin YAML-append wrapper that does **not** validate inputs); `complexa target show`/`rg` is the authoritative existence check; `complexa validate target CONFIG --target NAME` adds a PDB-path check (needs a real config) | Registering a new protein or ligand design target |
| [`complexa-design`](./complexa-design/) | **CLI** (`complexa design <pipeline>` orchestrates 4 stages with logging) | Direct `python -m proteinfoundation.{generate,filter,evaluate,analyze}` for single-stage debug | Protein binder, ligand binder, AME motif + ligand scaffolding |
| [`complexa-evaluate-pdbs`](./complexa-evaluate-pdbs/) | **CLI** (`complexa analysis <eval_cfg>` chains evaluate→analyze) | Direct `python -m proteinfoundation.{evaluate,analyze}` for debugging | Re-folding / scoring an existing PDB directory with AF2 / RF3 / ESMFold |
| [`complexa-sweep`](./complexa-sweep/) | **Python script** (`script_utils/generate_inference_configs.py`) + SLURM launcher | No CLI — `complexa design` does not accept `--sweeper` | Finding optimal beam_width, nsteps, reward weights, etc. |
| [`complexa-slurm`](./complexa-slurm/) | **Bash launchers** (`slurm_utils/launch_*.sh`) | No CLI; always preview with `--dry-run` first | Submitting jobs to a remote SLURM cluster |

## Shared infrastructure

| File | Purpose |
|---|---|
| [`_shared/scripts/preflight.sh`](./_shared/scripts/preflight.sh) | One-shot system probe (GPU, VRAM, disk, checkpoints, tools, `.env`). Outputs `preflight.json`. |
| [`_shared/scripts/write_manifest.py`](./_shared/scripts/write_manifest.py) | Emits a pinned, replayable `run_manifest.json` per pipeline run. |
| [`_shared/reference/hardware.md`](./_shared/reference/hardware.md) | Per-pipeline hardware requirements. |

The skills require `complexa` (this repo's CLI), `bash`, and optionally `nvidia-smi`. `complexa-slurm` additionally requires `ssh`/`rsync` on the local box and a configured `.env` Section 5.

## How the skills were built and validated

Each skill went through the [`skill-creator`](https://github.com/anthropics/skills/tree/main/skill-creator) workflow:

1. **Draft** — `SKILL.md` (≤300 lines) + progressive-disclosure `reference/*.md`. Authoring traced to source files (`cli_runner.py`, `target_cli.py`, `configs/**`, `slurm_utils/**`).
2. **Test prompts** — 2 realistic per skill (12 total). Saved in `evals/<skill>/evals.json`.
3. **Parallel eval** — for each prompt, ran a with-skill agent (sees the SKILL.md) vs a baseline (general Claude, repo grep-only). Both produce a planned `complexa …` invocation; no GPU runs.
4. **Grade** — 6–10 objective assertions per prompt (uses correct flag? cites real override key? runs preflight? refuses unsafe shortcuts?).
5. **Aggregate** — `benchmark.json` per skill: with-skill vs baseline pass-rate, wall-clock, tokens.
6. **Iterate** — fixed 2 targeted regressions in iteration-2 (build_uv_env step, AME L:0 rename inline).

Per-skill workspaces (`<skill>-workspace/iteration-N/`) are git-ignored; the SKILL.md content + evals.json are committed.

## Headline numbers

- With-skill avg pass-rate: **95.3%** vs baseline **73.5%** (Δ **+21.8 pts**).
- Token cost: with-skill **24.5% cheaper** per task.
- Wall-clock: with-skill **71.5 s/task** vs baseline **143.9 s/task**.
- With-skill **strictly above baseline on every skill** (+6.2 to +40.3 pts).

## Adding a new skill

Follow the same loop:

```bash
# 1. Draft SKILL.md and reference/ files
# 2. Write evals/<new-skill>/evals.json
# 3. Run iteration-1: spawn with-skill + baseline subagents per prompt
# 4. Grade, aggregate, render eval viewer
# 5. Iterate on regressions
# 6. (optional) python -m scripts.run_loop --skill-path <new-skill> for trigger-description tuning
```

The flagship reference is [`complexa-design`](./complexa-design/) — its SKILL.md anchors on a real scientific task (full pipeline → success rate + diversity) and shows the progressive-disclosure pattern at its widest (3 reference files).

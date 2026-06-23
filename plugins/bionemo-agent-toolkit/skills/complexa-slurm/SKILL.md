---
name: complexa-slurm
description: >
  Launch Proteina-Complexa pipelines on a remote SLURM cluster — binder search,
  LaProteina monomer design, or multi-node distributed training. Reach for this
  skill whenever the user says "launch on SLURM", "submit to the cluster",
  "submit binder search to SLURM", "kick off training on the cluster",
  "multi-node training", "cluster job", "sbatch", "remote GPU run", "complexa
  slurm", "launch_protein_binder_search.sh", "launch_laproteina_train.sh",
  "launch_laproteina_design_pipeline.sh", "launch on grizzly / polar",
  "--on-cluster", "run distributed training", "sweep on SLURM", "run all
  targets on the cluster", "kick off a multi-target binder search", "rsync to
  cluster", "submit a singleton requeue chain", or whenever a Hydra config /
  sweep needs to escape a single workstation. This skill drives the launcher
  scripts under `slurm_utils/`, **always previews with `--dry-run` first**, then
  submits, captures SLURM job IDs, and emits a replayable manifest. SLURM
  submission costs cluster time and is hard to reverse, so the dry-run gate is
  non-optional.
compatibility: "complexa CLI installed; bash 4+; .env Section 5 populated; SSH key to CLUSTER_HOST"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Complexa SLURM Skill

Drive `slurm_utils/launch_protein_binder_search.sh`,
`slurm_utils/launch_laproteina_design_pipeline.sh`,
`slurm_utils/launch_monomer_eval_from_pdb_dir.sh`, and
`slurm_utils/launch_laproteina_train.sh` to submit Proteina-Complexa jobs to a
remote SLURM cluster. Probe the local + cluster environment first, gather the
right flags, **always preview with `--dry-run` and surface the resolved sbatch
to the user before submission**, then submit, capture the job IDs, and emit
`slurm_manifest.json` for replay.

> **No `complexa` CLI involvement.** SLURM submission is bash-script-only —
> there is no `complexa slurm` subcommand. The launchers source `.env`, rsync
> the repo, generate sbatch scripts, and call `sbatch` over SSH. Don't try to
> replace them with `ssh ... sbatch <<EOF`; you'll lose rsync gating, sweeper
> expansion, and the `--dry-run` safety net.

## What this skill enables

- Launch the four-stage **binder search** pipeline (generate → filter →
  evaluate → analyze) on cluster GPUs, single-target or via `--targets-file`.
  Drives all three Complexa design pipelines — protein binder (default),
  ligand binder, AME / enzyme scaffolding — by passing the matching
  `configs/search_*_pipeline.yaml` to the launcher.
- Launch **LaProteina monomer design** (`launch_laproteina_design_pipeline.sh`,
  default config `design_monomer_pipeline.yaml`) for unconditional protein
  generation.
- Launch multi-node **distributed training** sized from YAML
  (`nnodes_`, `ngpus_per_node_`, `ncpus_per_task_train_`, `run_name`).
- Choose between **Docker (Pyxis/Enroot)** and **UV venv** runtimes
  per-submission via `--runtime`.
- Orchestrate **Hydra sweeps** (`--sweeper`) and per-config overrides
  (`--override`) across the cluster.
- Stay **safe by default** — every submission is gated behind a dry-run
  preview the user must approve.
- Auto-download results via rsync (skippable with `--skip-download`).

## Step 1: Cluster preflight

The local preflight (`_shared/scripts/preflight.sh`) covers GPU / ckpts / tools
on the **local** host. SLURM submission additionally needs cluster
reachability, an `sbatch` binary, and a live partition. Run **both** preflights.

```bash
bash .claude/skills/_shared/scripts/preflight.sh           # local
bash .claude/skills/complexa-slurm/scripts/cluster_preflight.sh   # cluster
```

`cluster_preflight.sh` writes `cluster_preflight.json` and checks:

1. `.env` Section 5 (`CLUSTER_USER`, `CLUSTER_HOST`, `CLUSTER_ACCOUNT`,
   `CLUSTER_PARTITION`, `CLUSTER_ROOT_REMOTE`, `CLUSTER_DATA_PATH`,
   `CLUSTER_RUNTIME`) is populated. Runtime-specific:
   `CLUSTER_CONTAINER_IMAGE` (docker) or `CLUSTER_UV_VENV` + `CLUSTER_CACHE_DIR`
   (uv).
2. `ssh -o BatchMode=yes -o ConnectTimeout=5 $CLUSTER_USER@$CLUSTER_HOST true`
   succeeds (passwordless SSH must already be set up).
3. The login node has `sbatch` on `$PATH`.
4. `sinfo -p $CLUSTER_PARTITION -h` returns at least one node.
5. `CLUSTER_CKPT_PATH` and `CLUSTER_SHARED_MODELS_PATH` (if set) exist on the
   cluster.
6. Local repo git SHA (for the manifest).

**Do not proceed** to Step 2 if any required check fails — fix `.env`, SSH, or
permissions first. See `reference/cluster_env.md` for what each var means.

## Step 2: Pick the workload

| Intent | Launch script |
|--------|---------------|
| Complexa design pipeline (protein binder, ligand binder, AME) | `slurm_utils/launch_protein_binder_search.sh` (pass the matching `configs/search_*_pipeline.yaml`) |
| LaProteina unconditional monomer design | `slurm_utils/launch_laproteina_design_pipeline.sh` |
| Monomer evaluation from PDB dir | `slurm_utils/launch_monomer_eval_from_pdb_dir.sh` |
| Distributed training (fine-tune, RL, base training) | `slurm_utils/launch_laproteina_train.sh` |

Full flag matrices in [reference/slurm_workloads.md](reference/slurm_workloads.md).

## Step 3: Gather params via AskUserQuestion

Ask only what's missing from context. Suggested order:

1. **Workload** — binder search / LaProteina monomer design / training.
2. **Target / task** (binder) — e.g. `22_DerF21`, `02_PDL1`, `39_7V11_LIGAND`,
   or `M0096_1chm`; or `--targets-file` path for batch mode.
3. **Config YAML path** (training) — defaults to
   `configs/training_local_latents.yaml`; ask if the user has a different one.
4. **Runtime override** — leave to `.env` default, or force `docker` / `uv`?
5. **Sweep** — pass a `--sweeper FILE`? (binder only)
6. **Targets file** — `--targets-file FILE` and `--num-runs N`? (binder only)
7. **Already on cluster?** — pass `--on-cluster` if the user is sitting on the
   login node (skips SSH/rsync). Binder script only.
8. **Keep results remote?** — pass `--skip-download` to leave outputs on the
   cluster. Default is to rsync them back.

## Step 4: ALWAYS dry-run first

Build the command and run it with `--dry-run`. Show the user the full output —
specifically the generated **sbatch script body**, the **Hydra overrides**, the
rsync target, and the resource block (`--nodes`, `--gres=gpu`, `--time`,
`--partition`). Get an explicit yes/no before submitting.

```bash
./slurm_utils/launch_protein_binder_search.sh --dry-run 22_DerF21
./slurm_utils/launch_laproteina_design_pipeline.sh --dry-run
./slurm_utils/launch_laproteina_train.sh --dry-run --config configs/training_local_latents.yaml
```

The dry-run logs "DRY RUN MODE — No changes will be made" and "Would create
slurm_batch_script_*.sh with content: …". Surface that block verbatim.

**Why this gate is non-negotiable:** every real submission allocates an account
quota, schedules potentially many node-hours, may evict another user's job,
and creates a run directory on `$CLUSTER_ROOT_REMOTE` that the script refuses
to overwrite. A pre-submission read is the cheapest way to catch wrong
partitions, wrong run names, or a typo in a Hydra override.

## Step 5: Submit

Re-run the same command without `--dry-run`. The launch scripts source `.env`,
rsync code under a `.rsync_lock/`, write `slurm_batch_script_*.sh` to the run
directory on the cluster, and call `sbatch` via SSH.

```bash
./slurm_utils/launch_protein_binder_search.sh 22_DerF21
./slurm_utils/launch_laproteina_design_pipeline.sh
./slurm_utils/launch_laproteina_train.sh --config configs/training_local_latents.yaml
```

Watch stdout for `Submitted batch job <ID>` (the helper logs
`Submitted <stage> [i/N] with Job ID: <ID>`). Training is submitted with
`--dependency=singleton` repeated `--num-jobs` times (default 5) — record all
IDs. Binder search and LaProteina design pipelines submit stages sequentially
and `wait_for_job` between stages, so the caller blocks until the next stage's
IDs are available.

## Step 6: Monitor

Take **one** snapshot at submission time and surface it to the user. Do not
poll — re-invocation of this skill is cheap.

```bash
ssh "$CLUSTER_USER@$CLUSTER_HOST" "squeue -j <id1>,<id2>,... -u $CLUSTER_USER"
```

Log locations on the cluster (under the run directory
`$CLUSTER_ROOT_REMOTE/<run_name>/`):

| Script | Stage | Log path |
|--------|-------|----------|
| binder search | generation | `slurm_run_outputs/inf/slurm_<jobid>_<array>.{out,err}` |
| binder search | filter | `slurm_run_outputs/filter/slurm_<jobid>_<array>.{out,err}` |
| binder search | evaluation | `slurm_run_outputs/eval/slurm_<jobid>_<array>.{out,err}` |
| binder search | analyze | `slurm_run_outputs/agg/slurm_<jobid>_<array>.{out,err}` |
| LaProteina design pipeline | gen/eval/agg | `slurm_run_outputs/{gen,eval,agg}/...` |
| training | all | `slurm_run_outputs/slurm_<jobid>.{out,err}` |

For follow-ups (job still running? failed?), have the user re-invoke this
skill, or `ssh $CLUSTER_HOST` and run `squeue -u $CLUSTER_USER` /
`sacct -j <id>` themselves.

## Step 7: Download results

When the user reports the job is done:

- Default (no flag): `launch_*.sh` auto-rsyncs results back when the pipeline
  finishes. Binder search downloads to
  `<run_name>-<YYYY_MM_DD_HH>/{inference,evaluation_results}` and aggregates
  via `script_utils/aggregate_successful_samples/aggregate_successful_samples.py`.
  LaProteina design pipeline downloads to
  `results_downloaded/<run_name>-<YYYY_MM_DD_HH>/`.
- `--skip-download` was passed: results stay at
  `$CLUSTER_ROOT_REMOTE/<run_name>/` on the cluster. Pull manually with
  `rsync -az $CLUSTER_USER@$CLUSTER_HOST:$CLUSTER_ROOT_REMOTE/<run_name>/ ./local_results/`.
- `--on-cluster` was passed: pipeline ran on the login node; results stay
  under the current working directory on the cluster.

Training does **not** auto-download — checkpoints live at
`$CLUSTER_ROOT_REMOTE/<run_name>/` (or `$CLUSTER_CKPT_PATH` if configured).

## Step 8: Emit `slurm_manifest.json`

Drop a single manifest into `./complexa_slurm/` so the user has one file with
everything needed for replay.

```json
{
  "timestamp": "2026-05-15T18:32:01Z",
  "workload": "binder_search",
  "launch_cmd": "./slurm_utils/launch_protein_binder_search.sh --runtime docker 22_DerF21",
  "cluster_host": "login.mycluster.example.com",
  "cluster_partition": "gpu,compute",
  "cluster_account": "my_slurm_account",
  "runtime": "docker",
  "run_name": "search_binder_pipeline-search-22_DerF21",
  "remote_run_dir": "/lustre/.../runs/search_binder_pipeline-search-22_DerF21",
  "sbatch_scripts": [
    "slurm_batch_script_gen.sh",
    "slurm_batch_script_filter.sh",
    "slurm_batch_script_eval.sh",
    "slurm_batch_script_analyze.sh"
  ],
  "slurm_job_ids": {"generation": "1234567", "filter": "...", "evaluation": "...", "analyze": "..."},
  "git_sha": "abc1234"
}
```

The launch scripts already write `.githash` into the remote run dir; mirror
that SHA into the local manifest.

## Hardware

| Workload | Per-job nodes | GPUs/node | CPUs/task | Walltime (default) | Notes |
|----------|---------------|-----------|-----------|--------------------|-------|
| Binder search (any stage) | 1 | 1 (`gpus-per-node 1`) | from `ncpus_` in pipeline YAML | 04:00:00 | Job array, one job per config |
| LaProteina design pipeline (any stage) | 1 | 1 | from `ncpus_` in pipeline YAML | 02:00:00 | Job array, one job per config |
| Training | from `nnodes_` (e.g. 12) | from `ngpus_per_node_` (e.g. 8) | from `ncpus_per_task_train_` | 04:00:00 | Singleton requeue chain (canonical: 12 × 8 = 96 H100 binder finetune) |

Defaults come from `generate_array_slurm_header` / `generate_train_slurm_header`
in `slurm_utils/slurm_helper.sh`. Full per-script breakdown in
[reference/slurm_workloads.md](reference/slurm_workloads.md).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ssh: connect: Permission denied (publickey)` | No passwordless SSH / wrong `CLUSTER_SSH_KEY` | `ssh-copy-id`, or set `CLUSTER_SSH_KEY=/abs/path/key` in `.env` |
| `Directory ... already exists on remote` | A prior run with the same `run_name` is on the cluster | `ssh $CLUSTER_HOST 'rm -rf $RUN_DIR'`, or change `run_name` in the YAML |
| `Container sqsh file not found on cluster` | `CLUSTER_CONTAINER_IMAGE` path wrong | Verify with `ssh $CLUSTER_HOST 'ls -lh <image>'`, or switch to a registry URL |
| `Missing required fields in <pipeline_config>` | `gen_njobs` / `eval_njobs` / `run_name` not in YAML | Re-derive from the canonical pipeline YAML; do not edit a downstream copy |
| `INVALID_QOS` / `account ... not allowed in partition` | `CLUSTER_ACCOUNT` lacks access to `CLUSTER_PARTITION` | Pick a partition the account is bound to; `ssh $CLUSTER_HOST 'sshare -A $CLUSTER_ACCOUNT'` |
| All array jobs `PENDING (Resources)` indefinitely | Partition oversubscribed or wrong reservation | Try a different partition; check `sinfo -p $CLUSTER_PARTITION` |

Long list (preemption, container pulls, missing checkpoints, rsync failures,
targets-file format, `--on-cluster` vs default) lives in
[reference/troubleshooting.md](reference/troubleshooting.md).

---

References:

- [reference/cluster_env.md](reference/cluster_env.md) — `.env` Section 5
  variables, defaults, what fails when each is missing.
- [reference/slurm_workloads.md](reference/slurm_workloads.md) — full flag
  matrix and sbatch shape per launch script, with copy-pasteable examples.
- [reference/troubleshooting.md](reference/troubleshooting.md) — common
  failure modes with diagnoses and fixes.

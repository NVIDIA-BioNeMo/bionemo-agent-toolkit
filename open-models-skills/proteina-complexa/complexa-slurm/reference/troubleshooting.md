# Troubleshooting — `complexa-slurm`

Symptom-first lookup. For each entry: what you see, why, the fix.

## SSH / authentication

### `ssh: connect to host ... port 22: Permission denied (publickey)`

- **Cause**: passwordless SSH not configured for the agent that runs the
  skill, or the wrong key is being offered.
- **Fix**:
  1. `ssh-copy-id $CLUSTER_USER@$CLUSTER_HOST` on a real terminal.
  2. Or set `CLUSTER_SSH_KEY=/abs/path/to/private_key` in `.env`. Make sure
     `chmod 600` on the key; OpenSSH refuses world-readable keys.
  3. If using `ssh-agent`, the launch script's subshell sees `$SSH_AUTH_SOCK`
     only if the calling shell exports it.

### `WARNING: UNPROTECTED PRIVATE KEY FILE!`

- **Cause**: `CLUSTER_SSH_KEY` has too-permissive mode.
- **Fix**: `chmod 600 $CLUSTER_SSH_KEY`.

### `BatchMode = yes; no passphrase` errors in preflight

- **Cause**: SSH key is passphrase-protected and no agent is running.
- **Fix**: `eval "$(ssh-agent -s)"; ssh-add $CLUSTER_SSH_KEY` before
  invoking the skill, **or** create a passphrase-less deploy key for
  scripted use.

### `Host key verification failed`

- **Cause**: `~/.ssh/known_hosts` has a stale entry for the cluster.
- **Fix**: `ssh-keygen -R $CLUSTER_HOST`, then SSH once manually so the new
  key is recorded. The preflight script uses `StrictHostKeyChecking=accept-new`
  so first-run prompts won't bite.

## SLURM scheduling

### Job stuck in `PD` / `PENDING (Resources)` for hours

- **Cause**: partition is oversubscribed or your account isn't bound to it.
- **Fix**:
  - `ssh $CLUSTER_HOST squeue -p $CLUSTER_PARTITION -u $CLUSTER_USER` to see
    queue depth.
  - Switch to a comma-list with fallback partitions: `CLUSTER_PARTITION=
    "polar3,polar4,grizzly"`.
  - `ssh $CLUSTER_HOST sshare -A $CLUSTER_ACCOUNT` to confirm fairshare.

### `error: Batch script ... requested ... nodes but only ... available`

- **Cause**: `nnodes_` in the training YAML exceeds the partition's node count.
- **Fix**: reduce `nnodes_` (or use a larger partition). Verify with
  `ssh $CLUSTER_HOST sinfo -p $CLUSTER_PARTITION -o "%P %D %c %G"`.

### `INVALID_QOS` / `Account ... not allowed in this partition`

- **Cause**: SLURM account isn't authorized on the chosen partition.
- **Fix**: pick a partition the account can use, or request access. Check via
  `sacctmgr show user $CLUSTER_USER`.

### Job preempted; what happens next?

- Training: `#SBATCH --requeue` + `SIGUSR1@600` + Lightning auto-requeue means
  the job receives a signal 10 min before preemption, checkpoints, and
  SLURM puts it back in the queue. The `--num-jobs N` chain has at most one
  active job at a time (singleton dependency), so preempted training resumes
  in the same chain slot.
- Binder / monomer arrays: each array task has `#SBATCH --requeue` too. Lost
  array tasks get requeued; downstream stages still block at
  `wait_for_job` until the whole array reaches a terminal state.

## Container / image

### `Container sqsh file not found on cluster`

- **Cause**: `CLUSTER_CONTAINER_IMAGE` points to a `.sqsh` path that doesn't
  exist on the cluster.
- **Fix**: `ssh $CLUSTER_HOST ls -lh <image>`; rebuild or transfer the sqsh.

### `pyxis: failed to pull container image`

- **Cause**: typo in registry URL, missing registry auth on cluster, or
  network restriction on compute nodes.
- **Fix**:
  1. Double-check `CLUSTER_CONTAINER_IMAGE`; it must match what's in your
     local `DOCKER_IMAGE` row of `.env`.
  2. Stash creds on the cluster via `enroot import` or registry login.
  3. Or convert to a `.sqsh` once on the login node and use that path.

### Inside the container: `ModuleNotFoundError: proteinfoundation`

- **Cause**: `PYTHONPATH` not pointing at `community_models` + `src` inside
  the container.
- **Fix**: confirm `slurm_helper.sh:build_container_exports` is emitting
  `PYTHONPATH=${ws}/community_models:${ws}/src:${ws}` (cluster shell view of
  the sbatch script). If you customized `CLUSTER_CONTAINER_WORKSPACE`, make
  sure your image is built with `.venv` at that workspace.

## Checkpoints / weights / model files

### Job fails: `FileNotFoundError: complexa.ckpt`

- **Cause**: local `ckpts/` wasn't rsynced (the blanket `*.ckpt` exclude rule
  fired), or `CLUSTER_CKPT_PATH` is set but the directory is empty/missing.
- **Fix**:
  - If `CLUSTER_CKPT_PATH` empty: rerun the launch; the rsync rule
    `--include='ckpts/**'` should beat the blanket exclude
    (`slurm_helper.sh:283`). Verify with `ssh $CLUSTER_HOST ls $RUN_DIR/ckpts`.
  - If `CLUSTER_CKPT_PATH` set: pre-populate that path manually.

### Job fails: missing ProteinMPNN / LigandMPNN `.pt` files

- **Cause**: binder search needs community model weights (`--include-community-weights`
  passes the override), but the local copy of `community_models/` lacks them.
- **Fix**: `complexa download --all` locally first; then the launcher's
  `validate_model_weights` (`slurm_helper.sh:773-796`) will pass.

### `CLUSTER_SHARED_MODELS_PATH` set but jobs still rsync big files

- **Cause**: the path is set but the directory doesn't exist yet — first
  invocation of `setup_shared_models` will copy `./community_models/` there.
  After the first successful run subsequent runs skip the rsync.
- **Fix**: let the first run complete, or pre-populate
  `$CLUSTER_SHARED_MODELS_PATH/community_models` manually.

## Filesystem / rsync

### `Directory ... already exists on remote. Delete or rename and try again.`

- **Cause**: `setup_remote_base` refuses to overwrite an existing run dir
  (`slurm_helper.sh:254-256`).
- **Fix**: `ssh $CLUSTER_HOST 'rm -rf $CLUSTER_ROOT_REMOTE/<run_name>'`, or
  bump `run_name` in the pipeline / training YAML, or pass a different
  `RUN_SUFFIX` / target / `--count`.

### `rsync: connection unexpectedly closed`

- **Cause**: network glitch, or rsync via login node hit a CPU/memory limit.
- **Fix**: set `CLUSTER_HOST_DC=<dc-node>` in `.env` to route rsync through
  the dedicated data-mover (`_rsync_code_to_remote` already prefers
  `CLUSTER_HOST_DC` when set, `slurm_helper.sh:296`).

### `.rsync_lock/` stuck after a crashed launch

- **Cause**: launch died mid-rsync; the mkdir-based lock didn't clean up.
- **Fix**: `acquire_lock` (`slurm_helper.sh:361-378`) reclaims locks whose
  owner PID no longer exists. For a manual force-clean: `rm -rf .rsync_lock`
  in the **local** repo root.

### `--skip-download` + rsync back fails

- **Cause**: pipeline finished but the auto-download rsync failed (auth,
  network, full local disk).
- **Fix**: rerun manually after fixing the underlying cause:
  ```bash
  rsync -az --progress \
    $CLUSTER_USER@$CLUSTER_HOST:$CLUSTER_ROOT_REMOTE/<run_name>/ \
    ./<run_name>-$(date +%Y_%m_%d_%H)/
  ```

## Logs and outputs

### Where is each stage's log?

Pipeline scripts write everything under `$CLUSTER_ROOT_REMOTE/<run_name>/slurm_run_outputs/`:

| Script | Stage | Path |
|--------|-------|------|
| binder | generation | `slurm_run_outputs/inf/slurm_<jobid>_<arr>.{out,err}` |
| binder | filter | `slurm_run_outputs/filter/slurm_<jobid>_<arr>.{out,err}` |
| binder | evaluation | `slurm_run_outputs/eval/slurm_<jobid>_<arr>.{out,err}` |
| binder | analyze | `slurm_run_outputs/agg/slurm_<jobid>_<arr>.{out,err}` |
| monomer | generation/eval/analyze | `slurm_run_outputs/{gen,eval,agg}/...` |
| training | all | `slurm_run_outputs/slurm_<jobid>.{out,err}` |

`<arr>` is the SLURM array index (`%a`). Tail with `ssh $CLUSTER_HOST tail
-f $RUN_DIR/slurm_run_outputs/inf/slurm_<jobid>_0.out`.

## Dry-run interpretation

### `Would create slurm_batch_script_train.sh with content:` followed by a script

- This is the **point** of `--dry-run`. Read the printed sbatch script —
  partition, node count, GPUs, time, and the `srun` line at the bottom.
  Confirm all of it matches your intent before re-running without `--dry-run`.

### Dry-run claims it generated configs but I see nothing under `configs/inference_configs/`

- `--dry-run` of binder search still runs the **local** config generator
  (writes into a tempdir) — but the staging + rsync are skipped, so the
  canonical paths under `./configs/inference_configs/` stay empty. This is
  expected. The tempdir under `configs/_gen_XXXXXX/` is cleaned up by the
  EXIT trap.

### Dry-run looks right but real run fails with a different sbatch

- Re-run dry-run from a clean checkout. If you've been editing `.env`
  mid-flight, the next real launch resources may have shifted.

## `--on-cluster` vs default SSH submission

- **Default** (no flag): the script runs **locally**, generates configs
  locally, rsyncs code to the cluster, then `ssh ... 'sbatch'` to submit.
  Lock file `.rsync_lock/` is acquired in the local repo. Best when you're
  working on a workstation.
- **`--on-cluster`**: the script runs **on the login node itself** (you `ssh`d
  in already), skips rsync, treats the current working directory as
  `$RUN_DIR`. Useful when iterating quickly on the cluster, or when local
  network egress is slow. Submitted via direct `sbatch` (no SSH hop).

If you see `bash: ssh: command not found` on cluster: you ran the default
flow from a login node where outbound SSH is restricted. Switch to
`--on-cluster`.

## Targets-file format

The `--targets-file FILE` flag (binder script only):

- One target per line. Examples: `22_DerF21`, `02_PDL1`.
- Blank lines: ignored.
- Lines starting with `#`: ignored (comments).
- Leading / trailing whitespace: stripped.

Parsed at `launch_protein_binder_search.sh:702-712`.

For each target the launcher does `--num-runs N` full pipeline runs and
appends to `failed_targets` on any failure; the loop continues to the end and
exits 1 if any failed.

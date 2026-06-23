# Section 5 — Cluster `.env` Reference

All `CLUSTER_*` variables are read **only** by `slurm_utils/*` launch scripts.
If you never run on the cluster you can leave them empty. `complexa init`
**does not** auto-write Section 5; you must edit `.env` by hand. Source:
`.env_example` lines 70–223, parsed by `slurm_utils/slurm_helper.sh`
(`load_config`, `require_cluster_vars`).

Throughout this doc:

- "**Required (all runtimes)**" = the launch script will `die` if missing.
- "**Required (docker)**" = required only when `CLUSTER_RUNTIME=docker`.
- "**Required (uv)**" = required only when `CLUSTER_RUNTIME=uv`.
- "**Optional**" = launch script handles a sensible default.

---

## Required (all runtimes)

### `CLUSTER_USER`
- **Type**: string (your cluster username).
- **Required**: yes, unless `--on-cluster` (binder script only).
- **Used by**: every `ssh`, `rsync`, `sbatch` invocation.
- **Pitfall**: an empty value makes SSH try to log in as the local user — a
  silent confusing failure. The preflight script catches this.

### `CLUSTER_HOST`
- **Type**: hostname / FQDN of a login node.
- **Required**: yes (unless `--on-cluster`).
- **Example**: `login.mycluster.example.com`.
- **Used by**: SSH submission, `wait_for_job`, results download.
- **Pitfall**: must be a login node where `sbatch` works. Compute nodes won't
  have `sbatch` on `$PATH`.

### `CLUSTER_ACCOUNT`
- **Type**: SLURM account string.
- **Required**: yes.
- **Example**: `my_slurm_account`.
- **Used by**: written into every sbatch header as `#SBATCH --account`.
- **Pitfall**: must be allowed on the chosen `CLUSTER_PARTITION`; mismatch
  produces `INVALID_QOS` or `Account ... not allowed in this partition`.

### `CLUSTER_PARTITION`
- **Type**: comma-separated SLURM partition list.
- **Required**: yes.
- **Example**: `"gpu,compute"`.
- **Used by**: written into the sbatch header as `#SBATCH --partition`.
- **Pitfall**: every partition listed must be reachable from your account, or
  jobs sit in `PENDING (Resources)` forever.

### `CLUSTER_ROOT_REMOTE`
- **Type**: absolute path on cluster filesystem.
- **Required**: yes.
- **Example**: `/path/to/cluster/runs`.
- **Used by**: every launch script — run dir is `$CLUSTER_ROOT_REMOTE/<run_name>`.
- **Pitfall**: must be on a filesystem visible from compute nodes (lustre,
  GPFS, NFS). Home directories may not be visible from all partitions.

### `CLUSTER_DATA_PATH`
- **Type**: absolute path on cluster filesystem.
- **Required**: yes.
- **Example**: `/path/to/cluster/data`.
- **Used by**: written into the per-run `.env` as `DATA_PATH`, mounted into
  Docker containers as `${CLUSTER_DATA_PATH}:${CLUSTER_DATA_PATH}`.
- **Pitfall**: training reads this path inside the container; misconfigured
  here means Hydra explodes on `${oc.env:DATA_PATH}`.

### `CLUSTER_RUNTIME`
- **Type**: `docker` or `uv`.
- **Required**: yes.
- **Used by**: branches every `_runtime_env_setup` / `validate_*_config`.
- **Pitfall**: must match the runtime you actually have on the cluster — a
  docker value with no Pyxis/Enroot installed will fail at `srun`.

---

## Required (docker)

### `CLUSTER_CONTAINER_IMAGE`
- **Type**: registry URL **or** absolute `.sqsh` path on cluster.
- **Required (docker)**: yes.
- **Example registry**: `<your-registry>/<your-image>:complexa-uv`.
- **Example sqsh**: `/lustre/.../images/complexa.sqsh`.
- **Used by**: `validate_docker_config`, `generate_docker_container_vars`.
- **Pitfall**: a registry URL behind an auth gate requires the cluster to have
  registry creds; a `.sqsh` file path must exist on the cluster (the
  preflight `validate_docker_config` checks this).

### `CLUSTER_CONTAINER_WORKSPACE`
- **Type**: absolute path inside the container.
- **Required (docker)**: yes (defaulted in `.env_example` to
  `/workspace/protein-foundation-models`; only edit if your image uses a
  different layout).
- **Used by**: every container mount and export — `PYTHONPATH`, `HOME`,
  `PROJECT_HOME`, Hydra config paths.
- **Pitfall**: must match the actual path inside the image where `.venv` is
  built. Changing this without rebuilding the image breaks `source
  /workspace/.venv/bin/activate`.

### `CLUSTER_DOCKER_MOUNTS` (optional)
- **Type**: comma-separated `host:container` pairs.
- **Required**: no.
- **Used by**: appended to the `--container-mounts` srun arg.
- **When to use**: when you need an extra lustre share or scratch dir visible
  inside the container.

---

## Required (uv)

### `CLUSTER_UV_VENV`
- **Type**: absolute path to a pre-built UV virtualenv on the cluster.
- **Required (uv)**: yes.
- **Example**: `/lustre/.../venvs/complexa-uv-py3.12`.
- **Used by**: every `generate_uv_env_setup` snippet — `source
  $CLUSTER_UV_VENV/bin/activate`.
- **Pitfall**: the venv must be built **on the cluster** (same glibc / CUDA
  / NCCL as compute nodes). Building locally and copying breaks dynamic libs.

### `CLUSTER_CACHE_DIR`
- **Type**: absolute path on cluster filesystem.
- **Required (uv)**: yes.
- **Used by**: written into per-run `.env` as `CACHE_DIR`; exported as
  `TORCH_HOME`, `BOLTZ_CACHE`. Also used by Docker runtime (optional there).
- **Pitfall**: must be writable by every job. Putting this under a per-user
  home that's not mounted on compute nodes silently fails.

---

## Optional

### `CLUSTER_HOST_DC`
- **Type**: hostname of a data-copier / data-mover node.
- **Default**: falls back to `CLUSTER_HOST`.
- **When to use**: ORD / OCI clusters have dedicated DC nodes with 100 Gbit/s
  links that rsync 5–10× faster than login nodes. Set this when uploading
  weights or `community_models/` for the first time.
- **Used by**: `_rsync_code_to_remote`, `setup_shared_models`. **Not** used by
  SSH submission (`sbatch` still goes via `CLUSTER_HOST`).

### `CLUSTER_SSH_KEY`
- **Type**: absolute path or `~/...` path to an SSH private key.
- **Default**: empty → SSH uses `ssh-agent` / default identity.
- **Used by**: `load_config` adds `-i <key> -o IdentitiesOnly=yes` to
  `SSH_OPTS`. If the file does not exist `load_config` will `die`.
- **Pitfall**: permissions must be `0600` or OpenSSH refuses it.

### `CLUSTER_SHARED_MODELS_PATH`
- **Type**: absolute path on cluster filesystem.
- **Default**: empty → `community_models/` is rsynced into every run
  directory (Python source only; weights excluded by blanket rules unless
  `--include-community-weights` is passed by `launch_protein_binder_search.sh`).
- **When to use**: when multiple users / runs on the same cluster share one
  `community_models/` (≈10 GB+ if you include weights). First call to
  `setup_shared_models` copies your local `./community_models/` there; later
  runs detect the directory exists and skip the copy. For Docker, the path is
  mounted into the container at `${CLUSTER_CONTAINER_WORKSPACE}/community_models`.
- **Pitfall**: make sure the path is readable by your SLURM job UID (group
  ACL on lustre often required).

### `CLUSTER_CKPT_PATH`
- **Type**: absolute path on cluster filesystem.
- **Default**: empty → local `ckpts/` is rsynced into every run directory
  (rsync override `--include='ckpts/**'` defeats the blanket `*.ckpt` rule).
- **When to use**: when you want one shared `ckpts/` (Complexa + AE pairs,
  ESM, AF2 weights) instead of one copy per run. Saves disk and rsync time.
  Docker mounts it at `${CLUSTER_CONTAINER_WORKSPACE}/checkpoints`; UV uses
  the host path directly.
- **Pitfall**: Hydra configs that interpolate `${oc.env:CKPT_PATH}` resolve to
  this path inside the container; sanity-check after first run.

---

## Worked example — typical OCI / ORD setup

```bash
# .env Section 5 — Docker runtime, shared models, dedicated DC node
CLUSTER_USER=<your-username>
CLUSTER_HOST="login.mycluster.example.com"
CLUSTER_HOST_DC="dc.mycluster.example.com"
CLUSTER_SSH_KEY=~/.ssh/id_ed25519_ord

CLUSTER_ACCOUNT="my_slurm_account"
CLUSTER_PARTITION="gpu,compute"
CLUSTER_RUNTIME=docker

CLUSTER_ROOT_REMOTE=/path/to/cluster/runs/${CLUSTER_USER}
CLUSTER_DATA_PATH=/path/to/cluster/data/PFM_data
CLUSTER_CACHE_DIR=/path/to/cluster/cache/${CLUSTER_USER}

CLUSTER_SHARED_MODELS_PATH=/path/to/cluster/shared/models
CLUSTER_CKPT_PATH=/path/to/cluster/shared/ckpts

CLUSTER_CONTAINER_IMAGE=${DOCKER_IMAGE}     # reuses Section 4 value
# CLUSTER_CONTAINER_WORKSPACE and CLUSTER_UV_* are auto-derived below the
# STOP block; leave them alone.
```

Same setup with the UV runtime instead:

```bash
CLUSTER_RUNTIME=uv
CLUSTER_UV_VENV=/path/to/cluster/venvs/complexa-uv-py3.12
# (CLUSTER_CACHE_DIR already required above — same value reused)
# CLUSTER_CONTAINER_IMAGE not needed for UV
```

---

## Interaction with `complexa init`

`complexa init` writes / rewrites Sections 1–4 and the auto-managed runtime
block at the bottom of `.env`. **It does not touch Section 5.** That means:

- On a fresh checkout, you must add cluster vars manually after running
  `complexa init`.
- Re-running `complexa init --force` will **not** wipe Section 5 — your
  cluster config survives.
- `complexa init` will **not** validate Section 5; only this skill's
  `cluster_preflight.sh` does.

For the auto-managed derivations (`CLUSTER_CONTAINER_WORKSPACE`,
`CLUSTER_UV_FOLDSEEK_EXEC`, …) at the bottom of `.env_example`, treat them as
read-only. They are derived from `CLUSTER_UV_VENV` and are sourced into the
remote `.env` by `slurm_helper.sh`'s `_emit_tool_exports`.

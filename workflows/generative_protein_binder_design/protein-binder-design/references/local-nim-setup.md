# Running the BioNeMo NIMs locally (self-hosted)

Use this when you want to self-host RFdiffusion, ProteinMPNN, and a co-folder (Boltz2)
instead of the managed `build.nvidia.com` endpoints — e.g. to avoid rate limits or to
keep a campaign self-contained on one node. The pipeline logic is unchanged; only the
base URL changes (no `Authorization` header for local NIMs).

## Prerequisites

- Docker with the NVIDIA container runtime (`docker run --gpus ...` works).
- An NGC API key in `NGC_API_KEY` (used to pull images and download model weights).
- `docker login nvcr.io -u '$oauthtoken' -p "$NGC_API_KEY"` once.

## Images

| NIM | Image | Idle GPU | Serves |
|---|---|---|---|
| RFdiffusion | `nvcr.io/nim/ipd/rfdiffusion:latest` | ~24 GB | `:8000/v1/biology/ipd/rfdiffusion/generate` |
| ProteinMPNN | `nvcr.io/nim/ipd/proteinmpnn:latest` | ~1.5 GB | `:8000/v1/biology/ipd/proteinmpnn/predict` |
| Boltz2 | `nvcr.io/nim/mit/boltz2:latest` | ~8 GB | `:8000/biology/mit/boltz2/predict` |

All three co-fit on one ≥48 GB GPU (~33 GB idle together).

## Launch pattern

Give each NIM its own persistent cache (so weights download once), a name, and a port.
Mount the cache at `/opt/nim/.cache` and make it writable:

```bash
mkdir -p ~/nimcache_rfd ~/nimcache_pmpnn ~/nimcache_boltz2 && chmod 777 ~/nimcache_*
docker run -d --name rfdiffusion --gpus device=0 --shm-size=4g \
  -e NGC_API_KEY -v ~/nimcache_rfd:/opt/nim/.cache -p 8081:8000 \
  nvcr.io/nim/ipd/rfdiffusion:latest
docker run -d --name proteinmpnn --gpus device=0 --shm-size=4g \
  -e NGC_API_KEY -v ~/nimcache_pmpnn:/opt/nim/.cache -p 8082:8000 \
  nvcr.io/nim/ipd/proteinmpnn:latest
docker run -d --name boltz2 --gpus device=0 --shm-size=8g \
  -e NGC_API_KEY -v ~/nimcache_boltz2:/opt/nim/.cache -p 8083:8000 \
  nvcr.io/nim/mit/boltz2:latest
```

Wait for readiness (first start downloads weights — minutes):

```bash
curl -fsS http://localhost:8081/v1/health/ready && echo RFD_OK
curl -fsS http://localhost:8082/v1/health/ready && echo PMPNN_OK
curl -fsS http://localhost:8083/v1/health/ready && echo BOLTZ2_OK
```

If the NIMs and your client share a user-defined docker network, reach them by container
name instead of published ports (e.g. `http://rfdiffusion:8000/...`).

## GPU profile selection

Most of these NIMs **auto-select** a profile by compute capability (SM) and just work on
a supported GPU. Some NIMs match profiles by **exact GPU model**, so on a GPU that has no
bundled profile the container exits early with `NIMProfileIDNotFound` / "0 profiles found".
If that happens, list the bundled profiles and pin the one that matches **your** GPU's
compute capability:

```bash
# 1) list the profiles this NIM ships and their tags (gpu / compute capability / precision / backend)
docker run --rm --gpus device=0 -e NGC_API_KEY \
  <nim-image> list-model-profiles
# 2) choose the profile whose tags match YOUR GPU (compute capability first), then pin it:
docker run -d --name <nim> --gpus device=0 --shm-size=8g \
  -e NGC_API_KEY -e NIM_MODEL_PROFILE=<profile_id> \
  -v ~/nimcache_<nim>:/opt/nim/.cache -p 8083:8000 <nim-image>
```

A TRT-optimized engine built for one GPU generally loads on another of the **same compute
capability** (you may see a benign cross-device warning). Always select the profile for the
hardware you are running on — **do not copy a `NIM_MODEL_PROFILE` id from another machine**,
and check the NIM's support matrix for your exact GPU.

## Then point the pipeline at local

Set the local base URLs and drop the `Authorization` header. Request/response shapes for
every NIM are in `references/pipeline.md` — only the URL/auth changes between hosted and
local.

# Running the BioNeMo NIMs locally

Use this guide when the user chooses self-hosted RFdiffusion, ProteinMPNN, and
Boltz2. Inference inputs go to the configured local services without an
Authorization header. Pulling containers and downloading model weights still
requires access to NVIDIA NGC.

## Prerequisites

- Docker with the NVIDIA Container Toolkit and a supported GPU/driver stack.
- An NGC key in `NGC_API_KEY`, with access to the selected model versions and
  their governing terms accepted.
- Choose the image version and digest from each model's NGC catalog:
  [RFdiffusion](https://catalog.ngc.nvidia.com/orgs/nim/teams/ipd/containers/rfdiffusion),
  [ProteinMPNN](https://catalog.ngc.nvidia.com/orgs/nim/teams/ipd/containers/proteinmpnn),
  [Boltz2](https://catalog.ngc.nvidia.com/orgs/nim/teams/mit/containers/boltz2).

Authenticate with the existing environment key through stdin, with shell tracing
disabled. This avoids putting the secret in the command's argument list:

```bash
set +x
printf '%s' "${NGC_API_KEY:?Set NGC_API_KEY}" | docker login nvcr.io --username '$oauthtoken' --password-stdin
```

## Image and API contracts

Set `RFD_IMAGE`, `PMPNN_IMAGE`, and `BOLTZ2_IMAGE` to the respective full NGC
repository reference ending in `@sha256:` plus its 64-character digest. Obtain
the digest from the selected catalog version or the `RepoDigests` output of
`docker image inspect` after pulling that explicit version. Do not invent a
digest or use a moving tag. Save the three references and selected GPU profiles
in the campaign parameters so a resumed run uses the same containers.

| NIM | Image variable | Cache mount | Local prediction path |
|---|---|---|---|
| RFdiffusion | `RFD_IMAGE` | `/opt/nim/.cache` | `/biology/ipd/rfdiffusion/generate` |
| ProteinMPNN | `PMPNN_IMAGE` | `/home/nvs/.cache/nim` | `/biology/ipd/proteinmpnn/predict` |
| Boltz2 | `BOLTZ2_IMAGE` | `/opt/nim/.cache` | `/biology/mit/boltz2/predict` |

These paths follow the published
[RFdiffusion 2.3.0](https://docs.nvidia.com/nim/bionemo/rfdiffusion/2.3.0/quickstart-guide.html),
[ProteinMPNN 1.2.0](https://docs.nvidia.com/nim/bionemo/proteinmpnn/1.2.0/quickstart-guide.html),
and [Boltz2 1.10.0](https://docs.nvidia.com/nim/bionemo/boltz2/1.10.0/getting-started.html)
guides; check the selected release's API/cache contract when changing versions.
Hosted prediction URLs additionally include `/v1`. GPU memory depends on the
model, profile, and input length; check each support matrix and run the stages
sequentially if the models do not fit together.

## Launch pattern

Run the following Bash block after setting the three image variables. It checks
every digest before launching any service. Each container receives only its own
cache directory and exposes an unauthenticated API on the host's loopback address.

```bash
(
set +x
set -euo pipefail
: "${NGC_API_KEY:?Set NGC_API_KEY}"
: "${RFD_IMAGE:?Set the RFdiffusion repository digest}"
: "${PMPNN_IMAGE:?Set the ProteinMPNN repository digest}"
: "${BOLTZ2_IMAGE:?Set the Boltz2 repository digest}"

require_digest() {
  local image_ref="$1" repository="$2" digest
  digest="${image_ref#"$repository@sha256:"}"
  if [[ "$image_ref" != "$repository@sha256:$digest" || ! "$digest" =~ ^[a-f0-9]{64}$ ]]; then
    printf 'Expected an immutable image digest for %s\n' "$repository" >&2
    exit 1
  fi
}
require_digest "$RFD_IMAGE" nvcr.io/nim/ipd/rfdiffusion
require_digest "$PMPNN_IMAGE" nvcr.io/nim/ipd/proteinmpnn
require_digest "$BOLTZ2_IMAGE" nvcr.io/nim/mit/boltz2

mkdir -p "$HOME/nimcache_rfd" "$HOME/nimcache_pmpnn" "$HOME/nimcache_boltz2"
chmod 700 "$HOME/nimcache_rfd" "$HOME/nimcache_pmpnn" "$HOME/nimcache_boltz2"
docker run -d --name rfdiffusion --gpus device=0 --shm-size=4g \
  --user "$(id -u):$(id -g)" -e NGC_API_KEY \
  -v "$HOME/nimcache_rfd:/opt/nim/.cache" -p 127.0.0.1:8081:8000 "$RFD_IMAGE"
docker run -d --name proteinmpnn --gpus device=0 --shm-size=4g \
  --user "$(id -u):$(id -g)" -e NGC_API_KEY \
  -v "$HOME/nimcache_pmpnn:/home/nvs/.cache/nim" -p 127.0.0.1:8082:8000 "$PMPNN_IMAGE"
docker run -d --name boltz2 --gpus device=0 --shm-size=8g \
  --user "$(id -u):$(id -g)" -e NGC_API_KEY \
  -v "$HOME/nimcache_boltz2:/opt/nim/.cache" -p 127.0.0.1:8083:8000 "$BOLTZ2_IMAGE"
)
```

The three caches are owned by the invoking user and mode 700; the containers run
with that user's UID/GID. For releases requiring a fixed container user, arrange
access to these exact directories for that UID before launch. Do not widen
permissions on unrelated caches. First startup downloads weights and can take
several minutes. Check readiness with local GET requests that send no credentials
or protein data and bypass configured HTTP proxies:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:8081/v1/health/ready
curl --noproxy '*' -fsS http://127.0.0.1:8082/v1/health/ready
curl --noproxy '*' -fsS http://127.0.0.1:8083/v1/health/ready
```

## GPU profile selection

If startup reports `NIMProfileIDNotFound` or no compatible profiles, inspect the
selected release's supported GPUs and available profiles. For releases exposing
`list-model-profiles`, reuse the already validated image digest:

```bash
docker run --rm --gpus device=0 -e NGC_API_KEY "${BOLTZ2_IMAGE:?Set the validated Boltz2 digest}" list-model-profiles
```

Select a profile documented for that GPU and add `-e NIM_MODEL_PROFILE` to the
corresponding launch command after setting the chosen profile in the environment.
Matching compute capability alone does not establish engine compatibility.
Record the profile with the image digest. Then use the local prediction paths
above in the pipeline and omit hosted authentication headers.

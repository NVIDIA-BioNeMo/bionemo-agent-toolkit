# Deploy Nam's local release candidate

## Contents

- [Source and image](#source-and-image)
- [Launch](#launch)
- [Readiness and discovery](#readiness-and-discovery)
- [Operational details](#operational-details)

## Source and image

Nam supplied this exact image:

```text
nvcr.io/nvstaging/nim/rfd4-proteina:1.0.0-rc.20260929072057-951ccf3c88abb594
```

Keep it pinned when reproducing his RC; do not replace it with `latest`, a
public RFdiffusion image, or a source-built development image. The current
branch and bundled requests are newer than this RC, so schema compatibility
must be checked against the running image. Its image-tag SHA was not present
as a Git object in the inspected checkout; no matching source revision or
image digest was inferred.

Prerequisites: Docker, an NVIDIA container runtime and compatible GPU/driver,
nvstaging entitlement, disk for the image and model caches, and a source
checkout containing `scripts/deploy_nim.sh`. No minimum GPU-memory figure
for this exact RC was established by this skill's validation.

The originally supplied checkout was on an early `main` scaffold. A separate
checkout avoids replacing someone's working branch:

```bash
git -C /path/to/rfd4-proteina-nim worktree add --detach \
  /tmp/rfd4-nim-rc-src origin/ntdo/oss-pipeline
export RFD4_SOURCE_DIR=/tmp/rfd4-nim-rc-src
test -f "$RFD4_SOURCE_DIR/scripts/deploy_nim.sh"
```

Use a fresh path; reuse a suitable existing checkout if already available.
The source branch moves. Record `git -C "$RFD4_SOURCE_DIR" rev-parse HEAD`.

## Launch

Run this launcher on an isolated GPU host allocated to the task. It runs
as root inside the container and exposes all GPUs. The command below binds
the unauthenticated service to loopback; do not publish it on shared or cloud
network interfaces. For a shared GPU host, use a reviewed launcher copy with
`--gpus device=<allocated-GPU-ID>` and test a non-root UID with writable cache
and workspace mounts. Non-root support for this exact RC has not been verified.

Supply `NGC_API_KEY_STAGING` in the shell environment using the user's normal
secret mechanism. Test presence without displaying it:

```bash
: "${NGC_API_KEY_STAGING:?Set your nvstaging API key in the environment}"
export RFD4_IMAGE=nvcr.io/nvstaging/nim/rfd4-proteina:1.0.0-rc.20260929072057-951ccf3c88abb594
export RFD4_CONTAINER=rfd4-skill-rc
export RFD4_WORK_DIR=/tmp/rfd4-skill-rc-data
```

The upstream script removes an existing container with the chosen name.
Choose an unused name. Check before calling it; do not remove someone else's
container as a setup convenience:

```bash
if docker container inspect "$RFD4_CONTAINER" >/dev/null 2>&1; then
  printf 'Choose a new RFD4_CONTAINER name; this one exists.\n' >&2
else
  NAME="$RFD4_CONTAINER" PORT=127.0.0.1:6626 BACKEND=bioir WORK_DIR="$RFD4_WORK_DIR" \
    "$RFD4_SOURCE_DIR/scripts/deploy_nim.sh" "$RFD4_IMAGE"
fi
```

This is Nam's launcher with explicit name, port, backend, and work-directory
settings. Its `-p "${PORT}":8000` expansion supports the loopback address in
`PORT`, producing `127.0.0.1:6626:8000` without changing the source. It runs
`docker run` in the foreground, with stdout redirected
inside the script; readiness does not run after it in that terminal until the
container exits. Use another terminal for checks, or run the launcher in the
background with a log path in the user's run directory. It does not itself
wait for a ready response.

## Readiness and discovery

From another terminal, wait for a JSON `true` body, not merely HTTP 200.
The custom health routes can return `false` with HTTP 200 before startup ends.
The check intentionally connects only to the local container at
`127.0.0.1:6626`; it accepts no target URL and follows no redirects or proxies.

```bash
python - <<'PY'
import http.client
import json
import time

STARTUP_TIMEOUT_SECONDS = 900
READINESS_TIMEOUT_SECONDS = 5
POLL_INTERVAL_SECONDS = 5
deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
while time.monotonic() < deadline:
    connection = http.client.HTTPConnection('127.0.0.1', 6626, timeout=READINESS_TIMEOUT_SECONDS)
    try:
        connection.request('GET', '/v1/health/ready')
        response = connection.getresponse()
        if response.status == 200 and json.loads(response.read()) is True:
            print('RFD4 is ready')
            break
    except (OSError, ValueError, http.client.HTTPException):
        pass
    finally:
        connection.close()
    time.sleep(POLL_INTERVAL_SECONDS)
else:
    raise SystemExit('Not ready after 15 minutes; inspect container logs before retrying')
PY
```

Inspect `docker logs "$RFD4_CONTAINER"` if startup fails. Read the running
schema before submitting examples from a newer branch:

```bash
curl --noproxy '*' --fail --silent --show-error --max-time 30 \
  http://127.0.0.1:6626/v1/tasks --output tasks.json
curl --noproxy '*' --fail --silent --show-error --max-time 30 \
  http://127.0.0.1:6626/openapi.json --output openapi.json
```

Use a new run directory for these files. Compare task names, input dialects,
recycle strategy names, and optional fields such as `batch_size` to the
request. Older images used `unconditional` and legacy `midpeak6_*` names.
Inspect their own contract and checkpoint behavior; do not automatically
downgrade newer payloads or silently change the requested RC.

From the installed skill directory, after a compatible request is prepared:

```bash
python scripts/design.py --mode local --base-url http://localhost:6626 \
  --request /path/to/compatible-request.json \
  --output-dir /tmp/rfd4-rc-design-run
```

## Operational details

The inspected `deploy_nim.sh` resolves credentials as follows: exported
`NGC_API_KEY_STAGING`, then exported `NGC_API_KEY`, then `NGC_API_KEY_STAGING`
from `ENV_FILE` (default repository `.env`). It logs into the image registry
with `--password-stdin`, pulls if needed, and passes the selected value as
container `NGC_API_KEY`. This runtime variable is required because this
RC style downloads weights at startup; successful registry login alone is
not sufficient. Avoid shell tracing and credential-bearing logs.

| Launcher setting | Default / behavior |
| --- | --- |
| `PORT` | Upstream default `6626` publishes on all interfaces; use `127.0.0.1:6626` as above to bind loopback, mapped to container `8000` |
| `NAME` | `rfd4-proteina-nim-deploy`; existing same-name container is removed |
| `BACKEND` | `bioir`, passed as `NIM_BACKEND` |
| `WORK_DIR` | `/tmp/rfd4-deploy-${USER}` |
| GPU selection | `--gpus all`; do not promise an idle GPU or a single-GPU allocation |
| Runtime | `--user 0`, working directory `/opt/nim/output` |
| Bind mounts | `cache` → `/opt/nim/.cache`; `workspace` → `/opt/nim/workspace`; `output` → `/opt/nim/output`; `bioir_cache` → `/opt/nim/bioir_cache` |

The script makes those four host directories writable and sets
`BIOIR_KERNEL_CACHE_DIR=/opt/nim/bioir_cache`. Keep caches on local disk;
the source notes warn about stale NFS handles and root-squashed paths.
It publishes the port using Docker's `-p PORT:8000` form; the loopback-qualified
`PORT` above limits exposure. Root execution and GPU allocation still need
the host isolation or reviewed launcher changes described under Launch.

The source's separate `run_from_registry.sh` serves development images with
baked-in weights. Its cache/auth behavior is not evidence for the RC above.
Docker was unavailable in the skill-authoring environment; this deployment
procedure was source-reviewed, not executed there.

---
name: proteinmpnn-nim
description: >
  Run ProteinMPNN inverse folding via NVIDIA NIM to design protein sequences for a target backbone. Use for ProteinMPNN, inverse folding, sequence design, backbone redesign, fixed chains/residues, omit_AAs, sampling temperature, soluble model, hosted NVIDIA API, local Docker, PDB input, and multi-FASTA output.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# ProteinMPNN NIM

Design protein sequences for a supplied backbone PDB. Use this `SKILL.md` for
first-pass hosted/local usage; load supplemental files only when needed:

- `references/api.md`: exact endpoints, schemas, Docker flags, response fields.
- `references/science.md`: inverse-folding uses, limits, and validation.
- `references/parameters.md`: design controls, fixed positions, sampling.
- `references/validation.md`: FASTA, score, and structure checks.
- `references/examples.md`: compact hosted/local request patterns.

## Choose Mode

Honor an explicitly configured runtime before asking. `NIM_API_MODE=local` selects
the local service at `PROTEINMPNN_NIM_URL`; the URL defaults to
`http://localhost:8000` for a NIM running in the same host or container. Ask only
when neither the environment nor the user's request makes the mode clear:

> Hosted NVIDIA API or local Docker NIM?

- Hosted: `https://health.api.nvidia.com/v1/biology/ipd/proteinmpnn/predict`
- Local: `${PROTEINMPNN_NIM_URL:-http://localhost:8000}/biology/ipd/proteinmpnn/predict`

Local inference paths do not include `/v1/`. Hosted requests use `Authorization: Bearer $NGC_API_KEY`. Supported local Docker
startup uses `NGC_API_KEY` (or `NVIDIA_API_KEY` via the preflight) for
registry login, entitlement checks, and first-run model downloads; pass it
into the container with `-e NGC_API_KEY`. Local inference requests use no
auth header after readiness. Warm-cache key-free startup varies by
image/version and should not be assumed.

## Local Docker

For local setup, run the full sequence — env preflight, `docker login`,
`docker run`, readiness loop, then the no-auth localhost request; do not answer
with only a localhost Python request. For the exact preflight (`.env` sourcing,
`NGC_API_KEY`/`NVIDIA_API_KEY` handling, and the `docker run` for
`nvcr.io/nim/ipd/proteinmpnn:latest`), copy the command block in
[`references/api.md`](references/api.md) under **Docker Reference** verbatim.
This NIM's cache mount is `/home/nvs/.cache/nim`, not `/opt/nim/.cache`.
When `PROTEINMPNN_NIM_URL` is supplied, the service is already managed elsewhere;
use that URL and do not start another Docker container.

Readiness:

```bash
proteinmpnn_nim_url="${PROTEINMPNN_NIM_URL:-http://localhost:8000}"
until curl -sf "${proteinmpnn_nim_url%/}/v1/health/ready"; do sleep 5; done
```

## Request Pattern

Read PDB content inline; do not send only a file path.

```python
import os
from pathlib import Path
import requests

HOSTED = os.getenv("NIM_API_MODE", "hosted").strip().lower() != "local"
pdb_content = Path("1R42.pdb").read_text()
nim_url = os.getenv("PROTEINMPNN_NIM_URL", "http://localhost:8000").rstrip("/")
url = (
    "https://health.api.nvidia.com/v1/biology/ipd/proteinmpnn/predict"
    if HOSTED else f"{nim_url}/biology/ipd/proteinmpnn/predict"
)
headers = {"Content-Type": "application/json"}
if HOSTED:
    headers["Authorization"] = f"Bearer {os.environ['NGC_API_KEY']}"

payload = {
    "input_pdb": pdb_content,
    "num_seq_per_target": 10,
    "sampling_temp": [0.1],
    "use_soluble_model": False,
    "ca_only": False,
}
response = requests.post(url, headers=headers, json=payload, timeout=300)
response.raise_for_status()
result = response.json()
```

Common controls:

- Redesign only chain A: `"input_pdb_chains": ["A"]`.
- Exclude amino acids: `"omit_AAs": ["C"]` or `"omit_AAs": ["M"]`.
- Diversity: `"sampling_temp": [0.1, 0.3, 0.5]` (always a list).
- Solubility bias: `"use_soluble_model": True`.
- Candidate count: `num_seq_per_target` is 1-100.

## Save And Report Output

Save the returned `mfasta` and pair scores only with designed (non-native/WT)
rows, using the snippet in [`references/examples.md`](references/examples.md)
under **Save Multi-FASTA**. Validate promising designs by predicting structures
with Boltz2 or OpenFold3 and comparing them to the target backbone. For
FASTA/score sanity checks, read `references/validation.md`.

## Limits And Troubleshooting

- Minimum GPU VRAM: about 3 GB.
- `sampling_temp` must be a list, even for one value.
- Empty `mfasta`: check non-empty `input_pdb` and `num_seq_per_target >= 1`.
- PDB parse errors: use valid PDB ATOM records.
- Local URL 404 usually means an accidental `/v1/` prefix.
- Cache mount error: use `/home/nvs/.cache/nim` inside the container.

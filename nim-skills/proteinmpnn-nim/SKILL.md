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

Ask only when context is unclear:

> Hosted NVIDIA API or local Docker NIM?

- Hosted: `https://health.api.nvidia.com/v1/biology/ipd/proteinmpnn/predict`
- Local: `http://localhost:8000/biology/ipd/proteinmpnn/predict`

Local inference paths do not include `/v1/`. Hosted requests use `Authorization: Bearer $NGC_API_KEY`. Supported local Docker
startup uses `NGC_API_KEY` (or `NVIDIA_API_KEY` via the preflight) for
registry login, entitlement checks, and first-run model downloads; pass it
into the container with `-e NGC_API_KEY`. Local inference requests use no
auth header after readiness. Warm-cache key-free startup varies by
image/version and should not be assumed.

## Local Docker

For local setup answers, copy the preflight below exactly before `docker login`,
`docker run`, readiness, and the no-auth local request. Do not answer with only
a localhost Python request. This NIM's cache mount is unique:
`/home/nvs/.cache/nim`, not `/opt/nim/.cache`.

```bash
set -a
[ -f .env ] && . ./.env
set +a

if [ -z "${NGC_API_KEY:-}" ] && [ -n "${NVIDIA_API_KEY:-}" ]; then
  export NGC_API_KEY="$NVIDIA_API_KEY"
fi
: "${NGC_API_KEY:?Set NGC_API_KEY or NVIDIA_API_KEY}"
: "${LOCAL_NIM_CACHE:?Set LOCAL_NIM_CACHE}"

echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin

export NIM_TEST_GPU="${NIM_TEST_GPU:-0}"
mkdir -p "${LOCAL_NIM_CACHE}"
chmod 777 "${LOCAL_NIM_CACHE}"

docker run -it \
  --runtime=nvidia \
  --gpus "device=${NIM_TEST_GPU}" \
  -e NGC_API_KEY \
  -v "${LOCAL_NIM_CACHE}:/home/nvs/.cache/nim" \
  -p 8000:8000 \
  nvcr.io/nim/ipd/proteinmpnn:latest
```

Readiness:

```bash
until curl -sf http://localhost:8000/v1/health/ready; do sleep 5; done
```

## Request Pattern

Read PDB content inline; do not send only a file path.

```python
import os
from pathlib import Path
import requests

HOSTED = True
pdb_content = Path("1R42.pdb").read_text()
url = (
    "https://health.api.nvidia.com/v1/biology/ipd/proteinmpnn/predict"
    if HOSTED else "http://localhost:8000/biology/ipd/proteinmpnn/predict"
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

```python
mfasta = result["mfasta"]
Path("designed_sequences.fa").write_text(mfasta)

# Scores correspond to designed sequences. The mfasta may include a native/WT
# row; do not pair that row with generated-sequence scores.
headers = [line for line in mfasta.splitlines() if line.startswith(">")]
designed_headers = [
    h for h in headers if "native" not in h.lower() and "wt" not in h.lower()
]
for header, score in zip(designed_headers, result.get("scores", [])):
    print(f"{header} score: {score:.4f}")
```

Validate promising designs by predicting structures with Boltz2 or OpenFold3
and comparing them to the target backbone. For FASTA/score sanity checks, read
`references/validation.md`.

## Limits And Troubleshooting

- Minimum GPU VRAM: about 3 GB.
- `sampling_temp` must be a list, even for one value.
- Empty `mfasta`: check non-empty `input_pdb` and `num_seq_per_target >= 1`.
- PDB parse errors: use valid PDB ATOM records.
- Local URL 404 usually means an accidental `/v1/` prefix.
- Cache mount error: use `/home/nvs/.cache/nim` inside the container.

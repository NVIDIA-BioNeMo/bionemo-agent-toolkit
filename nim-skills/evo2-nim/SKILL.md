---
name: evo2-nim
description: >
  Generate and analyze DNA sequences using NVIDIA's Evo 2 BioNeMo NIM microservice. Use for Evo2/Evo 2, DNA generation, genomic sequence generation, hosted generation, local Docker deployment, local forward passes, layer outputs, logits, sampled probabilities, and BioNeMo NIM workflows.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "requests>=2.28; numpy>=1.24"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Evo 2 NIM

Use Evo 2 for DNA generation and, locally, layer-output extraction. Use this
`SKILL.md` for basic hosted/local use; load supplemental files only when needed:

- `references/api.md`: exact schemas, layer names, Docker flags, hardware notes.
- `references/science.md`: genomic use cases, limits, and interpretation.
- `references/parameters.md`: generation/forward parameter effects.
- `references/validation.md`: DNA, probability, timing, and tensor checks.
- `references/examples.md`: compact hosted/local request patterns.

## Choose Mode

Ask only when context is unclear:

> Hosted NVIDIA API or local Docker Evo 2 NIM?

- Hosted generation: `https://health.api.nvidia.com/v1/biology/arc/evo2-40b/generate`
- Local generation: `http://localhost:8000/biology/arc/evo2/generate`
- Local forward/layer outputs: `http://localhost:8000/biology/arc/evo2/forward`

The hosted docs expose generation. `/forward` is documented for local Docker;
do not invent a hosted `/forward` endpoint. Hosted requests use `Authorization: Bearer $NGC_API_KEY`. Supported local Docker
startup uses `NGC_API_KEY` (or `NVIDIA_API_KEY` via the preflight) for
registry login, entitlement checks, and first-run model downloads; pass it
into the container with `-e NGC_API_KEY`. Local inference requests use no
auth header after readiness. Warm-cache key-free startup varies by
image/version and should not be assumed.

## Local Docker Requirements

Evo 2 local deployment requires FP8-capable GPUs. Do not present A100 as
compatible; A100 can pull the image but fails warmup because FP8 requires
compute capability 8.9 or higher.

- Default 40B: 2x H100 80 GB or 1x H200 141 GB. Use `NIM_TEST_GPUS=0,1` for
  2x H100, or `NIM_TEST_GPUS=0` for one H200.
- 7B fallback: set `NIM_VARIANT=7b`; supported GPUs include H100, H200,
  RTX 6000 Ada, and L40S.
- Approximate disk: 110 GB for 40B, 50 GB for 7B.

Use shell env first; source repo-root `.env` only if present. Do not invent a
cache default or drop the `NVIDIA_API_KEY` fallback.

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

# 40B default: 0,1 for 2x H100; set 0 for a single H200.
export NIM_TEST_GPUS="${NIM_TEST_GPUS:-0,1}"
mkdir -p "${LOCAL_NIM_CACHE}"
chmod 777 "${LOCAL_NIM_CACHE}"

# For 7B: export NIM_VARIANT=7b; export NIM_TEST_GPUS="${NIM_TEST_GPUS:-0}"
docker run --rm -it --name evo2-nim \
  --runtime=nvidia \
  --gpus "\"device=${NIM_TEST_GPUS}\"" \
  -e NGC_API_KEY \
  -e NIM_VARIANT \
  -v "${LOCAL_NIM_CACHE}:/opt/nim/.cache" \
  -p 8000:8000 \
  nvcr.io/nim/arc/evo2:2
```

Readiness:

```bash
until curl -sf http://localhost:8000/v1/health/ready; do sleep 10; done
```

If RTX PRO 6000 Blackwell Workstation fails with no Transformer Engine
attention backend, treat it as outside the current validated matrix and rerun
on a documented GPU/runtime.

## DNA Generation

Normalize prompts before sending. Use A/C/G/T unless ambiguous bases are a
deliberate modeling choice and clearly reported.

```python
import json
import os
from pathlib import Path
import requests

HOSTED = True

def clean_dna(value: str) -> str:
    seq = "".join(value.upper().split())
    invalid = sorted(set(seq) - set("ACGT"))
    if invalid:
        raise ValueError(f"Unexpected DNA characters: {''.join(invalid)}")
    return seq

prompt = clean_dna("ACTGACTGACTGACTG")
nim_url = os.getenv("EVO2_NIM_URL", "http://localhost:8000")
url = (
    "https://health.api.nvidia.com/v1/biology/arc/evo2-40b/generate"
    if HOSTED else f"{nim_url}/biology/arc/evo2/generate"
)
headers = {"Content-Type": "application/json"}
if HOSTED:
    api_key = os.getenv("NGC_API_KEY")
    headers["Authorization"] = f"Bearer {api_key}"

payload = {
    "sequence": prompt,
    "num_tokens": 64,
    "temperature": 0.7,
    "top_k": 3,
    "top_p": 0.0,
    "random_seed": 1,
    "enable_sampled_probs": True,
    "enable_elapsed_ms_per_token": True,
}
response = requests.post(url, headers=headers, json=payload, timeout=180)
response.raise_for_status()
result = response.json()
seq = result["sequence"]
if sorted(set(seq.upper()) - set("ACGT")):
    raise ValueError("Generated sequence contains unexpected non-ACGT bases")

Path("evo2_generation.json").write_text(json.dumps(result, indent=2) + "\n")
Path("evo2_generated.fa").write_text(f">evo2_generated\n{seq}\n")
print(f"Generated {len(seq)} bases in {result.get('elapsed_ms')} ms")
```

Only request `enable_logits` when needed; logits can make responses large.
`random_seed` supports development reproducibility, not biological certainty.

## Local Forward Pass

Forward returns base64-encoded NPZ tensors.

```python
import base64
import io
import os
import numpy as np
import requests

nim_url = os.getenv("EVO2_NIM_URL", "http://localhost:8000")
payload = {
    "sequence": clean_dna("ACTGACTGACTG"),
    "output_layers": ["output_layer", "decoder.layers.3.self_attention"],
}
response = requests.post(
    f"{nim_url}/biology/arc/evo2/forward",
    headers={"Content-Type": "application/json"},
    json=payload,
    timeout=300,
)
response.raise_for_status()
npz_bytes = base64.b64decode(response.json()["data"])
with open("evo2_forward_outputs.npz", "wb") as handle:
    handle.write(npz_bytes)
arrays = np.load(io.BytesIO(npz_bytes), allow_pickle=False)
for name in arrays.files:
    arr = arrays[name]
    print(name, arr.shape, arr.dtype, bool(np.isfinite(arr).all()), float(arr.mean()))
```

## Validate And Report

Save request/response JSON, generated FASTA, and a metrics JSON with sequence
length, GC fraction, ambiguous-base fraction, homopolymer length, sampled-prob
checks, and elapsed timing. Treat invalid schema or alphabet as hard failures;
treat extreme GC, low complexity, duplicates, and missing motifs as warnings.
For deeper checks, read `references/validation.md`.

Key fields: `sequence`, `num_tokens`, `temperature`, `top_k` (0-6), `top_p`
(0-1), `random_seed`, `enable_sampled_probs`, `enable_elapsed_ms_per_token`,
and optional `enable_logits`.

## Troubleshooting

- `401/403`: hosted key missing/expired or not sent as Bearer token.
- `422`: wrong field names such as `max_tokens` instead of `num_tokens`.
- Local auth confusion: do not send `Authorization` to localhost.
- Local startup: first run downloads model assets; wait on `/v1/health/ready`.
- FP8 failure: use hosted, 7B on a supported FP8 GPU, or documented 40B GPUs.

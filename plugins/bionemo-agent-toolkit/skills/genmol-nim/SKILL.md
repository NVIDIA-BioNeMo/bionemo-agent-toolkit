---
name: genmol-nim
description: >
  Generate novel drug-like molecules using the GenMol NIM microservice. Use for de novo generation, scaffold decoration, motif extension, lead optimization, SAFE notation, QED or LogP ranking, hosted NVIDIA API calls, or local Docker deployment. GenMol takes SAFE notation in the smiles field, not ordinary SMILES.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "safe-mol>=0.1.14; requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# GenMol NIM

Generate drug-like molecules with GenMol. Use this `SKILL.md` for first-pass
hosted/local usage; load supplemental files only when needed:

- `references/api.md`: endpoints, schema, Docker flags, response fields.
- `references/science.md`: use cases, strengths, limits, and handoffs.
- `references/parameters.md`: SAFE patterns and tuning effects.
- `references/validation.md`: chemical and artifact checks.
- `references/examples.md`: compact request patterns.

## Choose Mode

Ask only when context is unclear:

> Hosted NVIDIA API or local Docker NIM?

- Hosted: `https://health.api.nvidia.com/v1/biology/nvidia/genmol/generate`
- Local: `http://localhost:8000/generate`

Hosted requests use `Authorization: Bearer $NGC_API_KEY`. Supported local Docker
startup uses `NGC_API_KEY` (or `NVIDIA_API_KEY` via the preflight) for
registry login, entitlement checks, and first-run model downloads; pass it
into the container with `-e NGC_API_KEY`. Local inference requests use no
auth header after readiness. Warm-cache key-free startup varies by
image/version and should not be assumed.

## Local Docker

Use shell env first; source repo-root `.env` only if present. Do not print keys.
For local setup answers, include this sequence: env preflight, `docker login`,
`docker run`, readiness loop, then a no-auth localhost request. Do not invent a
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

export NIM_TEST_GPU="${NIM_TEST_GPU:-0}"
mkdir -p "${LOCAL_NIM_CACHE}"
chmod 777 "${LOCAL_NIM_CACHE}"

docker run --rm -it --name genmol-nim \
  --runtime=nvidia --gpus=all \
  -e NVIDIA_VISIBLE_DEVICES="${NIM_TEST_GPU}" \
  --shm-size=2G \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e NGC_API_KEY \
  -v "${LOCAL_NIM_CACHE}:/opt/nim/.cache" \
  -p 8000:8000 \
  nvcr.io/nim/nvidia/genmol:1.0.1
```

GenMol is single-GPU; `NIM_TEST_GPU` defaults to `0`. Wait for readiness:

```bash
until curl -sf http://localhost:8000/v1/health/ready; do sleep 5; done
```

## SAFE Input

The API field is named `smiles`, but GenMol expects SAFE notation. Masked
positions use `[*{min-max}]`.

- De novo: `safe_input = "[*{20-30}]"`
- Scaffold decoration: `safe_input = scaffold_to_safe("C1CC(=O)NC1", 10, 15)`
- Motif extension: `safe_input = f"[*{{5-10}}].{motif_safe}.[*{{5-10}}]"`
- Lead optimization: encode the hit, then replace a fragment with `.[*{5-12}]`

Use `safe-mol` for conditioned generation. Simple ring scaffolds may raise
`SAFEFragmentationError`; fall back to the original SMILES plus a SAFE mask.

```python
import safe as sf

def scaffold_to_safe(smiles: str, frag_min: int, frag_max: int) -> str:
    try:
        safe_str = sf.encode(smiles)
    except sf.SAFEFragmentationError:
        safe_str = smiles
    return f"{safe_str}.[*{{{frag_min}-{frag_max}}}]"
```

Wider masks increase diversity; tight masks keep analog size more predictable.

## Request Pattern

```python
import os
import requests

HOSTED = True
url = (
    "https://health.api.nvidia.com/v1/biology/nvidia/genmol/generate"
    if HOSTED else "http://localhost:8000/generate"
)
headers = {"Content-Type": "application/json"}
if HOSTED:
    headers["Authorization"] = f"Bearer {os.environ['NGC_API_KEY']}"

payload = {
    "smiles": "[*{20-30}]",  # SAFE notation
    "num_molecules": 30,
    "temperature": "1.0",    # string, not float
    "noise": "1.0",          # string, not float
    "step_size": 1,
    "scoring": "QED",        # or "LogP"
    "unique": False,
}

response = requests.post(url, headers=headers, json=payload, timeout=180)
response.raise_for_status()
result = response.json()
```

Gotchas:

- `temperature` and `noise` are strings.
- `num_molecules` is 1-1000; invalid/duplicate molecules may be filtered, so
  request extra when the user needs a minimum count.
- `scoring` is `"QED"` for drug-likeness or `"LogP"` for lipophilicity.
- Set `unique=True` for deduplicated analog lists.

## Save And Report Output

```python
if result.get("status") != "success":
    raise RuntimeError(result.get("error", "GenMol failed"))

molecules = sorted(result["molecules"], key=lambda m: m["score"], reverse=True)
for rank, mol in enumerate(molecules[:30], start=1):
    print(f"{rank:3d} {mol['score']:8.4f} {mol['smiles']}")

with open("generated_molecules.smi", "w", encoding="utf-8") as handle:
    handle.write("smiles\tscore\n")
    for mol in molecules:
        handle.write(f"{mol['smiles']}\t{mol['score']:.4f}\n")
```

For chemical validity, uniqueness, PAINS/alerts, and visualization with RDKit,
read `references/validation.md`.

## Limits And Troubleshooting

- Fewer molecules than requested is expected after filtering.
- Invalid SAFE strings cause `status: "failed"` or validation errors.
- Install `safe-mol` only for scaffold, motif, or lead-optimization workflows;
  de novo masks work without conversion.
- Local startup downloads about 20 GB into `LOCAL_NIM_CACHE`.
- Container issues: confirm `nvidia-smi`, NVIDIA Container Toolkit, and
  `--runtime=nvidia`; use `NIM_TEST_GPU` to choose the single visible GPU.

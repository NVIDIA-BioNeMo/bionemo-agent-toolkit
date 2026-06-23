---
name: diffdock-nim
description: >
  Run DiffDock molecular docking via NVIDIA NIM to predict small-molecule binding poses against protein targets. Use for DiffDock, molecular docking, ligand docking, blind docking, SMILES or SDF ligands, ranked poses, confidence scores, hosted NVIDIA API, or local Docker deployment.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# DiffDock NIM

Predict protein-ligand binding poses with blind docking. Use this `SKILL.md` for
first-pass hosted/local usage; load supplemental files only when needed:

- `references/api.md`: exact hosted/local endpoints, schemas, Docker flags.
- `references/science.md`: docking use cases, limits, and handoffs.
- `references/parameters.md`: ligand formats, pose counts, diffusion controls.
- `references/validation.md`: receptor, ligand, pose, and confidence checks.
- `references/examples.md`: compact hosted/local and pose-saving patterns.

## Choose Mode

Ask only when context is unclear:

> Hosted NVIDIA API or local Docker NIM?

- Hosted: `https://health.api.nvidia.com/v1/biology/mit/diffdock`
- Local: `http://localhost:8000/molecular-docking/diffdock/generate`

The hosted and local paths differ. Local has no `/v1/` prefix and uses the
`/molecular-docking/` route. Hosted requests use `Authorization: Bearer $NGC_API_KEY`. Supported local Docker
startup uses `NGC_API_KEY` (or `NVIDIA_API_KEY` via the preflight) for
registry login, entitlement checks, and first-run model downloads; pass it
into the container with `-e NGC_API_KEY`. Local inference requests use no
auth header after readiness. Warm-cache key-free startup varies by
image/version and should not be assumed.

## Local Docker

For local setup answers, copy the preflight below exactly. Keep the optional
`.env` load, `NVIDIA_API_KEY` fallback, `LOCAL_NIM_CACHE`,
`NVIDIA_VISIBLE_DEVICES=0` default, `--shm-size=2G`, and both `--ulimit` flags.

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

docker run --rm -it --name diffdock-nim \
  --runtime=nvidia \
  -e NVIDIA_VISIBLE_DEVICES="${NIM_TEST_GPU}" \
  --shm-size=2G \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e NGC_API_KEY \
  -v "${LOCAL_NIM_CACHE}:/opt/nim/.cache" \
  -p 8000:8000 \
  nvcr.io/nim/mit/diffdock:2.2.0
```

Readiness:

```bash
until curl -sf http://localhost:8000/v1/health/ready; do sleep 5; done
```

## Prepare Inputs

Protein receptor must be ATOM records only. Strip headers, water, and HETATM.

```python
from pathlib import Path
raw_pdb = Path("protein.pdb").read_text()
protein = "\n".join(line for line in raw_pdb.splitlines() if line.startswith("ATOM"))
if not protein:
    raise ValueError("protein.pdb has no ATOM records")
```

Ligand options:

- SMILES: `ligand = "CC(=O)OC1=CC=CC=C1C(=O)O"`; `ligand_file_type = "txt"`.
- SDF: `ligand = Path("ligand.sdf").read_text()`; `ligand_file_type = "sdf"`.
- MOL2: `ligand_file_type = "mol2"`.

Do not use `"smiles"` as `ligand_file_type`; SMILES is `"txt"`.

## Request Pattern

```python
import os
import requests

HOSTED = True
url = (
    "https://health.api.nvidia.com/v1/biology/mit/diffdock"
    if HOSTED else "http://localhost:8000/molecular-docking/diffdock/generate"
)
headers = {"Content-Type": "application/json"}
if HOSTED:
    headers["Authorization"] = f"Bearer {os.environ['NGC_API_KEY']}"

payload = {
    "protein": protein,
    "ligand": ligand,
    "ligand_file_type": ligand_file_type,
    "num_poses": 10,
    "time_divisions": 20,
    "steps": 18,
    "save_trajectory": False,
}
response = requests.post(url, headers=headers, json=payload, timeout=300)
response.raise_for_status()
result = response.json()
```

## Save And Report Output

`ligand_positions` and `position_confidence` are parallel ranked lists.
`position_confidence[0]` is the rank-1 pose confidence.

```python
poses = result["ligand_positions"]
scores = result["position_confidence"]
for rank, (pose_sdf, score) in enumerate(zip(poses, scores), start=1):
    filename = f"pose_{rank}_conf{score:.3f}.sdf"
    with open(filename, "w", encoding="utf-8") as handle:
        handle.write(pose_sdf)
    print(f"pose {rank}: confidence={score:.4f} saved={filename}")
print(f"best pose confidence: {scores[0]:.4f}")
```

View pose SDF files with the receptor in PyMOL, ChimeraX, or UCSF Chimera. For
pose sanity checks and confidence caveats, read `references/validation.md`.

## Limits And Troubleshooting

- Max `num_poses`: 100. Max `time_divisions`: 20. Max `steps`: 18.
- Single GPU; local minimum is about 24 GB VRAM.
- `422`: invalid `ligand_file_type`, invalid SMILES/SDF, or no ATOM records.
- Empty poses: validate receptor ATOM records and ligand parseability.
- Local URL 404 usually means the wrong hosted path or an accidental `/v1/`.

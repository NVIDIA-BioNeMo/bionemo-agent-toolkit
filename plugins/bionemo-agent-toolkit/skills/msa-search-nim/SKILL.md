---
name: msa-search-nim
description: >
  Generate multiple sequence alignments (MSAs) for protein sequences using the ColabFold MSA-Search NIM. Use for homolog search, UniRef30/ColabFold env searches, A3M or FASTA alignments, paired MSA search for complexes, PDB70 structural templates, hosted NVIDIA API calls, or local Docker deployment.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# MSA-Search NIM

Generate protein MSAs with GPU-accelerated MMSeqs2. Use this `SKILL.md` for
first-pass hosted/local usage; load supplemental files only when needed:

- `references/api.md`: exact endpoints, schemas, Docker flags, response fields.
- `references/science.md`: MSA purpose, pairing/templates, limits, handoffs.
- `references/parameters.md`: database, pairing, depth, and template tuning.
- `references/validation.md`: alignment, template, and artifact checks.
- `references/examples.md`: compact hosted/local request patterns.

## Choose Mode And Endpoint

Ask only when context is unclear:

> Hosted NVIDIA API or local Docker NIM?

- Hosted standard MSA: `https://health.api.nvidia.com/v1/biology/colabfold/msa-search/predict`
- Hosted paired MSA: `https://health.api.nvidia.com/v1/biology/colabfold/msa-search/paired/predict`
- Local standard MSA: `http://localhost:8000/biology/colabfold/msa-search/predict`
- Local paired MSA: `http://localhost:8000/biology/colabfold/msa-search/paired/predict`
- Local templates: `http://localhost:8000/biology/colabfold/msa-search/structure-templates/predict`

Local inference paths do not include `/v1/`. Hosted requests use `Authorization: Bearer $NGC_API_KEY`. Supported local Docker
startup uses `NGC_API_KEY` (or `NVIDIA_API_KEY` via the preflight) for
registry login, entitlement checks, and first-run model downloads; pass it
into the container with `-e NGC_API_KEY`. Local inference requests use no
auth header after readiness. Warm-cache key-free startup varies by
image/version and should not be assumed.
The hosted template path returned HTTP 404 in validation, so use local Docker
for template search unless the hosted docs/service changes.

## Local Docker

Local setup requires a GPU and about 1.4 TB / 1660 GB of NVMe storage for
databases. For setup answers, include env preflight, `docker login`,
`docker run`, readiness, and then no-auth local inference. Do not invent a cache
default or drop the `NVIDIA_API_KEY` fallback.

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

echo "MSA-Search local databases require about 1.4 TB (1660 GB) of NVMe storage."
mkdir -p "${LOCAL_NIM_CACHE}"
chmod 777 "${LOCAL_NIM_CACHE}"

docker run --rm --name msa-search \
  --runtime=nvidia \
  --gpus all \
  -e NGC_API_KEY \
  -v "${LOCAL_NIM_CACHE}:/opt/nim/.cache" \
  -p 8000:8000 \
  nvcr.io/nim/colabfold/msa-search:2
```

Readiness:

```bash
until curl -sf http://localhost:8000/v1/health/ready; do sleep 10; done
```

## Standard MSA Request

Use exact case-sensitive database names and response keys.

```python
import os
import requests

HOSTED = True
url = (
    "https://health.api.nvidia.com/v1/biology/colabfold/msa-search/predict"
    if HOSTED else "http://localhost:8000/biology/colabfold/msa-search/predict"
)
headers = {"Content-Type": "application/json"}
if HOSTED:
    headers["Authorization"] = f"Bearer {os.environ['NGC_API_KEY']}"

payload = {
    "sequence": "SGSMKTAISLPDETFDRVSRRASELGMSRSEFFTKAAQR",
    "databases": ["Uniref30_2302", "colabfold_envdb_202108"],
    "e_value": 0.0001,
    "output_alignment_formats": ["a3m"],
}
response = requests.post(url, headers=headers, json=payload, timeout=300)
response.raise_for_status()
result = response.json()
```

## Paired MSA Request

Use paired search for protein complexes; payload field is `sequences` plural,
and output is `alignments_by_chain`.

```python
url = (
    "https://health.api.nvidia.com/v1/biology/colabfold/msa-search/paired/predict"
    if HOSTED else "http://localhost:8000/biology/colabfold/msa-search/paired/predict"
)
payload = {
    "sequences": [chain_a_sequence, chain_b_sequence],
    "e_value": 0.0001,
    "output_alignment_formats": ["a3m"],
}
```

## Local Template Search

Use local Docker for structural templates. Set `max_msa_sequences=500` unless
`NIM_GLOBAL_MAX_MSA_DEPTH` was changed.

```python
url = "http://localhost:8000/biology/colabfold/msa-search/structure-templates/predict"
headers = {"Content-Type": "application/json"}
payload = {
    "sequence": "VLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVA",
    "structural_template_databases": ["pdb70_220313"],
    "max_structures": 20,
    "max_msa_sequences": 500,
}
```

## Save Outputs

```python
# Standard MSA: result["alignments"][database][format]["alignment"]
for db_name, formats in result.get("alignments", {}).items():
    for fmt_name, data in formats.items():
        with open(f"msa_{db_name}.{fmt_name}", "w", encoding="utf-8") as handle:
            handle.write(data["alignment"])

# Paired MSA: one alignment set per chain
for chain_id, chain_data in result.get("alignments_by_chain", {}).items():
    for db_name, formats in chain_data.items():
        for fmt_name, data in formats.items():
            with open(f"msa_chain_{chain_id}_{db_name}.{fmt_name}", "w", encoding="utf-8") as handle:
                handle.write(data["alignment"])

# Template search: save mmCIF structures and M8 hit tables
for name, cif in result.get("structures", {}).items():
    open(f"template_{name}.cif", "w", encoding="utf-8").write(cif)
for name, hit_table in result.get("search_hits", {}).items():
    open(f"template_hits_{name}.m8", "w", encoding="utf-8").write(hit_table)
```

A3M output can feed OpenFold3, AlphaFold2, or RoseTTAFold. For alignment depth,
template, and sequence sanity checks, read `references/validation.md`.

## Limits And Troubleshooting

- Sequence length: 1-4096 amino acids; `X` works since v2.3.0.
- `max_msa_sequences`: 1-500; local GPU server default must match
  `NIM_GLOBAL_MAX_MSA_DEPTH`.
- Paired MSA requires at least two sequences.
- Local URL 404 usually means an accidental `/v1/` prefix.
- First local run can take hours while databases populate `LOCAL_NIM_CACHE`.

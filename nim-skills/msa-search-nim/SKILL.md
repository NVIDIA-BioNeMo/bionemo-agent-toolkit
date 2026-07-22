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

> **Recommended deployment path.** For any real workflow, do NOT start with the plain
> full-database `docker run` below — it triggers the NIM's built-in downloader over the
> full ~1.4 TB set, which is slow (well over an hour, and on large single-DB profiles it
> can stall past 80 minutes; see the measurements under "Parallel Download"). Instead,
> default to the two-step fast path:
>
> 1. **Pick the smallest task-specific profile** for your task ("Faster Startup" below) —
>    e.g. `databases:uniref30` for paired/complex work.
> 2. **Download the database(s) in parallel with aria2c and launch via `NIM_MODEL_NAME`**
>    ("Parallel Download For Any Database Set" below) — ~14 min for UniRef30 instead of
>    >80 min, measured on an H100 node. This applies whether you need one database or
>    the full `databases:all` set.
>
> Use the plain `docker run` in this section only for a quick `databases:pdb70` smoke
> test, or when you specifically want the NIM to manage its own blob cache. The parallel
> path below covers every case, including the full `databases:all` set.

Local setup requires a GPU. The full database set is about 1.4 TB / 1660 GB of
NVMe storage, but you rarely need all of it — use a **task-specific profile**
(see "Faster Startup" below) downloaded in parallel to download only the databases your task requires,
which cuts both storage and startup time. Size the cache volume to the profile you
pick. For setup answers, include env preflight, `docker login`,
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

## Faster Startup: Task-Specific Database Profiles

The full database download is ~1.4 TB and can take well over an hour on first launch. If you
only need some databases, select a **task-specific profile** so the NIM downloads just those.
This is the single biggest lever on local startup time.

List the profiles your image actually ships (hashes change between releases — never hardcode
them):

```bash
docker run --rm --entrypoint list-model-profiles nvcr.io/nim/colabfold/msa-search:2
```

Then pass the chosen hash with `NIM_MODEL_PROFILE`:

```bash
docker run --rm --name msa-search \
  --runtime=nvidia --gpus all \
  -e NGC_API_KEY \
  -e NIM_MODEL_PROFILE=<hash-from-list-model-profiles> \
  -v "${LOCAL_NIM_CACHE}:/opt/nim/.cache" \
  -p 8000:8000 \
  nvcr.io/nim/colabfold/msa-search:2
```

Profiles available in this image (confirm hashes with `list-model-profiles`):

| Profile tags | Databases | Best for | Storage |
|---|---|---|---|
| `databases:pdb70` | PDB70 | Quick testing / smoke check | ~100 MB |
| `databases:uniref30` | UniRef30 | **Paired MSA search for complexes** — UniRef30 is the only DB used for species-based pairing | ~500 GB |
| `databases:uniref30,pdb70,pdb` | UniRef30 + PDB70 + PDB structures | Structural template search | ~700 GB |
| `databases:all` (default) | UniRef30 + ColabFold envdb + PDB70 + PDB100 + PDB structures | Full sensitivity, all databases | ~1.2 TB |

Verify the loaded profile after readiness:

```bash
curl -s localhost:8000/v1/metadata | jq
```

Notes:

- The request-level `databases` parameter only selects among databases **already
  downloaded**; it does NOT change what is fetched at startup. Startup footprint is set by
  `NIM_MODEL_PROFILE` alone.
- **Paired search needs UniRef30 only.** `colabfold_envdb_202108` has no taxonomy and cannot
  be used for pairing, so `databases:uniref30` is the correct, smallest profile for
  complex/paired workflows — it skips the envdb, the largest part of the full set.
- For maximum monomer sensitivity (UniRef30 + envdb merged) you still need `databases:all`;
  there is no envdb-inclusive profile smaller than the full set.

### Custom Or Individual Databases

To use a single manually downloaded database (or your own MMSeqs2 DB), download it from NGC
and point the NIM at the mount with `NIM_MODEL_NAME` instead of a profile:

```bash
ngc registry model download-version nim/colabfold/msa-search:uniref30_2302-m18v1
# then mount the directory and set -e NIM_MODEL_NAME=/databases
```

`NIM_MODEL_NAME` **replaces** the profile databases entirely — the NIM uses only what is
under that directory (discovered by scanning for `**/*.idx`). Mount multiple databases under
one parent to combine them. NGC-downloaded databases are pre-indexed for GPU Server; custom
databases must be indexed with `mmseqs createindex` first. Individually downloadable NGC model
versions: `uniref30_2302-m18v1`, `colabfold_envdb_202108-m18v1`, `pdb70_220313-m18v1`,
`pdb100_230517-m18v1`, `pdb_20251028_zip-m18v1`.

## Recommended: Parallel Download For Any Database Set (Fast Deployment)

**This is the recommended way to download the databases at all — for any profile,
including the full `databases:all` set.** Task-specific profiles cut *what* you
download; this parallel downloader cuts *how long* that download takes. Use it whether
you need one database or all of them. The gain is largest for the `databases:uniref30` profile, which is ~490 GB
dominated by two very large files (a ~241 GB GPU index and a ~134 GB sequence DB).

The NIM's built-in downloader parallelizes **across files** (`max_parallel_files=10`) but pulls
each file over roughly one connection. The NGC CDN throttles a single connection to ~20–25
MB/s, so while the downloader is fetching one of the two giant files, most of its parallel
slots sit idle and throughput collapses to that single-flow rate. Measured on an H100 node,
the built-in path did not reach `/health/ready` in over 80 minutes.

A range-parallel downloader splits **each file** into many byte-range segments (the NGC CDN
advertises `accept-ranges: bytes`), so a single 241 GB file is pulled over 16 connections at
once — ~15× the single-flow rate. Same node, `aria2c` fetched the full ~490 GB in **~13.5
minutes**.

Workflow (download once with aria2, then start the NIM against the files via `NIM_MODEL_NAME`):

```bash
# 1) Get presigned file URLs for the individual database model version from NGC.
#    (Requires NGC_API_KEY. The response arrays `urls` and `filepath` are positionally paired.)
curl -s -H "Authorization: Bearer $NGC_API_KEY" \
  'https://api.ngc.nvidia.com/v2/org/nim/team/colabfold/models/msa-search/uniref30_2302-m18v1/files' \
  -o files.json

# 2) Build an aria2 input file (URL + target filename per entry) and download in parallel.
python3 - <<'PY'
import json
d = json.load(open("files.json"))
lines = []
for url, path in zip(d["urls"], d["filepath"]):
    lines += [url.strip(), "  dir=/data/fast-db", f"  out={path}"]
open("aria.in", "w").write("\n".join(lines) + "\n")
PY
aria2c -i aria.in \
  --max-concurrent-downloads=4 --max-connection-per-server=16 --split=16 \
  --min-split-size=1M --continue=true --file-allocation=none

# 3) Start the NIM against the downloaded directory. NIM_MODEL_NAME makes the NIM discover
#    databases by scanning for **/*.idx, bypassing the profile/blob cache entirely.
docker run -d --name msa-search --runtime=nvidia --gpus all \
  -e NGC_API_KEY \
  -e NIM_MODEL_NAME=/databases \
  -v /data/fast-db:/databases \
  -p 8000:8000 \
  nvcr.io/nim/colabfold/msa-search:2
```

For **all databases** (equivalent to `databases:all`), repeat step 1 for each individual DB
version and download them into sibling directories under one parent, then point
`NIM_MODEL_NAME` at that parent — the NIM discovers every DB by scanning `**/*.idx`:

```bash
# fetch each DB's file list into /data/all-db/<db>/ ... then one aria2c per list, e.g.:
for V in uniref30_2302-m18v1 colabfold_envdb_202108-m18v1 pdb70_220313-m18v1 \
         pdb100_230517-m18v1 pdb_20251028_zip-m18v1; do
  curl -s -H "Authorization: Bearer $NGC_API_KEY" \
    "https://api.ngc.nvidia.com/v2/org/nim/team/colabfold/models/msa-search/$V/files" \
    -o "files_$V.json"
  # build an aria2 input from files_$V.json (dir=/data/all-db) and run aria2c on it
done
# then launch once against the parent:
#   docker run -d ... -e NIM_MODEL_NAME=/databases -v /data/all-db:/databases ...
```

The per-connection CDN throttle is the same for every database, so parallel download helps
the full set proportionally — the more you download, the more absolute time it saves.

Notes:

- The presigned URLs expire (typically within a day) — build the aria2 input and start the
  download promptly after fetching `files.json`.
- Keep the downloaded directory's internal layout intact (e.g. `uniref30_2302/…`); the
  `filepath` values already encode it. The NIM needs the `.idx` file plus its companion files
  and the small `.UNIREF30_READY` / `*.tar.gz.unpacked` markers.
- The bottleneck is the CDN's per-connection cap, not local disk or CPU — a fast NVMe volume
  writes far faster than the network delivers. Raising `--split` / `--max-connection-per-server`
  helps only up to the node's aggregate egress ceiling.
- Best of all: download the profile once, then **persist the cache volume** (or this
  `fast-db` directory) and mount it on future nodes for a ~20 s warm start with no re-download.

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

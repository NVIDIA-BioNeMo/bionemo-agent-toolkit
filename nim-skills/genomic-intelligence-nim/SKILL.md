---
name: genomic-intelligence-nim
description: >
  Predict regulatory features, gene structure, and expression directly from DNA sequence using Genomic Intelligence's hosted DNA language models. Six tasks over one hosted REST contract — promoter regions, splice donor/acceptor sites, enhancer activity, chromatin state, sequence-to-expression (log TPM), and de-novo gene/transcript annotation. Use for regulatory genomics, promoter/enhancer/splice/chromatin scanning, expression prediction, and gene annotation from a gene name, a genomic region, or a FASTA. Bearer auth; no local GPU or model weights.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Genomic Intelligence NIM

One skill, six DNA-sequence prediction tasks, served by Genomic Intelligence's
hosted GPU service. Give it a **gene name**, a **genomic region**, or a **FASTA**;
it resolves a sequence, calls `POST /v1/tasks/{task}/predict`, and writes a
report + machine-readable JSON. Inference is remote — no model weights, GPU, or
heavyweight Python stack; the only dependency is `requests`.

Load supplemental files only when needed:

- `references/tasks.md`: per-task model, bounds, output fields, and biology.
- `references/api.md`: endpoints, request/response envelope, async, errors.
- `references/authentication.md`: `GI_API_KEY`, base URL, partner tiers.
- `references/sequence-acquisition.md`: gene/region → FASTA, TSS window, species.
- `references/errors.md`: error envelope, rate limits, async polling detail.

> **Hosted, third-party service.** Genomic Intelligence is operated by Genomic
> Intelligence, not NVIDIA. The interface is the hosted-NIM shape (HTTPS +
> `Authorization: Bearer` + JSON). There is no local Docker mode.

## The six tasks

| Task | What it predicts | Mode | Length |
|---|---|---|---|
| `promoter` | Promoter regions (sliding window) | sync | 1–500,000 bp |
| `splice` | Splice donor/acceptor sites | sync | 1–500,000 bp |
| `enhancer` | Developmental & housekeeping enhancer activity | sync | 1–500,000 bp |
| `chromatin` | Chromatin state across hundreds of tracks | sync | 1–500,000 bp |
| `expression` | Expression as log(TPM+1) | sync | **exactly 9,198 bp** |
| `annotation` | De-novo gene/transcript structure | **async** | 1–500,000 bp |

`expression` additionally needs a cell-type/assay context string
(`--description`, e.g. `"K562 cells"`) and an exact 9,198 bp TSS-centred window.
`annotation` submits with `Prefer: respond-async` and polls to completion.
Details: `references/tasks.md`.

## Authentication

This skill calls a hosted API and requires a partner bearer key (`gi_…`):

```bash
export GI_API_KEY=gi_yourkeyhere
```

Request a key at **contact@genomicintelligence.ai**. Do not commit or hard-code a
key — it is resolved from the environment. Optional override: `GI_BASE_URL`
(default `https://api.genomicintelligence.ai`). See
`references/authentication.md`.

## Install

Python ≥3.8 and one package — no weights, no GPU:

```bash
pip install requests
```

## Provided scripts

Unlike the inline-only `nim-skills/`, this skill ships a small, self-contained
(`requests`-only) runner, because the surface spans six tasks plus an async job
(`annotation`) and an exact-window contract (`expression`) that do not inline
cleanly. Shipping `scripts/` is not prohibited by CONTRIBUTING and other skills
do it; the runner is the same proven
client used across Genomic Intelligence's other integrations.

- **`scripts/gi_predict.py`** — one CLI, six tasks: FASTA → prediction →
  `report.md` + `result.json` + `reproducibility/`, and a compact JSON summary on
  stdout. Owns auth, length validation, the sync/async split, and error handling.
- **`scripts/gi_fetch.py`** — optional acquisition: gene symbol or region →
  reference FASTA via Ensembl (public, no key), including TSS-centring for
  `expression`.
- **`scripts/gi_client.py`**, **`scripts/gi_ensembl.py`** — the `/v1` client and
  Ensembl helpers the two CLIs import.

**Use the provided scripts — do not hand-roll `curl`, an Ensembl fetch, or an
inline HTTP client.** They own the length/async/expression contract.

## Quick start

Each task ships a real reference FASTA in `assets/demo/`:

```bash
# Promoter scan of the TP53 locus (chr17, GRCh38)
python scripts/gi_predict.py --task promoter --demo --output out/promoter

# Splice sites in HBB
python scripts/gi_predict.py --task splice --demo --output out/splice

# Expression (needs a cell-type context; fixture is a 9,198 bp TSS window)
python scripts/gi_predict.py --task expression --demo --description "K562 cells" --output out/expr

# De-novo annotation (async submit → poll, no extra flags)
python scripts/gi_predict.py --task annotation --demo --output out/annot
```

**By gene name** (fetch → predict, the common real case):

```bash
FASTA=$(python scripts/gi_fetch.py --gene TP53 --out out/tp53.fa)
python scripts/gi_predict.py --task promoter --input "$FASTA" --output out/promoter

# Expression of HBB in K562 — the exact 9,198 bp TSS window is built for you
FASTA=$(python scripts/gi_fetch.py --gene HBB --for-expression --out out/hbb.fa)
python scripts/gi_predict.py --task expression --input "$FASTA" --description "K562 cells" --output out/expr
```

`gi_predict.py` prints a compact JSON summary to **stdout** (headline scalars
only; bulky per-item arrays stay in `result.json`). Progress/verification lines
go to **stderr**:

```
[gi-<task>] OK — wrote out/<task>/report.md (NNN ms wall)
```

## Minimal inline call (no scripts)

For the simplest sync tasks you can call the endpoint directly:

```python
import os, requests

base = os.environ.get("GI_BASE_URL", "https://api.genomicintelligence.ai").rstrip("/")
resp = requests.post(
    f"{base}/v1/tasks/promoter/predict",
    headers={"Authorization": f"Bearer {os.environ['GI_API_KEY']}",
             "Content-Type": "application/json",
             "User-Agent": "BioNeMo-GI-Skill/0.1.0"},
    json={"sequence": "ACGT...", "sequence_name": "example"},
    timeout=300,
)
resp.raise_for_status()
body = resp.json()          # {"data": {...}, "meta": {...}}
print(body["data"]["summary"])
```

Prefer the runner for `expression` (exact-window + `description`) and
`annotation` (async) — those are error-prone to inline.

## Standard workflow

1. **Identify the task** from the request (map to one of the six above; if
   ambiguous between promoter/enhancer/chromatin, ask — they are distinct models).
2. **Resolve the sequence.** If the user attached a FASTA, use it. If they named
   a gene, `gi_fetch.py --gene <SYMBOL>` (add `--for-expression` for expression).
   If they gave a region, `gi_fetch.py --region <chr:start-end>`. Add
   `--species <production_name>` for non-human (default human/GRCh38).
3. **Predict:**
   ```bash
   python scripts/gi_predict.py --task <task> --input <FASTA> --output <dir> \
     [--model <id>] [--description "<cell type>"]   # description: expression only
   ```
4. **Read the result:** parse the stdout JSON for the headline; open
   `<dir>/report.md` or `<dir>/result.json` for detail.

## Validate and report

Treat an invalid alphabet, an out-of-bounds length, a missing `expression`
window/description, or a non-2xx response as **hard failures** (the runner exits
non-zero and names the cause on stderr). Treat zero hits on a sequence you
expected to be feature-bearing as a **warning**. Record `meta.model` and
`meta.request_id` for audit.

## Troubleshooting

| Symptom (stderr) | Cause | Fix |
|---|---|---|
| `GI_API_KEY is not set` | No key | `export GI_API_KEY=gi_…` |
| `invalid input — expects exactly 9,198 bp` | Wrong expression window | Use `gi_fetch.py --gene X --for-expression` |
| `--description is required` | expression w/o context | `--description "K562 cells"` |
| `API error: [401 …]` | Bad/revoked key | Re-check `GI_API_KEY` |
| `API error: [422 …]` | Body/model rejected | Check `--model` in `references/tasks.md` |
| `API error: [429 …]` | Rate limit | Back off; partner tiers have caps |
| `API error: [504 upstream_timeout]` | Large sync req, cold GPU | Retry or shorten |
| `parsed an empty sequence` | Empty/invalid FASTA | Check the file is a single ACGT record |

More: `references/errors.md`.

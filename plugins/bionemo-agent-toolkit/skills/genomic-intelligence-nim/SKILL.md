---
name: genomic-intelligence-nim
description: >
  Predict regulatory features, gene structure, and expression directly from DNA sequence using Genomic Intelligence's hosted DNA language models. Six tasks over one hosted REST contract — promoter regions, splice donor/acceptor sites, enhancer activity, chromatin state, sequence-to-expression (log TPM), and de-novo gene/transcript annotation. Use for regulatory genomics, promoter/enhancer/splice/chromatin scanning, expression prediction, and gene annotation from a gene name, a genomic region, or a FASTA. Bearer auth; no local GPU or model weights.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "requests>=2.28"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Genomic Intelligence NIM

One skill, six DNA-sequence prediction tasks, served by the hosted Genomic
Intelligence API. Give it a **gene name**, a **genomic region**, or a **FASTA**;
it resolves a sequence, calls that task's own predict operation, and writes a
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
>
> Research and development use. Not for clinical or diagnostic decisions.

## The six tasks

Each task is its own published operation — `POST /v1/tasks/promoter/predict`,
`/v1/tasks/splice/predict`, and so on — with its own request schema, its own
minimum length, and its own closed `options` object. The URLs are unchanged from
what callers already send.

| Task | What it predicts | Recommended mode | Accepted length | `context_window_bp` |
|---|---|---|---|---|
| `promoter` | Promoter regions (sliding window) | sync | 300–500,000 bp | 2,000 bp (300 bp models exist) |
| `splice` | Splice donor/acceptor sites | sync | 100–500,000 bp | 15,000 bp |
| `enhancer` | Developmental & housekeeping enhancer activity | sync | 50–500,000 bp | 249 bp |
| `chromatin` | Chromatin state across hundreds of tracks | sync | 200–500,000 bp | 1,000 bp |
| `expression` | Expression as log(TPM+1) | sync | **9,198–500,000 bp** | n/a (`trained_window_bp` 9,198) |
| `annotation` | De-novo gene/transcript structure | async | 1,000–500,000 bp | n/a |

`Recommended mode` is guidance, not a constraint — every task accepts both. Omit `Prefer` for a synchronous `200`; send `Prefer: respond-async` for a `202` plus `GET /v1/tasks/jobs/{job_id}`. Only the composite workflow enforces a mode, rejecting sync above 50,000 bp with `413 sync_too_large`.

The minimum is **admission control, not regime**. A sequence above the floor but
shorter than the selected model's `bio_spec.context_window_bp` is *accepted and
scored* — against a window padded out to the context window. So a 100 bp enhancer
request succeeds, but the model saw ~150 bp of padding; compare your length
against `context_window_bp` (from `GET /v1/tasks/{task}/models`) to know whether
it scored real sequence. Longer-than-context input is fine: the scanner steps a
prediction window at a time and pads only the final partial window. All lengths
are measured **after whitespace is stripped**, so a line-wrapped FASTA body can be
pasted verbatim. Under the floor and over the cap are both
`422 validation_failed` — over-length is *not* a `413`.

`expression` additionally needs a cell-type/assay context string
(`--description`, e.g. `"K562 cells"`). The model always scores exactly one
9,198 bp TSS-centred window, so 9,198 bp is a hard floor — but the endpoint
accepts up to 500,000 bp and will cut the window for you if you pass
`--tss-index` (the 0-based TSS offset into the sequence). `--tss-index` is
required for any expression sequence that is not exactly 9,198 bp.
`annotation` defaults to `Prefer: respond-async` and polls to completion; the
mode is the runner's choice, not an API constraint.
Details: `references/tasks.md`.

`options` is closed (`additionalProperties: false`) on every task, and each task
declares different keys — `description` exists only on `expression`. An
unrecognised key is a hard `422 validation_failed`, never ignored, so never
forward an option you have not confirmed against the live schema.

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

This skill ships a small, self-contained (`requests`-only) runner rather than
inline snippets: the surface spans six tasks plus an async job (`annotation`)
and a windowing contract (`expression`) that do not inline cleanly. The runner
is the same client Genomic Intelligence's other integrations use.

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

# Or hand over a whole locus and name the TSS; the server slices TSS +/- 4,599 bp.
#
# STRAND: expression scores whatever you send, in the orientation you send it.
# It never reverse-complements, and nothing in the request or the response
# reports strand -- a wrong-strand window returns a confident number, not an
# error. Always submit gene-sense sequence. --region returns the strand you ask
# for and defaults to --strand 1, so a minus-strand gene needs --strand -1
# explicitly. HBB is minus-strand.
LOCUS=$(python scripts/gi_fetch.py --region chr11:5,220,000-5,240,000 --strand -1 \
  --out out/locus.fa)
# Offset of the TSS into the returned sequence, 0-based, whitespace stripped.
# Plus strand:  TSS_INDEX = TSS - REGION_START
# Minus strand: TSS_INDEX = REGION_END - TSS      (the sequence is reverse-complemented)
# Must satisfy 4599 <= TSS_INDEX <= len(sequence) - 4599.
# HBB 5' end on the minus strand is 5,229,395 (Ensembl, GRCh38).
TSS_INDEX=$(( 5240000 - 5229395 ))
python scripts/gi_predict.py --task expression --input "$LOCUS" --description "K562 cells" \
  --tss-index "$TSS_INDEX" --output out/expr
```

Prefer `--for-expression` when you have a gene symbol: it resolves the canonical
transcript and cuts the window for you, so there is no offset to get wrong. A
`--tss-index` that is in range but wrong is not an error — it scores the wrong
window and returns `200`.

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

Prefer the runner for `expression` (window/`tss_index` bounds + `description`) and
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
     [--model <id>] [--description "<cell type>"] [--tss-index <n>]
     # --description and --tss-index: expression only
   ```
4. **Read the result:** parse the stdout JSON for the headline; open
   `<dir>/report.md` or `<dir>/result.json` for detail.

## Validate and report

Treat an invalid alphabet, an out-of-bounds length, a missing `expression`
window/description/`--tss-index`, or a non-2xx response as **hard failures** (the
runner exits non-zero and names the cause on stderr). Treat zero hits on a
sequence you expected to be feature-bearing as a **warning**. Record
`meta.model` and `meta.request_id` for audit. For `expression`, also check the
`scored_window` / `tss_index` echoed in the stdout summary: a `--tss-index` that
is in range but wrong is not an error, it just scores the wrong window.

## Troubleshooting

| Symptom (stderr) | Cause | Fix |
|---|---|---|
| `GI_API_KEY is not set` | No key | `export GI_API_KEY=gi_…` |
| `sequence too short: … < 9,198 bp minimum` | Expression sequence below the window size | Use `gi_fetch.py --gene X --for-expression` |
| `sequence too short: … bp minimum` (other tasks) | Below the task floor (promoter 300, splice 100, enhancer 50, chromatin 200, annotation 1,000) | Fetch more sequence; server-side this is a `422`, not a `413` |
| `API error: [413 payload_too_large]` | Raw request body over 16 MiB | Split the input; this is the body cap, not the sequence cap |
| `--tss-index is required unless the sequence is exactly 9,198 bp` | Longer locus, no TSS named | Add `--tss-index <0-based offset>` |
| `--tss-index … outside the allowed range` | TSS too close to an edge | Submit more flanking sequence |
| `--description is required` | expression w/o context | `--description "K562 cells"` |
| `API error: [401 …]` | Bad/revoked key | Re-check `GI_API_KEY` |
| `API error: [422 …]` | Body/model rejected | Check `--model` in `references/tasks.md` |
| `API error: [429 …]` | Rate limit | Back off; partner tiers have caps |
| `API error: [504 timeout]` | Large sync req, cold GPU | Retry or shorten |
| `parsed an empty sequence` | Empty/invalid FASTA | Check the file is a single ACGT record |
| `invalid input — …: sequence contains characters outside ACGTN` | IUPAC ambiguity codes or gap characters | Resolve them to explicit bases; the parser refuses rather than deleting them, because deleting shifts every downstream coordinate |
| `invalid input — …: expected a single FASTA record` | Multi-record FASTA | Split the file and submit one record per request |
| `network error reaching the API` | DNS/TLS/connection failure or read timeout | Transport-level, not a request problem; retry |
| `timed out waiting for the job` | Async job outlived the poll deadline | Retry, or shorten the input |

More: `references/errors.md`.

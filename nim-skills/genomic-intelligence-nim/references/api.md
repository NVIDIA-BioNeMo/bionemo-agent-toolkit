# API reference — the /v1 contract

Genomic Intelligence exposes one versioned REST contract; all six tasks share
the same request/response shape. Authoritative, live schema:
<https://api.genomicintelligence.ai/v1/openapi.json> (human view:
<https://api.genomicintelligence.ai/redoc>). This file is a point-in-time
snapshot — if it disagrees with the OpenAPI doc, the OpenAPI doc wins.

## Endpoints

```
POST https://api.genomicintelligence.ai/v1/tasks/{task}/predict
     task ∈ { promoter, splice, enhancer, chromatin, annotation }
POST https://api.genomicintelligence.ai/v1/tasks/expression/predict
     # same URL shape, but its own published operation and its own,
     # stricter request schema (ExpressionPredictRequest)
GET  https://api.genomicintelligence.ai/v1/tasks/jobs/{job_id}   # async (annotation)
```

- Base URL overridable via `GI_BASE_URL`.
- Auth: `Authorization: Bearer $GI_API_KEY` (partner key, prefix `gi_`).
- `Content-Type: application/json`, `Accept: application/json`.

## Request body

```json
{
  "sequence": "ACGT…",           // required; A/C/G/T(/N)
  "sequence_name": "TP53",        // optional label echoed back
  "model": "g0-promoter-2000bp",  // optional; omit for the task default
  "options": { "description": "K562 cells" }  // required for expression only
}
```

`expression` has a different body — it is closed to unknown fields, `options` is
a closed object whose only (required) key is `description`, and it takes a fifth
field:

```json
{
  "sequence": "ACGT…",                        // required, 9,198–500,000 bp
  "options": { "description": "K562 cells" }, // required
  "tss_index": 12345,                         // required unless len == 9198
  "sequence_name": "HBB",
  "model": "…"
}
```

Length bounds are per-task (see `references/tasks.md`): 1–500,000 bp for every
task, plus a 9,198 bp **floor** for `expression`, which always scores exactly one
9,198 bp window — `sequence[tss_index-4599 : tss_index+4599]`. Lengths and
`tss_index` are measured on the **whitespace-stripped** sequence. The runner
validates length and `tss_index` bounds locally before any call.

Expression responses echo the windowing: `meta.task_specific_counts.tss_index` /
`.scored_window`, and `data.input.tss_index` / `.scored_window` /
`.submitted_sequence_length`. Note `data.input.sequence_length` is the **scored**
length (always 9,198), not what you submitted.

## Response envelope

Success is `200` with a `{data, meta}` envelope. `data.summary` carries the
headline scalars; `data` also carries the per-item arrays (`regions`, `sites`,
`transcripts`) or `prediction` (expression). `meta` carries `model`,
`request_id`, and timing. Exact fields per task: `references/tasks.md`.

## Async (annotation)

`annotation` runs asynchronously:

1. `POST …/tasks/annotation/predict` with header `Prefer: respond-async` → `202`
   with `data.job_id`.
2. Poll `GET …/tasks/jobs/{job_id}` — `202` while running (optional
   `data.progress`), `200` with the final `{data, meta}` when done.

`scripts/gi_predict.py` handles the submit/poll loop (2 s interval, 30-min cap)
and streams progress to stderr — no extra flags.

## Error envelope

Non-2xx responses carry:

```json
{ "error": { "code": "…", "message": "…", "request_id": "…", "details": {} } }
```

Common: `401/403` (auth), `422` (bad body/model/options), `429` (rate limit),
`504 upstream_timeout` (large sync request on a cold GPU). More:
`references/errors.md`.

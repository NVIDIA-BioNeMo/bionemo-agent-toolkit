# API reference — the /v1 contract

Genomic Intelligence exposes one versioned REST contract; all six tasks share
the same request/response shape. Authoritative, live schema:
<https://api.genomicintelligence.ai/v1/openapi.json> (human view:
<https://api.genomicintelligence.ai/redoc>). This file is a point-in-time
snapshot — if it disagrees with the OpenAPI doc, the OpenAPI doc wins.

## Endpoints

```
POST https://api.genomicintelligence.ai/v1/tasks/{task}/predict
     task ∈ { promoter, splice, enhancer, chromatin, expression, annotation }
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

Length bounds are per-task (see `references/tasks.md`): 1–500,000 bp for all
tasks except `expression`, which requires **exactly 9,198 bp** centred on a TSS.
The runner validates length locally before any call.

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

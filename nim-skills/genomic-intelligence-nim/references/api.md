# API reference — the /v1 contract

Genomic Intelligence exposes one versioned REST contract. Each task is its own
published operation with its own request schema — the shared `PredictRequest` is
gone. Authoritative, live schema:
<https://api.genomicintelligence.ai/v1/openapi.json> (human view:
<https://api.genomicintelligence.ai/redoc>). This file is a point-in-time
snapshot — if it disagrees with the OpenAPI doc, the OpenAPI doc wins.

## Endpoints

The document publishes eleven operations. The six predict paths are literal, one
per task — the URLs are byte-identical to what callers already send, so no client
URL construction changes:

```
POST https://api.genomicintelligence.ai/v1/tasks/promoter/predict     # PromoterPredictRequest
POST https://api.genomicintelligence.ai/v1/tasks/splice/predict       # SplicePredictRequest
POST https://api.genomicintelligence.ai/v1/tasks/enhancer/predict     # EnhancerPredictRequest
POST https://api.genomicintelligence.ai/v1/tasks/chromatin/predict    # ChromatinPredictRequest
POST https://api.genomicintelligence.ai/v1/tasks/annotation/predict   # AnnotationPredictRequest
POST https://api.genomicintelligence.ai/v1/tasks/expression/predict   # ExpressionPredictRequest
POST https://api.genomicintelligence.ai/v1/workflows/find-genes-and-predict-expression
GET  https://api.genomicintelligence.ai/v1/tasks/jobs                 # list async jobs
GET  https://api.genomicintelligence.ai/v1/tasks/jobs/{job_id}        # poll an async job
GET  https://api.genomicintelligence.ai/v1/tasks/{task}/models        # model registry
GET  https://api.genomicintelligence.ai/health                        # public
```

An unrecognised task segment is `404 not_found` (`"Unknown task: bogus"`), not a
`422`.

- Base URL overridable via `GI_BASE_URL`.
- Auth: `Authorization: Bearer $GI_API_KEY` (partner key, prefix `gi_`) on every
  `/v1/*` route, including `GET /v1/tasks/{task}/models`.
- `Content-Type: application/json`, `Accept: application/json`.

`GET /v1/tasks/{task}/models` is **not** the `{data, meta}` envelope — it returns
a flat `{task, default_model, models: [{id, name, description, is_default,
bio_spec}]}`.

## Request body

Every request model is `additionalProperties: false`, as is every `options`
object, so an unknown key is a hard `422 validation_failed` with
`type: "extra_forbidden"` — never silently ignored.

```json
{
  "sequence": "ACGT…",           // required; A/C/G/T(/N); per-task minLength
  "sequence_name": "TP53",        // optional label echoed back (max 128 chars)
  "model": "g0-promoter-2000bp",  // optional; omit for the task default
  "options": { "threshold": 0.5 } // task-specific, closed; see below
}
```

`options` per task (all closed):

| Task | `options` keys |
|---|---|
| promoter | `threshold` (0–1, default 0.5) |
| splice | `threshold` (0–1, default 0.5), `site_types` (subset of `["donor","acceptor"]`, default both) |
| enhancer | *(none)* |
| chromatin | `threshold` (0–1, default 0.5) |
| annotation | `batch_size` (1–128, default 8), `shift_coordinates`, `reverse_complement` (default true) |
| expression | `description` — **required**, and the only key |
| composite | `description`, `annotation_model`, `expression_model`, `batch_size`, `shift_coordinates` |

`expression` additionally requires `options` itself and takes a fifth field:

```json
{
  "sequence": "ACGT…",                        // required, 9,198–500,000 bp
  "options": { "description": "K562 cells" }, // required
  "tss_index": 12345,                         // required unless len == 9198
  "sequence_name": "HBB",
  "model": "…"
}
```

Length bounds are per-task, published as `minLength`/`maxLength` on each request
schema and enforced before any model loads (see `references/tasks.md`): promoter
300, splice 100, enhancer 50, chromatin 200, annotation 1,000, expression 9,198,
composite 1,000 — all capped at 500,000 bp. Under the floor and over the cap are
both `422 validation_failed` at `loc ["body","sequence"]`; over-length is **not**
a `413`. The floor is admission control, not regime: a request above the floor
but below the model's `bio_spec.context_window_bp` is accepted and scored against
a padded window.

Lengths and `tss_index` are measured on the **whitespace-stripped** sequence, so a
line-wrapped FASTA body pastes verbatim (a `>` header line still fails the
alphabet check). The runner validates length and `tss_index` bounds locally
before any call — those local constants are a mirror of
`gpu_service/core/limits.py`, which is published as `minLength`; the served
schema wins.

## `bio_spec` (from `GET /v1/tasks/{task}/models`)

- `request_max_bp` — the enforced ceiling (500,000 for every model).
- `context_window_bp` — the model's own sliding window in bp; `null` for
  annotation and expression. Live: promoter `g0-promoter-2000bp` 2,000 (the
  300 bp promoter models 300), splice 15,000, enhancer 249, chromatin 1,000.
- `trained_window_bp` — fixed receptive field; 9,198 for `g0-expression`, `null`
  for sliding-window models.

There is no `strand_sensitive` flag. The splice model is strand-specific in
practice — feed transcript orientation.

Expression responses echo the windowing: `meta.task_specific_counts.tss_index` /
`.scored_window`, and `data.input.tss_index` / `.scored_window` /
`.submitted_sequence_length`. Note `data.input.sequence_length` is the **scored**
length (always 9,198), not what you submitted.

## Response envelope

Success is `200` with a `{data, meta}` envelope. `data.summary` carries the
headline scalars; `data` also carries the per-item arrays (`regions`, `sites`,
`transcripts`) or `prediction` (expression). `meta` carries `model`,
`request_id`, and timing. Exact fields per task: `references/tasks.md`.

## Async (annotation, and any predict operation)

`Prefer` is a declared header parameter on all six predict operations and on the
composite — any of them can be run async, not just `annotation`:

1. `POST …/tasks/annotation/predict` with header `Prefer: respond-async` → `202`
   with `{data: {job_id, status: "accepted", links}, meta}` (the same
   `{data, meta}` envelope as a sync `200`). The job id is also in the
   `Content-Location` and `X-Job-Id` response headers.
2. Poll `GET …/tasks/jobs/{job_id}` — `202` while running (`{data: {job_id,
   status, progress}, meta}`), `200` with the final `{data, meta}` when done.

Async is JSON-only: a text `format` combined with `Prefer: respond-async` is
rejected.

`scripts/gi_predict.py` handles the submit/poll loop (2 s interval, 30-min cap)
and streams progress to stderr — no extra flags.

## Error envelope

Non-2xx responses carry:

```json
{ "error": { "code": "…", "message": "…", "request_id": "…", "details": … } }
```

`error.code` is a closed 21-value enum: `bad_request`, `unauthorized`,
`forbidden`, `not_found`, `conflict`, `job_expired`, `payload_too_large`,
`sync_too_large`, `unsupported_format`, `validation_failed`,
`too_many_requests`, `rate_limited`, `internal_error`, `timeout`,
`insufficient_memory`, `model_not_found`, `task_not_supported_by_model`,
`model_loading`, `service_unavailable`, `http_error`, `unknown`. The schema tells
clients to treat an unlisted value as a generic failure, not a parse error.

Switch on `code` first, then read `details` — `details` is keyed on the sibling
`code` and matches the declared schema: `validation_failed` carries the
`ValidationFailedDetails` object `{errors: [{loc, msg, type}, …]}`. Read it
defensively and never make control flow depend on its shape.

`error.request_id` mirrors the `X-Request-Id` response header, and both are set
on every response — error envelopes (including `413 sync_too_large`) and success
envelopes, where it lives at `meta.request_id`. Every response carries
`RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` and
`RateLimit-Policy`; a `429` adds `Retry-After`.

Common: `401/403` (auth), `422 validation_failed` (bad body/length/model/options
— including over-length sequence), `429` (rate limit), `413 payload_too_large`
(raw body over 16 MiB), `415 unsupported_format` (an unsupported `format` query
value — never a silent fallback to JSON), `504 timeout` (large sync
request on a cold GPU). More: `references/errors.md`.

Per-task `format` values: promoter `json|bed|bedgraph`, splice `json|bed|gff3`,
enhancer `json|bedgraph`, chromatin `json|bed`, annotation `json|bed|gff3`,
expression JSON only. Text formats are synchronous-only.

## Composite: find genes, then predict expression

```
POST /v1/workflows/find-genes-and-predict-expression
```

Request `FindGenesAndPredictExpressionRequest`: `sequence` 1,000–500,000 bp and
`options` are both required, and `options.description` (cell type / assay
context) is required too — enforced at runtime rather than marked `required` in
`FindGenesAndPredictExpressionOptions`, so a missing or empty value is a
`422 validation_failed` with the message *"options.description is required (cell
type / assay context)"*. Send it.

It annotates the sequence, centres a 9,198 bp window on each discovered gene's
TSS (padding with `N` up to half the window rather than dropping an edge gene),
and returns an expression prediction per gene. `meta.task_specific_counts` is
`{genes_found, genes_predicted, genes_skipped}` with
`genes_predicted + genes_skipped == genes_found`; per-gene causes are in
`data.expression_predictions[].skip_reason`.

Above **50,000 bp** the composite forces async: a synchronous request over that
size is `413 sync_too_large` with `error.details = {sequence_length, threshold}`.
Retry the same body with `Prefer: respond-async`.

## Version note

Everything above is live on `api.genomicintelligence.ai`, which serves
gpu_service `2026.08.19.5`: the six literal predict operations, the typed
`options` objects, the per-task floors, the published composite, the `Prefer`
parameter, the `code` enum and the `bio_spec` fields. Check `info.version` in
`/v1/openapi.json` if a detail here does not match.

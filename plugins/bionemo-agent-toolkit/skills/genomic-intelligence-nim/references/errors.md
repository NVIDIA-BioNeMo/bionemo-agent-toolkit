# Errors, Async Polling & Limits

## Error envelope

Non-2xx responses carry a JSON `{error}` envelope, surfaced by the skill as
`API error: [<status> <code>] <message> (request_id=<id>)` on stderr (exit
code 2). The shape:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "human-readable explanation",
    "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "details": []
  }
}
```

Always quote the `request_id` when reporting an issue to Genomic Intelligence.
It mirrors the `X-Request-Id` response header, and both are set on every
response: error envelopes carry `error.request_id`, success envelopes carry
`meta.request_id`. Reading the header as a fallback remains sound practice.

`code` is a **closed 21-value enum**: `bad_request`, `unauthorized`, `forbidden`,
`not_found`, `conflict`, `job_expired`, `payload_too_large`, `sync_too_large`,
`unsupported_format`, `validation_failed`, `too_many_requests`, `rate_limited`,
`internal_error`, `timeout`, `insufficient_memory`, `model_not_found`,
`task_not_supported_by_model`, `model_loading`, `service_unavailable`,
`http_error`, `unknown`. The schema explicitly says to treat an unlisted value as
a generic failure, not a parse error.

**Branch on `code`, never on `details` or `loc`.** `details` is keyed on the
sibling `code` (`ValidationFailedDetails`, `TaskNotSupportedByModelDetails`,
`ModelNotFoundDetails`, `SyncTooLargeDetails`, `GenericDetails`, or null). A
validation failure carries the declared `{errors: [{loc, msg, type}, …]}`
object — the FastAPI error array wrapped under `errors`. Read it defensively
and keep control flow off it.

## Common status codes

| Status | `code` | Meaning | Action |
|---|---|---|---|
| 400 | `bad_request` | Malformed request | Read the message |
| 401 / 403 | `unauthorized` / `forbidden` | Missing / bad / revoked key | Re-check `GI_API_KEY` (see authentication.md) |
| 404 | `not_found` | **Unknown task** or unknown job id | Check the `--task` value (an unrecognised task is a 404, not a 422); a job may have expired |
| 410 | `job_expired` | Async job result no longer retained | Re-submit |
| 413 | `payload_too_large` | Raw request body over **16 MiB**, rejected before parsing | Split the input — this is the body cap, not the sequence cap |
| 413 | `sync_too_large` | Composite workflow called synchronously above 50,000 bp | Retry with `Prefer: respond-async`; `details` = `{sequence_length, threshold}` |
| 415 | `unsupported_format` | Unsupported `format` query value | Use a format the task supports — there is no silent fallback to JSON |
| 422 | `validation_failed` | Sequence under the task floor **or over the 500,000 bp cap**, out-of-range/missing `tss_index`, missing `options.description`, unknown body or `options` key | Read the message; fix the body |
| 429 | `rate_limited` / `too_many_requests` | Concurrency / rate cap exceeded | Back off (honour `Retry-After`); request a higher tier |
| 500 | `internal_error` | Server-side failure | Retry; if persistent, report with `request_id` |
| 503 | `service_unavailable` / `model_loading` | Backend transiently down or a model is loading | Retry with backoff |
| 504 | `timeout` | Large sync request on a cold GPU | Retry, or use a smaller sequence |

Note that a sequence **over** 500,000 bp is a `422 validation_failed`
(`"sequence is 520000 bp; the maximum is 500000 bp"`, `loc
["body","sequence"]`) — *not* a `413`. `413` means only the 16 MiB raw-body cap
or the composite's synchronous-delivery cap.

The skill validates length, the `expression` `--description`, and the
`--tss-index` bounds **before** any network call, so those failures (exit
code 1) never reach the API. Server-side, every expression contract violation
(sequence below 9,198 bp, missing/out-of-range `tss_index`, missing
`options.description`, unknown body field) is a `422 validation_failed`. There
is no opt-out flag, header, or query parameter; nothing is padded or clamped.
The `tss_index` checks come from a whole-model validator and report at
`loc: ["body"]`, never `body.tss_index`.

Every response — success or error — carries `RateLimit-Limit`,
`RateLimit-Remaining`, `RateLimit-Reset` and `RateLimit-Policy`; a `429` adds
`Retry-After`.

## Async polling (`annotation`)

The skill runs `annotation` asynchronously by default; the API accepts either
mode on every task (`Prefer: respond-async` is declared on all six predict
operations, and annotation returns `200` synchronously without it). The flow
inside `scripts/gi_predict.py`:

1. `POST /v1/tasks/annotation/predict` with header `Prefer: respond-async`
   → returns `202` with `data.job_id`.
2. Poll `GET /v1/tasks/jobs/{job_id}`:
   - `202` → still running; `data.progress` is streamed to stderr; sleep and re-poll.
   - `200` → terminal; the body is the final `{data, meta}` envelope.
   - other → raised as a `GIError`.

Defaults: poll every 2 s, give up after 30 min. Typical real latency is ~20 s
for a ~20 kb sequence (longer on a cold GPU).

## Limits

- **Max sequence length:** 500,000 bp for every task (over → `422`).
- **Minimum sequence length, per task:** promoter 300, splice 100, enhancer 50,
  chromatin 200, annotation 1,000, expression 9,198 bp. Under → `422`. The floor
  is admission control, not regime — see `references/tasks.md`.
- **Expression minimum:** 9,198 bp is also the width of the single TSS-centred
  window the model scores. Above that width, `tss_index` is required.
- **Raw request body:** 16 MiB, enforced before parsing (`413
  payload_too_large`).
- **Composite synchronous delivery:** 50,000 bp (`413 sync_too_large` above it).
- **Single record per request:** split multi-record FASTA and run per record.
- **Rate / concurrency:** per partner tier; `429` signals you have exceeded it.

Authoritative limits are published as `minLength`/`maxLength` on each task's
request schema in the live OpenAPI document at
<https://api.genomicintelligence.ai/v1/openapi.json>. Numbers repeated in this
skill are mirrors.

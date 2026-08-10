# Errors, Async Polling & Limits

## Error envelope

Non-2xx responses carry a JSON `{error}` envelope, surfaced by the skill as
`API error: [<status> <code>] <message> (request_id=<id>)` on stderr (exit
code 2). The shape:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "human-readable explanation",
    "request_id": "req_…",
    "details": { }
  }
}
```

Always quote the `request_id` when reporting an issue to Genomic Intelligence.

## Common status codes

| Status | `code` (typical) | Meaning | Action |
|---|---|---|---|
| 400 / 422 | `invalid_request` | Sequence or option rejected upstream | Read the message; check length and `--model`/`--description` |
| 401 / 403 | `unauthorized` | Missing / bad / revoked key | Re-check `GI_API_KEY` (see authentication.md) |
| 404 | `not_found` | Unknown task or job id | Check the `--task` value; job may have expired |
| 429 | `rate_limited` | Concurrency / rate cap exceeded | Back off and retry; request a higher tier |
| 500 | `internal_error` | Server-side failure | Retry; if persistent, report with `request_id` |
| 503 | `unavailable` | Backend transiently down | Retry with backoff |
| 504 | `upstream_timeout` | Large sync request on a cold GPU | Retry, or use a smaller sequence |

The skill validates length and the `expression` `--description` **before** any
network call, so those failures (exit code 1) never reach the API.

## Async polling (`annotation`)

`annotation` is async. The flow inside `scripts/gi_predict.py`:

1. `POST /v1/tasks/annotation/predict` with header `Prefer: respond-async`
   → returns `202` with `data.job_id`.
2. Poll `GET /v1/tasks/jobs/{job_id}`:
   - `202` → still running; `data.progress` is streamed to stderr; sleep and re-poll.
   - `200` → terminal; the body is the final `{data, meta}` envelope.
   - other → raised as a `GIError`.

Defaults: poll every 2 s, give up after 30 min. Typical real latency is ~20 s
for a ~20 kb sequence (longer on a cold GPU).

## Limits

- **Max sequence length:** 500,000 bp for all tasks except `expression`, which
  requires an exact 9,198 bp window.
- **Single record per request:** split multi-record FASTA and run per record.
- **Rate / concurrency:** per partner tier; `429` signals you have exceeded it.

Authoritative limits live in `gpu_service/core/limits.py` and the live OpenAPI
document at <https://api.genomicintelligence.ai/v1/openapi.json>.

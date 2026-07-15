# Authentication

Every `/v1/*` call requires a partner bearer key. The skill sends it as
`Authorization: Bearer <key>`. Public routes that need no key: `/health`,
`/docs`, `/redoc`, `/v1/openapi.json`.

## Setting the key

```bash
export GI_API_KEY=gi_yourkeyhere
```

Resolution order in `scripts/gi_client.py`:

1. Explicit `--api-key` CLI flag (highest precedence).
2. `GI_API_KEY` environment variable.
3. Otherwise: a `RuntimeError` with onboarding instructions and exit code 2.

Keys are bearer tokens beginning with `gi_`. Request one at
**contact@genomicintelligence.ai**.

## Base URL

Default: `https://api.genomicintelligence.ai`. Override for staging or a local
service:

```bash
export GI_BASE_URL=https://staging.example.internal
# or per-invocation:
python scripts/gi_predict.py --task promoter --demo --base-url http://localhost:8001
```

## Partner tiers

Keys are scoped to a partner tier with concurrency and rate limits. If you hit
`429`, you have exceeded your concurrency or per-minute cap — back off and
retry. Higher-throughput needs: ask Genomic Intelligence to raise your tier.

## Security notes

- Never commit a real key. Keep it in the environment or a secrets manager.
- The key authorizes billed inference. Treat it like a credential.
- The skill never writes the key into `report.md`, `result.json`, or the
  reproducibility bundle — only the request ID and base URL are recorded.

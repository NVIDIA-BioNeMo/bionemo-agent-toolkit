---
name: zao-embed
description: Generate 2048-dimensional molecular embeddings from SMILES using a subscribed ZAO SageMaker Marketplace endpoint. ZAO is a 4D molecular foundation model (multi-conformer 3D) from SyntheticGestalt. The endpoint does all preprocessing internally (SMILES standardization, nvmolkit GPU conformer generation, feature extraction, model forward pass); this skill only registers the endpoint, sends SMILES, and returns embeddings for use as drop-in features in any downstream ML model. Use for molecular featurization, virtual screening feature prep, or embedding extraction.
license: Apache-2.0 OR CC-BY-4.0
compatibility: Two modes. (1) AWS SageMaker (default) uses an AWS account subscribed to the ZAO SageMaker Model Package with a deployed endpoint, plus boto3 and IAM creds for sagemaker-runtime InvokeEndpoint (no GPU on the caller). (2) Local container mode hits a locally-running ZAO Marketplace container over HTTP, plus the requests package (needs a CUDA GPU on the host running the container). Designed for Claude Code, Codex, and Nemotron.
metadata:
  owner: zao@syntheticgestalt.com
  classification: workflow-skill
  risk_tier: skill
# Line/token budget: within the 500-line / 5000-token cap for skill files.
---

# zao-embed

Turn SMILES into ZAO's 2048-dimensional molecular embeddings by calling a customer-subscribed ZAO SageMaker Marketplace endpoint. The endpoint owns the full pipeline; this skill is a thin client: register the endpoint, batch the SMILES, invoke, parse embeddings, report failures.

## Prerequisites (no local compute)

- **Subscription**: an AWS account subscribed to the *ZAO - 4D Molecular Foundation Model* SageMaker Model Package on AWS Marketplace, with an endpoint already deployed (`ml.g6e.2xlarge` recommended). Deploying the endpoint is a one-time step the user does in their own account; this skill does not create or deploy endpoints.
- **Credentials**: IAM credentials on the caller (env, profile, or role) with `sagemaker-runtime:InvokeEndpoint`. Auth is AWS SigV4 -- there is no bearer token or API key.
- **Client deps**: `boto3` (and `numpy` if writing `.npz/.npy/.csv`). No GPU, no model download, no RDKit on the caller side.

## Register the endpoint

The caller reads the endpoint from environment variables so the user registers it once. Pick the mode the user has; ask them which if it is not already set.

**AWS SageMaker (default)** -- a subscribed, deployed Marketplace endpoint:

```bash
export ZAO_SAGEMAKER_ENDPOINT=<deployed-endpoint-name>
export AWS_REGION=<the-region-the-endpoint-runs-in>   # or rely on ~/.aws/config
```

The caller has no built-in region default: it uses your AWS environment / profile (`$AWS_REGION`, `$AWS_DEFAULT_REGION`, or `~/.aws/config`). Set `AWS_REGION` only if your profile does not already point at the endpoint's region. `--endpoint` / `--region` flags override the env vars per call.

**Local container** -- the same ZAO Marketplace container run locally (e.g. via Docker on a GPU host), reachable over HTTP on the `/invocations` route:

```bash
export ZAO_ENDPOINT_URL=http://localhost:8080/invocations
```

`--endpoint-url` overrides it per call. When `--endpoint-url` / `ZAO_ENDPOINT_URL` is set the caller POSTs directly to that URL (no AWS transport, no SigV4) and needs the `requests` package instead of boto3. The request/response contract is identical to the SageMaker path.

## Inputs

Required (one of):

- `--smiles <S> [<S> ...]` -- one or more SMILES on the command line, or
- `--smiles-file <path>` -- plain-text file, one SMILES per line (`#` comments and blank lines ignored), or
- SMILES piped on stdin (one per line).

Optional:

- `--out <path>` -- write results to `.npz` (smiles + embeddings matrix), `.npy` (matrix only), `.csv` (smiles + e0..e2047), or `.jsonl` (raw per-mol records). Omit to return embeddings inline in the JSON summary (small inputs only).
- `--batch-size N` -- SMILES per request (default 1000; keeps each request under the SageMaker 6 MB payload / 60 s response limits).
- `--endpoint` / `--region` -- override the env vars.

Valid input range: drug-like molecules, MW 100-1000 Da. Molecules outside the model's range or that fail standardization come back with a `null` embedding and an `error` string -- they do not fail the whole request.

## Workflow

Let `$SKILL` be this skill's directory.

1. **Confirm the endpoint is registered.** If neither `$ZAO_SAGEMAKER_ENDPOINT` (AWS) nor `$ZAO_ENDPOINT_URL` (local) is set and the user passed no `--endpoint` / `--endpoint-url`, ask the user for the endpoint before proceeding. Do not guess an endpoint name. Once the user gives it, `export` it (`export ZAO_SAGEMAKER_ENDPOINT=<name>` or `export ZAO_ENDPOINT_URL=<url>`) so every later call in this session reuses it without re-asking.

2. **Invoke the endpoint.**
   ```
   python3 $SKILL/../../scripts/invoke_endpoint.py \
       --smiles-file <user-file> \
       --out <run-dir>/embeddings.npz
   ```
   (or `--smiles ...` / stdin). The kernel batches, calls `sagemaker-runtime:InvokeEndpoint`, and prints a single JSON summary to stdout.

3. **Parse the JSON summary** and report to the user:
   - `n_input`, `n_embedded`, `n_failed`, `embedding_dim` (expect 2048),
   - `output` path (if `--out` was given), and
   - `failed_smiles[]` -- surface these so the user sees which molecules were out of range / unparseable.

   Abort and surface the message if the summary is `{"ok": false, ...}`.

## Output

- `.npz`: `np.load(path, allow_pickle=True)` -> `smiles` (object array) and `embeddings` (`(N, 2048)` float32; failed rows are all-NaN, aligned by index).
- The embeddings are drop-in features for any downstream model (CatBoost, XGBoost, scikit-learn, a NN). To go straight to ADMET / activity predictions, hand off to the `zao-predict` skill.

## Hard rules

- **Never create, deploy, modify, or delete the SageMaker endpoint.** This skill only calls an endpoint the user already deployed. Endpoint lifecycle is the user's responsibility (and incurs their AWS charges).
- **Do not print AWS credentials.** Rely on the standard boto3 credential chain.
- **Do not fall back to any local model.** If the endpoint is unreachable, report the error; there is no CPU/GPU fallback path on the caller side.
- **Preserve input order.** The response is index-aligned to the input; keep failed rows in place (NaN) rather than dropping them.

## Common errors

- `no endpoint: ... set ZAO_SAGEMAKER_ENDPOINT` -> register the endpoint name.
- `no AWS region configured` -> set `AWS_REGION`, add a region to `~/.aws/config`, or pass `--region` (the region where the endpoint is deployed).
- `ValidationError ... Endpoint ... not found` -> the name is wrong or the endpoint is not deployed / not `InService` in this region.
- `AccessDeniedException` -> the IAM identity lacks `sagemaker-runtime:InvokeEndpoint` on this endpoint.
- `ModelError` / 60 s timeout -> the batch was too large or a molecule was pathological; lower `--batch-size`.
- All rows `null` with `error` -> molecules outside MW 100-1000 Da or invalid SMILES; check the `failed_smiles[]` list.

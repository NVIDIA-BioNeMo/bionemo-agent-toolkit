---
name: zao-predict
description: Predict molecular properties or activities (ADMET, binding, toxicity, solubility, etc.) from SMILES by using ZAO embeddings as features for a downstream CatBoost model. Featurization runs on a subscribed ZAO SageMaker Marketplace endpoint; this skill trains CatBoost on the user's labeled data and predicts on query molecules, matching the ZAO TDC ADMET benchmark pipeline (random_strength=2, seed=42, Logloss/MAE). Use to build a property/activity predictor from a labeled CSV, or to score new molecules with a model trained earlier.
license: Apache-2.0 OR CC-BY-4.0
compatibility: Requires an AWS account subscribed to the ZAO SageMaker Model Package with a deployed endpoint, IAM credentials with sagemaker-runtime:InvokeEndpoint, and client-side Python deps boto3, numpy, pandas, catboost. No GPU needed on the caller side. Designed for Claude Code, Codex, and Nemotron.
metadata:
  owner: zao@syntheticgestalt.com
  classification: workflow-skill
  risk_tier: skill
# Line/token budget: within the 500-line / 5000-token cap for skill files.
---

# zao-predict

Build a molecular property/activity predictor on top of ZAO. The endpoint turns SMILES into 2048-dim embeddings; this skill trains a downstream CatBoost model on the user's labels and predicts on new molecules. This reproduces the ZAO benchmark recipe (embedding + CatBoost) that ranks #1 on several TDC ADMET tasks.

## When to use vs zao-embed

- `zao-embed` -> you just want the embedding vectors (you bring your own model).
- `zao-predict` -> you have a labeled CSV and want predictions end-to-end, or you already trained a model here and want to score new molecules.

## Prerequisites

- A ZAO endpoint registered as in `zao-embed` -- either a deployed SageMaker Marketplace endpoint (`ZAO_SAGEMAKER_ENDPOINT` + `AWS_REGION`) or a local ZAO container (`ZAO_ENDPOINT_URL`). `invoke_endpoint.py` handles both.
- Client-side deps: `boto3`, `numpy`, `pandas`, `catboost`. No GPU on the caller.

## Inputs

Train + predict (the common case):

- **Labeled CSV** -- a SMILES column (`--smiles-col`, default `smiles`) and a label column (`--label-col`). Labels are `{0,1}` for classification or real numbers for regression (auto-detected; force with `--task`).
- **Query SMILES** -- a plain-text file (or `--smiles`) of molecules to score.

Predict-only (reuse an earlier model):

- A `model.cbm` + its `model.cbm.meta.json` sidecar from a prior run, and query SMILES.

## Workflow

Let `$SKILL` be this skill's directory and `$S=$SKILL/../../scripts`. Work in a fresh run directory `$RUN` (e.g. `runs/predict_<UTC-timestamp>/`).

1. **Confirm the endpoint is registered** (as in `zao-embed`). If neither `$ZAO_SAGEMAKER_ENDPOINT` nor `$ZAO_ENDPOINT_URL` is set, ask the user, then `export` it. This skill calls `invoke_endpoint.py` twice (train + query), so exporting once avoids re-asking on the second call.

2. **Embed the training molecules.** Extract the SMILES column from the labeled CSV to a text file first (one per line), then:
   ```
   python3 $S/invoke_endpoint.py --smiles-file $RUN/train_smiles.txt --out $RUN/train_emb.npz
   ```
   Surface `n_failed` / `failed_smiles[]` from the summary.

3. **Train CatBoost.**
   ```
   python3 $S/train_catboost.py \
       --embeddings $RUN/train_emb.npz \
       --labels <labeled-csv> --smiles-col smiles --label-col <Y> \
       --out $RUN/model.cbm
   ```
   Parse the JSON summary: report `task` (classification/regression), `n_train`, `n_dropped` (rows with no/failed embedding or missing label), and the label stats/counts. The model and its `.meta.json` sidecar land in `$RUN`.

4. **Embed the query molecules.**
   ```
   python3 $S/invoke_endpoint.py --smiles-file <query.txt> --out $RUN/query_emb.npz
   ```

5. **Predict.**
   ```
   python3 $S/predict_catboost.py \
       --model $RUN/model.cbm --embeddings $RUN/query_emb.npz \
       --out $RUN/predictions.csv
   ```

6. **Report to the user.** From the predict summary: `output` CSV path, `n_predicted`, `n_skipped_failed_embedding`, and the task type. The CSV has `smiles`, `y_pred`, and (classification only) `y_prob`; failed-embedding rows are kept with NaN so the output stays index-aligned to the query input.

Predict-only: skip steps 2-3 and pass an existing `--model`.

## Defaults

CatBoost hyperparameters come from `config/defaults_predict.json` (`random_strength=2`, `random_seed=42`; Logloss for classification, MAE for regression) -- the exact ZAO `catboost_default` recipe. Override per run with `--random-strength` / `--random-seed`.

## Hard rules

- **Never create, deploy, modify, or delete the SageMaker endpoint.** Only call the user's already-deployed endpoint.
- **Do not fabricate labels or predictions.** Only train on the labels the user supplies; every prediction must come from the trained model.
- **Keep predictions index-aligned to the query input.** Do not drop failed-embedding rows; emit NaN for them and report the count.
- **One label column per model.** For a multi-task CSV, train one model per `--label-col` and say so to the user.
- **Do not print AWS credentials.** Rely on the boto3 credential chain.

## Common errors

- `no rows left after aligning labels to embeddings` -> the labels CSV SMILES do not match the embedded SMILES (canonicalization differs), or all training embeddings failed. Check `failed_smiles[]` from step 2 and the SMILES column.
- `embedding dim ... != model's ...` -> the query embeddings came from a different model/endpoint than the training embeddings.
- `model sidecar meta not found` -> predict needs `model.cbm.meta.json`; keep it next to the model file.
- `catboost required` -> `pip install catboost` on the caller.

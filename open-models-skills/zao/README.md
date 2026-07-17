# ZAO agent skills

Agent-ready skills for **ZAO**, a 4D molecular foundation model from SyntheticGestalt. ZAO turns SMILES into 2048-dimensional molecular embeddings by processing multiple 3D conformers per molecule, capturing spatial arrangement and conformational flexibility that 1D/2D representations miss. The embeddings are drop-in features for downstream property/activity models.

These skills are tool-agnostic Markdown files; the scripts they call are deterministic kernels that can also be run directly without an agent.

## Audience: who should read what

- **If you are a user:** install the skills once (see [Installing the skills](#installing-the-skills)), subscribe to the ZAO Marketplace model and deploy an endpoint in your own cloud account, then ask your agent (Claude Code, Codex, Nemotron, etc.) by name, e.g. *"use zao-embed to featurize these SMILES"* or *"use zao-predict to train an ADMET model on this labeled CSV."* The agent reads the relevant `SKILL.md` and drives the rest.
- **If you are an agent:** read the `skills/<skill-name>/SKILL.md` for the workflow the user asked for, plus the endpoint-registration notes below.

## Endpoint-first (no local model)

Unlike self-hosted skills, these do **not** run the model on the caller. ZAO is distributed as a managed endpoint on a cloud marketplace: the user subscribes to the model, deploys an endpoint in their own account, and the skill calls that endpoint. All preprocessing (SMILES standardization, GPU conformer generation, feature extraction, model forward pass) happens **inside the endpoint container** — the caller only sends SMILES and receives embeddings.

Two deployment modes are supported, with the same request/response contract:

- **AWS SageMaker (default)** — a subscribed *ZAO* SageMaker Model Package deployed as a real-time endpoint. Auth is AWS SigV4 (the caller's IAM credentials); there is no bearer token.
- **Local container** — the same ZAO Marketplace container run locally on a GPU host, reachable over HTTP. Selected by setting `ZAO_ENDPOINT_URL`.

## Skills

| Skill | What the user provides | What it does |
|---|---|---|
| [`zao-embed`](skills/zao-embed/SKILL.md) | SMILES (CLI / file / stdin) | Calls the endpoint and returns 2048-dim embeddings (`.npz/.npy/.csv/.jsonl`). Failed molecules come back with a `null` embedding + error, index-aligned. |
| [`zao-predict`](skills/zao-predict/SKILL.md) | A labeled CSV + query SMILES | Embeds via the endpoint, trains a downstream CatBoost model on the user's labels, and predicts on query molecules. Reproduces ZAO's benchmark recipe (embedding + CatBoost). |

`zao-predict` composes `zao-embed`'s caller: it embeds the training set, trains, embeds the query set, and predicts.

## Register the endpoint

The caller reads the endpoint from environment variables so the user registers it once per session. There is no built-in region default; the region resolves from your AWS environment/profile.

```bash
# AWS SageMaker (default)
export ZAO_SAGEMAKER_ENDPOINT=<deployed-endpoint-name>
export AWS_REGION=<region>            # or rely on ~/.aws/config

# OR local container
export ZAO_ENDPOINT_URL=http://localhost:8080/invocations
```

If nothing is set, the agent asks for the endpoint on first use and exports it so later calls in the session reuse it.

## Requirements per skill

| Skill | Caller-side deps | Notes |
|---|---|---|
| `zao-embed` | `boto3` (SageMaker) or `requests` (local); `numpy` for `.npz/.npy/.csv` output | No GPU on the caller. The endpoint host needs a CUDA GPU. |
| `zao-predict` | above + `numpy`, `pandas`, `catboost` | Training/inference of the downstream CatBoost model runs on the caller (CPU is fine). |

## Installing the skills

The skills follow the [agentskills.io](https://agentskills.io) spec: each skill is a directory under [`skills/`](skills/) containing a `SKILL.md`. Primary target agents are **Claude Code**, **Codex**, and **Nemotron**.

```bash
# via the skills CLI (interactive)
npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit

# or, for Claude Code, symlink each skill from a repo checkout
for d in open-models-skills/zao/skills/zao-*/; do
  ln -sfn "$(realpath "$d")" ~/.claude/skills/"$(basename "$d")"
done
```

## Scripts (kernels)

Deterministic logic lives under [`scripts/`](scripts/). Each prints a structured JSON summary the calling skill consumes.

| Script | Purpose |
|---|---|
| `invoke_endpoint.py` | Send SMILES to the ZAO endpoint (SageMaker or local) and collect embeddings |
| `train_catboost.py` | Train a downstream CatBoost model on embeddings + user labels |
| `predict_catboost.py` | Predict with a trained CatBoost model on query embeddings |

Hyperparameter defaults for the downstream model live in [`config/defaults_predict.json`](config/defaults_predict.json) (`random_strength=2`, `random_seed=42`; Logloss for classification, MAE for regression) — the ZAO benchmark recipe. Override with the corresponding `--<name>` flag.

## Tests

[`tests/test_skill_frontmatter.py`](tests/test_skill_frontmatter.py) checks that every `SKILL.md` conforms to the agentskills.io spec and the project's metadata requirements. Run with `pytest tests/`.

## License

Source code is Apache-2.0; skills and documentation are CC-BY-4.0.

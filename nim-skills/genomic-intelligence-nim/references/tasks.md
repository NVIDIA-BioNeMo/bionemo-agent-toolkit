# Tasks Reference

The Genomic Intelligence `/v1` API exposes six DNA-sequence tasks. Each is its
own published operation — `POST /v1/tasks/promoter/predict`,
`/v1/tasks/splice/predict`, … — with its own request schema, its own minimum
length, and its own closed `options` object. There is no longer a shared
`PredictRequest`. The URLs are unchanged; only the schemas are per-task. Each
returns a `{data, meta}` envelope. This skill's `scripts/gi_predict.py --task
<task>` selects the endpoint; the table below documents what differs per task.

Source of truth for bounds and models: `gpu_service/core/limits.py` (one constant
per task) and `gpu_service/config/models.yaml`, published as `minLength` on each
request schema in the live OpenAPI doc at
<https://api.genomicintelligence.ai/v1/openapi.json>. The numbers below and in
`scripts/gi_predict.py` are **mirrors** — if they disagree with the served
schema, the served schema wins.

## Summary

| Task | Default model | Mode | Accepted length | Model context window | Demo fixture |
|---|---|---|---|---|---|
| promoter | `g0-promoter-2000bp` | sync | 300–500,000 bp | 2,000 bp | `promoter_tp53.fa` |
| splice | `g0-splice-bigbird` | sync | 100–500,000 bp | 15,000 bp | `splice_hbb.fa` |
| enhancer | `g0-deepstarr` | sync | 50–500,000 bp | 249 bp | `enhancer_eve.fa` |
| chromatin | `g0-deepsea` | sync | 200–500,000 bp | 1,000 bp | `chromatin_active_promoter_chr19.fa` |
| expression | `g0-expression` | sync | **9,198–500,000 bp** | 9,198 bp (fixed) | `expression_hbb_k562.fa` |
| annotation | `g0-annotation` | **async** | 1,000–500,000 bp | n/a | `annotation_tp53.fa` |

There are no per-model floors: a task's minimum is the strictest its models need,
and every model stays listed and loadable.

**Floor ≠ regime.** The minimum is admission control, enforced at request
validation before any model loads. A request above the floor but shorter than the
selected model's `bio_spec.context_window_bp` is **accepted and scored** — against
a window padded out to the context window. Enhancer is the sharp case: the bound
is 50 bp but `g0-deepstarr`'s context window is 249 bp, so 50–248 bp is scored
mostly on padding. Compare your length against `context_window_bp` (from
`GET /v1/tasks/{task}/models`) to know whether the model saw real sequence.
Longer-than-context input is fine — the scanner steps a prediction window at a
time and pads only the final partial window.

Under the floor and over the 500,000 bp cap are both `422 validation_failed` at
`loc ["body","sequence"]` — over-length is **not** a `413`. All lengths are
measured after whitespace is stripped.

To list the models available for a task and pass a non-default one, use
`--model <id>`. The model registry is the single source of truth; do not invent
model IDs.

## `options` per task

Every `options` object is closed (`additionalProperties: false`); an unknown key
is a hard `422 validation_failed` (`type: "extra_forbidden"`,
`loc: ["body","options","<key>"]`), never ignored.

| Task | Keys |
|---|---|
| promoter | `threshold` (0–1, default 0.5) |
| splice | `threshold` (0–1, default 0.5), `site_types` (subset of `["donor","acceptor"]`, default both) |
| enhancer | *(none)* |
| chromatin | `threshold` (0–1, default 0.5) |
| annotation | `batch_size` (1–128, default 8), `shift_coordinates`, `reverse_complement` (default true) |
| expression | `description` — **required**, and the only key |

`--description` therefore applies to `expression` only; the runner drops it (with
a warning) on any other task rather than letting the server 422.

## promoter

Predicts promoter regions over a sliding window. `data.summary` reports
`promoter_windows` / `total_windows`; `data.regions` lists windows with
`name`, `start`, `end`, `score`, and `strand`. Output also available as BED /
bedGraph via the API directly.

Non-human models exist (Drosophila, yeast, Arabidopsis) — pass `--model`. The
default `g0-promoter-2000bp` targets human/mammalian sequence.

## splice

Predicts splice **donor** and **acceptor** sites. `data.sites` lists each site
with `name`, `start`, `end`, `site_type` (donor/acceptor), `score`, and
`strand`. Default model `g0-splice-bigbird` (BigBird long-context). Good demo: a
gene with known introns (the bundled `splice_hbb.fa` is HBB).

## enhancer

Scores enhancer activity. The default `g0-deepstarr` (DeepSTARR) reports
**developmental** and **housekeeping** enhancer scores —
`summary.dev_score_max` / `summary.hk_score_max` per window. DeepSTARR is a
*Drosophila* model; the bundled demo (`enhancer_eve.fa`, the eve locus) reflects
that. Use the appropriate model for your organism.

The 50 bp floor is `g0-deepstarr`'s admission gate (the `dnabert-deepstarr`
alternative tolerates 16 bp, but the task floor is the strictest one). It is not
a biologically meaningful range: the model's `context_window_bp` is 249, so a
50–248 bp request is accepted and scored against a padded 249 bp window. Submit
at least 249 bp if you want the score to reflect real sequence.

## chromatin

Annotates chromatin state across a large panel of tracks (histone marks, DNase,
ATAC, TF binding) — the default `g0-deepsea` (DeepSEA) covers hundreds of
features. `summary.total_annotations` is the headline; the full per-track matrix
is in `data`. Output also available as BED via the API.

## expression

Predicts gene expression as **log(TPM+1)** from a fixed window. Its published
operation is `POST /v1/tasks/expression/predict` with schema
`ExpressionPredictRequest`, which — unlike the other five — requires `options` as
well as `sequence`. Three requirements the skill enforces locally:

1. **9,198–500,000 bp.** The model always scores exactly one 9,198 bp window
   **centred on the TSS** (2 × 4,599) — `sequence[tss_index-4599 :
   tss_index+4599]` — but the endpoint accepts up to 500 kb and slices for you.
   Below 9,198 bp is rejected; nothing is padded or truncated.
2. **`tss_index`** (`--tss-index`) — the 0-based TSS offset into the
   **whitespace-stripped** sequence. Required unless the sequence is exactly
   9,198 bp, where it defaults to 4,599 (the only legal value there). Bounds:
   `4599 ≤ tss_index ≤ len(sequence) − 4599`. The endpoint does not find the TSS
   for you and does not reverse-complement — submit gene-sense sequence.
3. **`--description`** — a cell-type / assay context string (e.g. `"K562
   cells"`), passed as `options.description`. Required, and the only key
   `options` accepts on this task.

The server reports both `tss_index` violations — "required unless exactly
9,198 bp" and the range check — from a whole-model validator, so they arrive at
`loc: ["body"]`, **never** `body.tss_index`. Match on
`error.code == "validation_failed"`; use the message for display only, and never
branch on `loc`.

`data.prediction.expression_log_tpm` (and `expression_tpm`) hold the result.
`meta.task_specific_counts` carries `tss_index` and `scored_window`
(`[start, end]`, always 9,198 wide) — check it, because a `tss_index` that is in
range but wrong (e.g. counted over raw FASTA characters including newlines)
scores the wrong window and still returns `200`. `data.input.sequence_length` is
the **scored** 9,198; the length you submitted is
`data.input.submitted_sequence_length`.

## annotation

De-novo gene / transcript structure prediction — transcript intervals and
strand, no reference annotation needed. **The skill always runs it async**
(`Prefer: respond-async` is a declared header parameter on every predict
operation, so any task can be run this way; annotation is the one that needs it):
the skill submits with
`Prefer: respond-async`, receives a `job_id`, and polls
`GET /v1/tasks/jobs/{job_id}` until terminal (HTTP 200). Typical latency ~20 s
for ~20 kb; progress is streamed to stderr. `data.transcripts` lists each
predicted transcript with `name`, `start`, `end`, `strand`, and `score` (plus
structure fields: `length`, `tss_position`, `polya_position`, `transcript_type`,
`exons`, `introns`, `cds`).

## Composite: find genes, then predict expression

`POST /v1/workflows/find-genes-and-predict-expression` — "what genes are in this
region, and how are they expressed?". Request
`FindGenesAndPredictExpressionRequest`: `sequence` 1,000–500,000 bp and `options`
both required; send `options.description` (cell type / assay context) too — it is
enforced at runtime and a missing or empty value is a `422 validation_failed`.
Optional `annotation_model`, `expression_model`, `batch_size` (1–128, default 8),
`shift_coordinates`.

It annotates the sequence, cuts a TSS-centred 9,198 bp window per discovered gene
(padding with `N` up to half the window rather than dropping an edge gene — the
direct expression route refuses to pad at all), and returns a prediction per
gene. `meta.task_specific_counts` = `{genes_found, genes_predicted,
genes_skipped}` with `genes_predicted + genes_skipped == genes_found`; per-gene
causes in `data.expression_predictions[].skip_reason`.

Above **50,000 bp** it forces async: a synchronous request over that size is
`413 sync_too_large` with `error.details = {sequence_length, threshold}`. Retry
the same body with `Prefer: respond-async`.

`scripts/gi_predict.py` does not wrap this workflow; call it directly (see
`references/api.md`).

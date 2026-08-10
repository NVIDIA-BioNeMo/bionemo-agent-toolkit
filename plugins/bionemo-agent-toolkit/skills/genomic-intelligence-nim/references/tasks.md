# Tasks Reference

The Genomic Intelligence `/v1` API exposes six DNA-sequence tasks. All share the
same request shape — `POST /v1/tasks/{task}/predict` with a JSON body
`{sequence, sequence_name, model?, options?}` — and return a `{data, meta}`
envelope. This skill's `scripts/gi_predict.py --task <task>` selects the
endpoint; the table below documents what differs per task.

Source of truth for bounds and models: the live OpenAPI doc at
<https://api.genomicintelligence.ai/v1/openapi.json> and the public task
reference at <https://docs.genomicintelligence.ai/tasks>.

## Summary

| Task | Default architecture | Mode | Length | Demo fixture |
|---|---|---|---|---|
| promoter | sliding-window promoter caller | sync | 1–500,000 bp | `promoter_tp53.fa` |
| splice | BigBird long-context | sync | 1–500,000 bp | `splice_hbb.fa` |
| enhancer | DeepSTARR (*Drosophila* S2) | sync | 50–500,000 bp | `enhancer_eve.fa` |
| chromatin | DeepSEA multi-track | sync | 1–500,000 bp | `chromatin_active_promoter_chr19.fa` |
| expression | TSS-window expression regressor | sync | **exactly 9,198 bp** | `expression_hbb_k562.fa` |
| annotation | structure-aware gene finder | **async** | 1–500,000 bp | `annotation_tp53.fa` |

Default models resolve **server-side** — omit `--model` unless you need a
specific one. List a task's models with `GET /v1/tasks/{task}/models`; the
live registry is the single source of truth. Do not invent or hardcode model
IDs — they can be retired without notice.

## promoter

Predicts promoter regions over a sliding window. `data.summary` reports
`promoter_windows` / `total_windows`; `data.regions` lists windows with
`name`, `start`, `end`, `score`, and `strand`. Output also available as BED /
bedGraph via the API directly.

Non-human models exist (Drosophila, yeast, Arabidopsis) — pass `--model`. The
default promoter model targets human/mammalian sequence.

## splice

Predicts splice **donor** and **acceptor** sites. `data.sites` lists each site
with `name`, `start`, `end`, `site_type` (donor/acceptor), `score`, and
`strand`. The default splice model uses a BigBird long-context architecture.
Good demo: a
gene with known introns (the bundled `splice_hbb.fa` is HBB).

## enhancer

Scores enhancer activity. The default enhancer model (DeepSTARR) reports
**developmental** and **housekeeping** enhancer scores —
`summary.dev_score_max` / `summary.hk_score_max` per window. DeepSTARR is a
*Drosophila* model; the bundled demo (`enhancer_eve.fa`, the eve locus) reflects
that. Use the appropriate model for your organism.

## chromatin

Annotates chromatin state across a large panel of tracks (histone marks, DNase,
ATAC, TF binding) — the default chromatin model (DeepSEA architecture) covers hundreds of
features. `summary.total_annotations` is the headline; the full per-track matrix
is in `data`. Output also available as BED via the API.

## expression

Predicts gene expression as **log(TPM+1)** from a fixed window. Two
requirements the skill enforces locally:

1. **Exactly 9,198 bp** — the model takes a 9,198 bp window **centred on the
   TSS** (2 × 4,599). Other lengths are rejected before any API call.
2. **`--description`** — a cell-type / assay context string (e.g. `"K562
   cells"`), passed as `options.description`. Required.

`data.prediction.expression_log_tpm` (and `expression_tpm`) hold the result.

## annotation

De-novo gene / transcript structure prediction — transcript intervals and
strand, no reference annotation needed. **Async only**: the skill submits with
`Prefer: respond-async`, receives a `job_id`, and polls
`GET /v1/tasks/jobs/{job_id}` until terminal (HTTP 200). Typical latency ~20 s
for ~20 kb; progress is streamed to stderr. `data.transcripts` lists each
predicted transcript with `name`, `start`, `end`, `strand`, and `score` (plus
structure fields: `length`, `tss_position`, `polya_position`, `transcript_type`,
`exons`, `introns`, `cds`).

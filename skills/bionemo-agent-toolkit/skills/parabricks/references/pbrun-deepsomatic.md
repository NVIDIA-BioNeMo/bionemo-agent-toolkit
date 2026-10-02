# Parabricks deepsomatic

Confirm the supported tumor-normal or tumor-only design. Collect tumor reads,
normal reads where applicable, reference FASTA, output location, and required
model bundle. Establish sample roles explicitly, and ask about intervals or
candidate resources when needed. Validate model suitability for the assay as
well as reference compatibility; investigate model and sample-label errors.
Use this for somatic analysis, not germline DeepVariant. Sensitivity or
specificity claims require comparable validation data.

## Gotchas

Parabricks DeepSomatic `--gvcf` option actually produces both .g.vcf and .vcf files with the same name. Do not generate separate commands for gvcf and vcf outputs.

## DeepSomatic Option Mapping

Parabricks v4.7.0 documents DeepSomatic as the
Google counterpart with TensorRT-accelerated model inference.

| Google DeepSomatic option | `pbrun deepsomatic` equivalent | Notes |
| --- | --- | --- |
| `--reads_tumor` | `--in-tumor-bam` | Required tumor BAM/CRAM input. |
| `--reads_normal` | `--in-normal-bam` | Required normal BAM/CRAM input for paired mode. |
| `--make_examples_extra_args` for supported candidate/pileup/read controls | Matching explicit Parabricks flags such as `--vsc-*`, `--alt-aligned-pileup`, `--min-mapping-quality`, and `--channel-*` | Exposes many make-examples options as first-class flags. |
| Google DeepSomatic options not listed here | No direct equivalent | Not documented for this tool. |
| — | `--pb-model-file` | TensorRT model file input. |

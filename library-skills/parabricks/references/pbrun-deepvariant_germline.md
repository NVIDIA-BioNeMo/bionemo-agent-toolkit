# Parabricks deepvariant_germline

Establish whether the pipeline starts from FASTQ pairs or a supported prepared
alignment mode. Collect the reference, destination, model settings, and any
needed read groups, known-sites resources, or intervals. Validate the chosen
input mode and model against the assay; inspect read-group and model errors.
For calling alone, use [deepvariant](pbrun-deepvariant.md); for short-read
alignment alone, use [fq2bam](pbrun-fq2bam.md).

## BWA-MEM/GATK/DeepVariant Option Mapping

Parabricks v4.7.0 documents
this as an end-to-end pipeline with alignment, sorting, duplicate marking, and
DeepVariant calling.

| Baseline option | `pbrun deepvariant_germline` equivalent | Notes |
| --- | --- | --- |
| BWA-MEM/DeepVariant reference | `--ref` | Required reference FASTA path. |
| `bwa mem <read1> <read2>` | `--in-fq <read1> <read2>` | Paired FASTQ input. |
| GATK/Picard final sorted/marked BAM output | `--out-bam` | BAM after sorting/duplicate marking. |
| DeepVariant `--model_type` | `--mode`, `--use-wes-model`, or selected model file | The manual documents short-read, PacBio, and ONT modes plus WES/model-file controls. |
| DeepVariant `--proposed_variants` | `--proposed-variants` | Candidate/importer VCF input. |
| DeepVariant make-examples options | Matching explicit Parabricks flags such as `--vsc-*`, `--variant-caller`, `--min-*`, `--channel-*` | Exposes many make-examples options directly. |
| GATK/DeepVariant intervals | `--interval` or `--interval-file` | Separates inline intervals from interval files. |
| `--java-options`, DeepVariant/GATK engine flags not listed here | No direct equivalent | Not documented for this tool. |
| — | `--disable-use-window-selector-model`, `--enable-small-model` | Compatibility/model behavior controls. |

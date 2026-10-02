# Parabricks germline

Confirm a germline pipeline is intended. Collect FASTQ pairs or supported
aligned inputs, reference FASTA, and VCF or gVCF destination. Clarify read
groups for FASTQ, optional intervals and ploidy, and known-sites resources when
BQSR is requested; check read-group and known-sites errors. For prepared-read
calling alone, use [haplotypecaller](pbrun-haplotypecaller.md); for preprocessing
alone, use [fq2bam](pbrun-fq2bam.md). Tumor analysis belongs with somatic tools.

## BWA-MEM/GATK Germline Option Mapping

Parabricks v4.7.0 documents this as a pipeline
from FASTQ to VCF, so the CLI maps to BWA-MEM, SortSam, MarkDuplicates,
BaseRecalibrator, ApplyBQSR, and HaplotypeCaller rather than one upstream tool.

| Baseline option | `pbrun germline` equivalent | Notes |
| --- | --- | --- |
| BWA-MEM/GATK `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `bwa mem <read1> <read2>` | `--in-fq <read1> <read2>` | Paired FASTQ input; repeat for multiple read groups. |
| GATK/Picard `SortSam -O` / final pipeline output BAM | `--out-bam` | BAM after sorting/duplicate marking. |
| Skip GATK/Picard `MarkDuplicates` | `--no-markdups` | Returns sorted BAM without duplicate marking when supported. |
| GATK `HaplotypeCaller --output`, `-O` | `--out-variants` | VCF/gVCF output. |
| GATK `HaplotypeCaller --emit-ref-confidence GVCF` | `--gvcf` | Generate gVCF output. |
| GATK `HaplotypeCaller --sample-ploidy` | `--ploidy` | The manual documents haploid/diploid support where applicable. |
| GATK `HaplotypeCaller` annotation/output-mode/pruning controls | `--haplotypecaller-options` | Pass supported original HaplotypeCaller options as one string. |
| GATK `--intervals`, `-L` | `--interval` or `--interval-file` | Separates inline intervals from interval files. |
| GATK `--interval-padding`, `-ip` | `--interval-padding`, `-ip` | Same padding role. |
| `--java-options`, GATK engine/common flags | No direct equivalent | Not exposed as GATK engine controls by current Parabricks docs. |

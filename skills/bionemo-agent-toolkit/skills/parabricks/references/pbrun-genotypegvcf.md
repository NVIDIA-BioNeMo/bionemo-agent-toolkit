# Parabricks genotypegvcf

Establish the single-sample or cohort GVCF input layout, reference requirements,
output VCF, and relevant intervals. Multi-sample behavior and input-list formats
depend on the selected release. Resolve missing required indexes with
[indexgvcf](pbrun-indexgvcf.md), then inspect malformed-GVCF and missing-index
errors. FASTQ or alignment inputs need a read-level caller before this step.

## GenotypeGVCFs Option Mapping

Parabricks v4.7.0 documents this as an accelerated
GATK GenotypeGVCFs counterpart for converting one or more gVCF inputs to VCF.

| GATK option | `pbrun genotypegvcf` equivalent | Notes |
| --- | --- | --- |
| `--variant`, `-V` | `--in-gvcf` | Required input gVCF/gVCF.GZ. |
| `--output`, `-O` | `--out-vcf` | Required output VCF. |
| GATK intervals, annotation controls, cloud flags, `--arguments_file`, and Java options | No direct equivalent | Not documented for this tool. |

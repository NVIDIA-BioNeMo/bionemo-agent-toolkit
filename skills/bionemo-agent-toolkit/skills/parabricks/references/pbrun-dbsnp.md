# Parabricks dbsnp

Collect the input VCF, dbSNP resource VCF, destination VCF, and reference if
required. The variant and dbSNP files must use the same reference build. Ask
about intervals, compression, and indexing when relevant; check annotation
semantics in the selected version's documentation and inspect resource or
malformed-VCF errors. This operation annotates variants already called; reads
must first go through an appropriate variant caller.

## dbSNP Annotation Option Mapping

Parabricks v4.7.0 documents `dbsnp` as a VCF annotation tool using a dbSNP VCF
resource.

| Baseline option | `pbrun dbsnp` equivalent | Notes |
| --- | --- | --- |
| Input VCF | `--in-vcf` | Required input VCF. |
| dbSNP/resource VCF | `--in-dbsnp-file` | Required dbSNP VCF.GZ with tabix index. |
| Output annotated VCF | `--out-vcf` | Required output VCF. |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun dbsnp` flags. |
| GATK/BCFtools annotation flags not listed here | No direct equivalent | Not documented for this tool. |

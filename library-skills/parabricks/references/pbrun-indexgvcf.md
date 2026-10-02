# Parabricks indexgvcf

Collect the GVCF needing an index and identify its downstream consumer.
Verify where the selected release writes the index and that the destination
is writable and accessible to that consumer. Check for malformed GVCF input.
Ordinary VCF indexing is in scope only when explicitly documented by that
release. Genotyping itself belongs with [genotypegvcf](pbrun-genotypegvcf.md).

## IndexFeatureFile Option Mapping

Parabricks v4.7.0 documents `indexgvcf` as
creating a `.tbi` index by appending `.tbi` to the input GVCF filename.

| GATK option | `pbrun indexgvcf` equivalent | Notes |
| --- | --- | --- |
| `--input`, `-I` | `--input` | Required gVCF/gVCF.GZ input. |
| Implicit output index path | Implicit `.tbi` next to input | Docs state the output name is determined by appending `.tbi` to the input GVCF filename. |
| GATK output path override, cloud flags, `--arguments_file`, and Java options | No direct equivalent | Not documented for this tool. |

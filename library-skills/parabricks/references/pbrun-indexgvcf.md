# Parabricks indexgvcf

Collect the GVCF needing an index and identify its downstream consumer.
Verify where the selected release writes the index and that the destination
is writable and accessible to that consumer. Check for malformed GVCF input.
Ordinary VCF indexing is in scope only when explicitly documented by that
release. Genotyping itself belongs with [genotypegvcf](pbrun-genotypegvcf.md).

## IndexFeatureFile Option Mapping

Parabricks v4.7.0 documents `indexgvcf` as
creating a `.tbi` index by appending `.tbi` to the input GVCF filename.
For `sample.g.vcf.gz`, the index is `sample.g.vcf.gz.tbi` alongside the input.
If the input mount is read-only, stage a copy in a writable directory and pass
that copy to `--input`. Check for existing destination files before copying;
there is no documented `--out` override for redirecting only the index.

| GATK option | `pbrun indexgvcf` equivalent | Notes |
| --- | --- | --- |
| `--input`, `-I` | `--input` | Required gVCF/gVCF.GZ input. |
| Implicit output index path | Implicit `.tbi` next to input | Docs state the output name is determined by appending `.tbi` to the input GVCF filename. |
| GATK output path override, cloud flags, `--arguments_file`, and Java options | No direct equivalent | Not documented for this tool. |

## References

- Parabricks 4.7.0 manual: <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_indexgvcf.html>

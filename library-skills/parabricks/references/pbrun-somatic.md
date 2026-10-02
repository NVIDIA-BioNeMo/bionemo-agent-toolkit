# Parabricks somatic

Establish supported tumor-normal or tumor-only mode, sample names, and the
relationship between specimens. Collect supported FASTQ or alignment inputs,
reference FASTA, output location, and any required germline resource, panel
of normals, known-sites, or intervals. Check sample-label and read-group errors.
This is not an inherited-variant workflow. Requests for a specific standalone
caller should use [mutectcaller](pbrun-mutectcaller.md) or
[deepsomatic](pbrun-deepsomatic.md).

## Somatic Pipeline Option Mapping

Depending on the selected version and requested caller, the
baseline may include BWA-MEM/GATK preprocessing plus Mutect2-style calling or a
DeepSomatic-style caller. Treat this as a pipeline mapping, not a one-to-one
single-tool mapping.

| Baseline option | `pbrun somatic` equivalent | Notes |
| --- | --- | --- |
| Reference FASTA | `--ref` | Required reference FASTA path. |
| Tumor FASTQ inputs | Tumor FASTQ input flags documented for the selected version | Verify exact tumor FASTQ flag names before finalizing. |
| Normal FASTQ inputs | Normal FASTQ input flags documented for the selected version | Verify exact normal FASTQ flag names before finalizing. |
| Tumor BAM/CRAM input | Tumor BAM input flag documented for the selected version | Use prepared-alignment mode only when supported. |
| Normal BAM/CRAM input | Normal BAM input flag documented for the selected version | Use paired mode when required by the workflow. |
| Tumor sample name | Tumor sample-name flag documented for the selected version | Must match BAM read group sample names where applicable. |
| Normal sample name | Normal sample-name flag documented for the selected version | Must match BAM read group sample names where applicable. |
| BWA-MEM read group/options | Read group flags and `--bwa-options` where documented | Do not invent sample or read group values. |
| GATK/Picard duplicate metrics | `--out-duplicate-metrics` or selected metrics flag | Verify output support for the selected version. |
| Mutect2 `--germline-resource` | `--mutect-germline-resource` | Germline resource VCF when used. |
| Mutect2 `--panel-of-normals`, `--pon` | No direct `pbrun somatic` equivalent | Use a `mutectcaller` PON workflow with `prepon`/`postpon` when required. |
| Mutect2/DeepSomatic output VCF | `--out-vcf` | Output somatic VCF. |
| Intervals/regions | `--interval` or `--interval-file` | Separates inline intervals from interval files where documented. |
| Baseline options not listed here | No direct equivalent | Not documented for this tool. |
| — | End-to-end tumor/normal input-mode flags | Combines preprocessing and somatic calling stages. |
| — | `prepon`/`postpon` PON handoff flags | Parabricks-specific decomposition of PON processing. |
| — | GPU alignment/calling stream, queue, and memory controls | GPU runtime tuning. |
| — | Caller-specific TensorRT/model flags where documented | Model deployment differs from CPU/GATK or Google runtimes. |

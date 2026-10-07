# Parabricks mutectcaller

Confirm supported tumor-normal or tumor-only mode. Collect reference FASTA,
tumor alignment, normal alignment where applicable, VCF destination, and
explicit tumor and normal sample labels. Ask for the germline resource, panel
of normals, and intervals required by the chosen workflow; validate their
reference builds and inspect sample-label or resource errors. Use a germline
caller for inherited-variant analysis.

For a panel of normals in **4.7.0**, follow
[prepon](pbrun-prepon.md) for contig-header validation and the required `.pon`
resource. Pass the prepared **VCF.GZ** to `--pon`, then use
[postpon](pbrun-postpon.md) for PON INFO annotation of the caller's VCF.
A `.tbi` alone does not replace the preprocessing resource.

## Mutect2 Option Mapping

Parabricks v4.7.0 documents `mutectcaller` as the
accelerated GATK Mutect2 counterpart; the core tumor/normal flags map directly,
but common GATK engine and Java controls do not.

| GATK option | `pbrun mutectcaller` equivalent | Notes |
| --- | --- | --- |
| `--input`, `-I` for tumor | `--in-tumor-bam` | Tumor BAM/CRAM input. |
| `--input`, `-I` for normal | `--in-normal-bam` | Normal BAM/CRAM input when running paired mode. |
| `--tumor-sample` | `--tumor-name` | Must match the sample name in the BAM header. |
| `--normal-sample` | `--normal-name` | Must match the sample name in the normal BAM header. |
| `--output`, `-O` | `--out-vcf` | Output somatic VCF. |
| `--germline-resource` | `--mutect-germline-resource` | Germline resource VCF when used. |
| `--panel-of-normals`, `--pon` | `--pon` | Use `prepon` first when the selected workflow requires a PON index. |
| `--alleles` | `--mutect-alleles` | Force-call allele VCF input. |
| `--interval-padding`, `-ip` | `--interval-padding`, `-ip` | Same padding role when documented. |
| `--java-options`, `--native-pair-hmm-threads`, GATK engine/common flags | No direct equivalent | Not exposed as GATK engine controls by current Parabricks docs. |
| — | PON index handoff from `prepon` / `postpon` workflow flags | Decomposes PON handling into preprocessing, calling, and postprocessing steps. |
| — | Parabricks-specific filtering or compatibility flags documented for the selected version | These are wrapper-specific controls; verify current docs before use. |
| — | GPU/CPU thread and partition controls | Runtime performance tuning. |

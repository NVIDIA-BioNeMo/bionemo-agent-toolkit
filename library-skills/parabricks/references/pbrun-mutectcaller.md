# Parabricks mutectcaller

Use this reference for NVIDIA Parabricks `pbrun mutectcaller` — GATK Mutect2-style somatic variant calling from tumor (and optional normal) BAM/CRAM to VCF.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm tumor-normal or tumor-only mode for the selected version.
3. Collect required inputs:
   - Reference FASTA.
   - Tumor BAM/CRAM.
   - Normal BAM/CRAM when applicable.
   - Output VCF.
   - Somatic resources such as germline resource, panel of normals, or intervals
     when required by the user’s workflow/version.
4. Ask for explicit tumor/normal sample names and labels.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun mutectcaller \
  --ref /workdir/<reference.fa> \
  <version-specific-tumor-normal-inputs> \
  --out-vcf /outputdir/<somatic.vcf.gz>
```

Verify exact tumor/normal, resource, interval, and filtering flags against the
selected version.

For a panel of normals in **4.7.0**, follow
[prepon](pbrun-prepon.md) for contig-header validation and the required `.pon`
resource. Pass the prepared **VCF.GZ** to `--pon`, then use
[postpon](pbrun-postpon.md) for PON INFO annotation of the caller's VCF.
A `.tbi` alone does not replace the preprocessing resource.

## Mutect2 Option Mapping

Use this mapping when translating a GATK `Mutect2` command to
`pbrun mutectcaller`. Parabricks documents `mutectcaller` as the
accelerated GATK Mutect2 counterpart; the core tumor/normal flags map directly,
but common GATK engine and Java controls do not.

| GATK option | `pbrun mutectcaller` equivalent | Notes |
| --- | --- | --- |
| `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `--input`, `-I` for tumor | `--in-tumor-bam` | Tumor BAM/CRAM input. |
| `--input`, `-I` for normal | `--in-normal-bam` | Normal BAM/CRAM input when running paired mode. |
| `--tumor-sample` | `--tumor-name` | Must match the sample name in the BAM header. |
| `--normal-sample` | `--normal-name` | Must match the sample name in the normal BAM header. |
| `--output`, `-O` | `--out-vcf` | Output somatic VCF. |
| `--germline-resource` | `--mutect-germline-resource` | Germline resource VCF when used. |
| `--panel-of-normals`, `--pon` | `--pon` | Use `prepon` first when the selected workflow requires a PON index. |
| `--alleles` | `--mutect-alleles` | Force-call allele VCF input. |
| `--intervals`, `-L` | `--interval` or `--interval-file` | Parabricks separates inline intervals from interval files. |
| `--interval-padding`, `-ip` | `--interval-padding`, `-ip` | Same padding role when documented. |
| `--java-options`, `--native-pair-hmm-threads`, GATK engine/common flags | No direct equivalent | Not exposed as GATK engine controls by current Parabricks docs. |

If a GATK `Mutect2` option is not listed above, assume there is no direct
`pbrun mutectcaller` flag until the selected Parabricks version's tool
reference says otherwise.

## mutectcaller Options Without Mutect2 Equivalents

| `pbrun mutectcaller` option | Why it has no GATK Mutect2 equivalent |
| --- | --- |
| PON index handoff from `prepon` / `postpon` workflow flags | Parabricks decomposes PON handling into preprocessing, calling, and postprocessing steps. |
| Parabricks-specific filtering or compatibility flags documented for the selected version | These are wrapper-specific controls; verify current docs before use. |
| `--num-streams-per-gpu`, `--mutect-low-memory`, `--run-partition` | Parabricks GPU/partition performance controls. `--num-streams-per-gpu` default 1. |
| `--num-gpus` | Parabricks GPU count. |


Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

## Validation

- Tumor and normal labels are explicit and correct.
- Resources match the reference build.
- Output VCF exists and is indexed when requested.
- Logs do not show sample-label, resource, reference, mount, CUDA, or memory
  errors.

## Guardrails

- Do not use for germline calling.
- Do not invent panel-of-normals or germline-resource files.
- Do not skip sample-label confirmation for tumor/normal workflows.

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/mutectcaller>

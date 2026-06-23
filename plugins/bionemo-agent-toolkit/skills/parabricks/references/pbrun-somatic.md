# Parabricks somatic

Use this reference for NVIDIA Parabricks `pbrun somatic` — end-to-end tumor-normal or tumor-only somatic pipeline from FASTQ or BAM/CRAM inputs to a somatic VCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm tumor-normal or tumor-only workflow support for the selected version.
3. Collect required inputs:
   - Reference FASTA.
   - Tumor BAM/CRAM or FASTQ inputs as supported.
   - Normal BAM/CRAM or FASTQ inputs when applicable.
   - Output VCF or output directory.
   - Somatic resources such as germline resource, panel of normals, known-sites,
     or intervals when required by the workflow.
4. Ask for tumor and normal sample names explicitly.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun somatic \
  --ref /workdir/<reference.fa> \
  <version-specific-tumor-normal-inputs> \
  <version-specific-output-options>
```

Verify exact input mode, resources, output, interval, and filtering flags
against the selected version.

## Somatic Pipeline Option Mapping

Use this mapping when translating a baseline somatic workflow to
`pbrun somatic`. Depending on the selected version and requested caller, the
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
| GATK `BaseRecalibrator --known-sites` | `--knownSites` | Repeatable known-sites VCF input when BQSR is used. |
| Mutect2 `--germline-resource` | `--mutect-germline-resource` | Germline resource VCF when used. |
| Mutect2 `--panel-of-normals`, `--pon` | No direct `pbrun somatic` equivalent | Use a `mutectcaller` PON workflow with `prepon`/`postpon` when required. |
| Mutect2/DeepSomatic output VCF | `--out-vcf` | Output somatic VCF. |
| Intervals/regions | `--interval` or `--interval-file` | Parabricks separates inline intervals from interval files where documented. |
| Baseline options not listed here | No direct equivalent | Not exposed by current Parabricks docs for `pbrun somatic`. |

## somatic Options Without Baseline Somatic Equivalents

| `pbrun somatic` option | Why it has no direct baseline equivalent |
| --- | --- |
| End-to-end tumor/normal input-mode flags | Parabricks combines preprocessing and somatic calling stages. |
| `prepon`/`postpon` PON handoff flags | Parabricks-specific decomposition of PON processing. |
| GPU alignment/calling stream, queue, and memory controls | Parabricks GPU runtime tuning. |
| GPU write/sort/storage controls | Parabricks accelerated output pipeline. |
| Caller-specific TensorRT/model flags where documented | Parabricks model deployment differs from CPU/GATK or Google runtimes. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Tumor/normal labels and sample relationships are correct.
- Reference and resources match the same build.
- Output VCF or output directory exists.
- Logs do not show sample-label, resource, reference, read group, mount, CUDA,
  or memory errors.

## Guardrails

- Do not use for germline calling.
- Do not invent tumor/normal relationships, panel-of-normals, or resource files.
- If the user asks for a specific caller, consider `mutectcaller` or
  `deepsomatic` instead.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_somatic.html>

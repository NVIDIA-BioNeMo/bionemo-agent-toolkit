# Parabricks germline

Use this reference for NVIDIA Parabricks `pbrun germline` — end-to-end GATK-style germline pipeline from FASTQ or BAM/CRAM through HaplotypeCaller to VCF/gVCF.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm whether the user wants an end-to-end GATK-style germline pipeline or
   a standalone `haplotypecaller` run.
3. Collect required inputs:
   - Reference FASTA.
   - FASTQ pairs or BAM/CRAM, depending on the selected version.
   - Output VCF/gVCF or output directory.
   - Known-sites/resources for BQSR when used.
4. Ask for read groups, intervals, ploidy, temporary directory, and logs when
   relevant.
5. For preprocessing-only questions, route to
   `pbrun-fq2bam.md` and related FASTQ/BAM references; for runtime readiness, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun germline \
  --ref /workdir/<reference.fa> \
  <version-specific-input-options> \
  <version-specific-output-options>
```

Verify exact input, known-sites, output, interval, and ploidy flags against the
selected version.

## BWA-MEM/GATK Germline Option Mapping

Use this when translating a baseline BWA-MEM plus GATK germline workflow to
`pbrun germline`. Preprocessing mappings (--ref, FASTQ/BAM inputs, BWA options,
markdup/BQSR, intervals, and shared execution controls) for `germline` are in
[shared-options.md](shared-options.md).

| Baseline option | `pbrun germline` equivalent | Notes |
| --- | --- | --- |
| GATK `HaplotypeCaller --output`, `-O` | `--out-variants` | VCF/gVCF output. |
| GATK `HaplotypeCaller --emit-ref-confidence GVCF` | `--gvcf` | gVCF mode. |
| GATK `HaplotypeCaller --sample-ploidy` | `--ploidy` | Haploid/diploid where documented. |
| GATK `HaplotypeCaller` annotation/output-mode/pruning controls | `--haplotypecaller-options` | Pass supported HaplotypeCaller options as one string. |
| `--java-options`, GATK engine/common flags | No direct equivalent | Not exposed as GATK engine controls. |

If a baseline option is not listed here or in [shared-options.md](shared-options.md)
for `germline`, assume no direct flag until the selected release's tool reference
confirms it.

## germline Options Without BWA-MEM/GATK Equivalents

Shared Parabricks pipeline and GPU controls for `germline` are in
[shared-options.md](shared-options.md). BWA tuning is in [performance.md](performance.md).

| `pbrun germline` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--run-partition` | Genome partitions for HaplotypeCaller (one process per partition). Not fq2bam GPU-process partitioning. |
| `--bwa-gpu-num-per-partition` | BWA GPUs per worker when `--run-partition` is set (default: 2; must divide `--num-gpus`). |
| `--num-streams-per-gpu` | HaplotypeCaller streams (default: 1). Not a partition flag. |

Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

## Validation

- Inputs and reference resources match the same build.
- Read groups are explicit when FASTQs are used.
- Output VCF/gVCF exists and is indexed when requested.
- Logs do not show known-sites, read-group, reference mismatch, mount, CUDA, or
  out-of-memory errors.

## Guardrails

- Do not use `germline` for somatic calling.
- Do not invent known-sites or ploidy settings.
- Do not pass `--sample-sex`, `--range-male`, `--range-female`, or
  `--use-GRCh37-regions` (removed in v4.7.1).

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/germline>

# Parabricks germline

Use this reference for NVIDIA Parabricks `pbrun germline` — end-to-end GATK-style germline pipeline from FASTQ or BAM/CRAM through HaplotypeCaller to VCF/gVCF.

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

Use this mapping when translating a baseline BWA-MEM plus GATK germline
workflow to `pbrun germline`. Parabricks v4.7.0 documents this as a pipeline
from FASTQ to VCF, so the CLI maps to BWA-MEM, SortSam, MarkDuplicates,
BaseRecalibrator, ApplyBQSR, and HaplotypeCaller rather than one upstream tool.

| Baseline option | `pbrun germline` equivalent | Notes |
| --- | --- | --- |
| BWA-MEM/GATK `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `bwa mem <read1> <read2>` | `--in-fq <read1> <read2>` | Paired FASTQ input; repeat for multiple read groups. |
| Single-end FASTQ input | `--in-se-fq` | Parabricks single-end input. |
| `bwa mem -R <read-group>` | read group string after FASTQ inputs, or `--read-group-*` flags | Do not invent read group values. |
| `bwa mem -M`, `-Y`, `-C`, `-T`, `-B`, `-U`, `-L`, `-I`, `-K` | `--bwa-options` | Pass supported BWA-MEM options as one string. |
| GATK/Picard `SortSam -O` / final pipeline output BAM | `--out-bam` | BAM after sorting/duplicate marking. |
| GATK/Picard `MarkDuplicates -M` | `--out-duplicate-metrics` | Duplicate metrics output. |
| Skip GATK/Picard `MarkDuplicates` | `--no-markdups` | Returns sorted BAM without duplicate marking when supported. |
| GATK `BaseRecalibrator --known-sites` | `--knownSites` | Repeatable known-sites VCF input. |
| GATK `BaseRecalibrator --output` | `--out-recal-file` | BQSR report output. |
| GATK `HaplotypeCaller --output`, `-O` | `--out-variants` | VCF/gVCF output. |
| GATK `HaplotypeCaller --emit-ref-confidence GVCF` | `--gvcf` | Generate gVCF output. |
| GATK `HaplotypeCaller --sample-ploidy` | `--ploidy` | Parabricks documents haploid/diploid support where applicable. |
| GATK `HaplotypeCaller` annotation/output-mode/pruning controls | `--haplotypecaller-options` | Pass supported original HaplotypeCaller options as one string. |
| GATK `--intervals`, `-L` | `--interval` or `--interval-file` | Parabricks separates inline intervals from interval files. |
| GATK `--interval-padding`, `-ip` | `--interval-padding`, `-ip` | Same padding role. |
| GATK/Picard `--TMP_DIR` / `--tmp-dir` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| `--java-options`, GATK engine/common flags | No direct equivalent | Not exposed as GATK engine controls by current Parabricks docs. |

If a baseline BWA-MEM, GATK, or Picard option is not listed above, assume there
is no direct `pbrun germline` flag until the selected Parabricks version's tool
reference says otherwise.

## germline Options Without BWA-MEM/GATK Equivalents

| `pbrun germline` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--max-read-length`, `--min-read-length`, `--filter-flag`, `--skip-multiple-hits` | Parabricks pipeline read/SAM filtering controls. |
| `--align-only`, `--standalone-bqsr`, `--fix-mate` | Parabricks pipeline mode controls. |
| `--monitor-usage`, `--no-warnings` | Parabricks runtime reporting controls. |
| `--bwa-nstreams`, `--bwa-cpu-thread-pool`, `--bwa-primary-cpus`, `--bwa-normalized-queue-capacity` | Parabricks CPU/GPU alignment scheduling controls. |
| `--cigar-on-gpu`, `--gpuwrite`, `--gpuwrite-deflate-algo`, `--gpusort`, `--use-gds` | GPU-accelerated write/sort/storage controls. |
| `--memory-limit`, `--low-memory` | Parabricks host/GPU memory controls. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Inputs and reference resources match the same build.
- Read groups are explicit when FASTQs are used.
- Output VCF/gVCF exists and is indexed when requested.
- Logs do not show known-sites, read-group, reference mismatch, mount, CUDA, or
  out-of-memory errors.

## Guardrails

- Do not use `germline` for somatic calling.
- Do not invent known-sites or ploidy settings.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_germline.html>

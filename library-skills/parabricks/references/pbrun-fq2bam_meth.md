# Parabricks fq2bam_meth

Use this reference for NVIDIA Parabricks `pbrun fq2bam_meth` — methylation/bisulfite FASTQ-to-BAM/CRAM alignment with sort and optional markdup/BQSR.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm this is a methylation or bisulfite sequencing workflow. If it is
   standard DNA alignment, route to `pbrun-fq2bam.md`.
3. Collect required inputs:
   - Paired or single-end FASTQ paths.
   - Methylation-compatible reference/genome inputs required by the selected
     version.
   - Output BAM or CRAM path.
   - Read group values when needed.
4. Ask about known-sites, duplicate marking, temporary directory, output format,
   and logs only when relevant and supported.
5. For runtime readiness or installation questions, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun fq2bam_meth \
  --ref /workdir/<reference.fa> \
  --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> \
  --out-bam /outputdir/<sample.meth.bam>
```

Verify exact methylation-specific reference, index, read group, and output
options against the selected version before finalizing.

## Performance Guidance

Prefer the documented automatic stream selection for general commands: leave
`--bwa-nstreams` unset, or set `--bwa-nstreams auto` only when making the
default explicit. Current NVIDIA Parabricks documentation says Parabricks
automatically chooses an optimal number of BWA streams from the GPU device
memory specification.

Use integer `--bwa-nstreams` values only for benchmark-driven tuning or
memory-pressure troubleshooting after confirming the selected Parabricks
version's docs. More streams increase device memory use, so fixed stream counts
should not be part of conservative default command templates.

## BWA-Meth/GATK Option Mapping

Use this mapping when translating a baseline BWA-Meth plus GATK/Picard
bisulfite alignment workflow to `pbrun fq2bam_meth`. Parabricks v4.7.0
documents `fq2bam_meth` as a GPU-accelerated BWA-Meth-compatible workflow that
can sort, mark duplicates, and optionally generate a BQSR report, so the CLI
maps to several upstream commands rather than one single tool.

| Baseline option | `pbrun fq2bam_meth` equivalent | Notes |
| --- | --- | --- |
| BWA-Meth reference / GATK `--reference`, `-R` | `--ref` | Required reference FASTA path. Parabricks expects the converted `.bwameth.c2t` reference from prior baseline BWA-Meth conversion to exist. |
| Paired-end FASTQ input | `--in-fq <read1> <read2>` | Paired bisulfite FASTQ input. Repeat for multiple pairs. |
| Single-end FASTQ input | `--in-se-fq` | Parabricks single-end bisulfite FASTQ input. |
| FASTQ manifest or file list | `--in-fq-list`, `--in-se-fq-list` | Parabricks manifest form. |
| BWA-MEM/BWA-Meth read group option | read group string after `--in-fq`/`--in-se-fq`, or `--read-group-*` flags | Do not invent read group values. |
| BWA-MEM-compatible `-M`, `-Y`, `-C`, `-T`, `-B`, `-U`, `-L`, `-I`, `-K` | `--bwa-options` | Pass supported BWA-MEM options as one string. |
| Alignment-only output | `--align-only` | Stops after BWA-Meth-compatible alignment output; does not coordinate-sort or mark duplicates. |
| GATK/Picard `SortSam --OUTPUT`, `-O` | `--out-bam` | Final BAM/CRAM output path. |
| GATK/Picard `SortSam --SORT_ORDER coordinate` | Default `fq2bam_meth` behavior | Coordinate sorting is part of the normal workflow. |
| GATK/Picard `MarkDuplicates -M` | `--out-duplicate-metrics` | Duplicate metrics output. |
| GATK/Picard `MarkDuplicates --OPTICAL_DUPLICATE_PIXEL_DISTANCE` | `--optical-duplicate-pixel-distance` | Used when duplicate metrics are requested. |
| GATK/Picard queryname duplicate behavior | `--markdups-assume-sortorder-queryname` | Parabricks compatibility control for duplicate marking. |
| GATK/Picard single-end duplicate behavior | `--markdups-single-ended-start-end`, `--ignore-rg-markdups-single-ended` | Single-end duplicate-marking controls. |
| GATK/Picard `MarkDuplicates` version behavior | `--markdups-picard-version-2182` | Compatibility flag for Picard 2.18.2-like marking. |
| Skip GATK/Picard `MarkDuplicates` | `--no-markdups` | Returns BAM after sorting. |
| GATK `BaseRecalibrator --known-sites` | `--knownSites` | Repeatable known-sites VCF input. |
| GATK `BaseRecalibrator --output` | `--out-recal-file` | BQSR report output. |
| GATK `BaseRecalibrator --intervals`, `-L` | `--interval`, `--interval-file` | Parabricks separates inline intervals from interval files. |
| GATK `BaseRecalibrator --interval-padding`, `-ip` | `--interval-padding`, `-ip` | Same padding role. |
| GATK/Picard `--TMP_DIR` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| GATK/Picard `--VERBOSITY` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag. |
| GATK/Picard `--version` | `--version` | Same version-reporting role. |
| GATK/Picard `--java-options` | No direct equivalent | Java runtime settings do not apply to the Parabricks containerized GPU pipeline. |
| GATK/Picard `--arguments_file`, validation, compression, and cloud-auth common flags | No direct equivalent | Not exposed by current Parabricks docs for `fq2bam_meth`. |

If a BWA-Meth, BWA-MEM, SortSam, MarkDuplicates, or BaseRecalibrator option is
not listed above, assume there is no direct `pbrun fq2bam_meth` flag until the
selected Parabricks version's tool reference says otherwise.

## fq2bam_meth Options Without BWA-Meth/GATK Equivalents

| `pbrun fq2bam_meth` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--out-qc-metrics-dir` | Parabricks workflow output for QC metrics. |
| `--max-read-length`, `--min-read-length` | Parabricks FASTQ filtering/alignment bounds. |
| `--no-warnings` | Parabricks warning suppression. |
| `--filter-flag` | Parabricks SAM flag-based filtering during output generation. |
| `--skip-multiple-hits` | Parabricks SA-tag-based output filtering. |
| `--fix-mate` | Parabricks mate-tag addition within this workflow. |
| `--monitor-usage` | Parabricks runtime resource monitoring. |
| `--standalone-bqsr` | Parabricks mode control for running BQSR as a standalone step inside this pipeline. |
| `--set-as-failed` | Bisulfite-specific Parabricks control for flagging selected strands as QC failures. |
| `--do-not-penalize-chimeras` | Bisulfite-specific Parabricks control for disabling the chimeric-alignment QC heuristic. |
| `--bwa-nstreams`, `--bwa-cpu-thread-pool`, `--num-cpu-threads-per-stage`, `--bwa-normalized-queue-capacity`, `--bwa-primary-cpus` | Parabricks CPU/GPU pipeline scheduling controls. Prefer `--bwa-nstreams auto` for default guidance; use integer stream counts only for benchmarked/manual tuning. |
| `--cigar-on-gpu` | Parabricks GPU offload for CIGAR generation. |
| `--gpuwrite`, `--gpuwrite-deflate-algo`, `--gpusort`, `--use-gds` | GPU-accelerated write/sort/storage controls. |
| `--memory-limit`, `--low-memory` | Parabricks host/GPU memory controls for the pipeline. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp` | Parabricks temporary-file retention. |
| `--no-seccomp-override` | Parabricks Docker/seccomp behavior. |
| `--preserve-file-symlinks` | Parabricks path handling behavior. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- FASTQ and methylation reference inputs resolve inside the container.
- Output BAM/CRAM is created.
- Logs do not show reference/index incompatibility, FASTQ pairing, read group,
  mount, CUDA, or out-of-memory errors.
- The output is appropriate for the user’s downstream methylation workflow.

## Guardrails

- Do not use `fq2bam_meth` for ordinary short-read DNA alignment.
- Do not assume standard `fq2bam` flags all apply to `fq2bam_meth`.
- Do not invent bisulfite/methylation reference preparation steps; verify them
  against docs or user-provided pipeline standards.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted/bestperformance.html>
- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_fq2bam_meth.html>

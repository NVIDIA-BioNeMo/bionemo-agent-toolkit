# Parabricks fq2bam

Use this reference for NVIDIA Parabricks `pbrun fq2bam` — paired short-read FASTQ to aligned BAM/CRAM with sort and optional markdup/BQSR.

## First Steps

1. Identify the execution context:
   - Parabricks version or container tag.
   - Local Docker run, remote host, cloud instance, WDL/Nextflow wrapper, or another launcher.
   - Whether the current machine is the target GPU machine.
2. Collect required inputs:
   - Reference FASTA path inside the container.
   - One or more paired FASTQ input sets.
   - Output BAM or CRAM path.
   - Input and output host directories to mount.
3. Collect optional inputs when relevant:
   - Known-sites VCF paths for BQSR.
   - Output recalibration report path.
   - Read group strings. Do not invent read groups; ask for sample/library/platform/unit values if needed.
   - Output metrics, log file, temporary directory, and target output format.
4. If the user asks about runtime, suitability, software prerequisites, installation readiness, or performance, see `runtime-environment.md` in this skill.
5. Generate a conservative command and clearly mark placeholders the user must replace.
6. Add validation checks after the command.

## Command Shape

Prefer Docker commands shaped like:

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun fq2bam \
  --ref /workdir/<reference.fa> \
  --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> \
  --out-bam /outputdir/<sample.bam>
```

When known-sites are supplied for BQSR, include both known-sites and recalibration output:

```bash
  --knownSites /workdir/<known-sites.vcf.gz> \
  --out-recal-file /outputdir/<sample.recal.txt>
```

For multiple FASTQ pairs from the same sample, repeat `--in-fq`. If read groups are required, include the read group string as the final value for each `--in-fq` group, using values provided by the user.

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

## BWA-MEM/GATK Option Mapping

Use this mapping when translating a baseline BWA-MEM plus GATK/Picard
alignment workflow to `pbrun fq2bam`. Parabricks v4.7.0 documents `fq2bam` as
a GPU BWA-MEM workflow that can sort, mark duplicates, and optionally generate
a BQSR report, so the CLI maps to several upstream commands rather than one
single tool.

| Baseline option | `pbrun fq2bam` equivalent | Notes |
| --- | --- | --- |
| `bwa mem <reference>` / GATK `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `bwa mem <read1> <read2>` | `--in-fq <read1> <read2>` | Paired-end FASTQ input. Repeat for multiple pairs. |
| Single-end FASTQ input | `--in-se-fq` | Parabricks single-end FASTQ input. |
| FASTQ manifest or file list | `--in-fq-list`, `--in-se-fq-list` | Parabricks manifest form; no direct BWA-MEM flag. |
| `bwa mem -R <read-group>` | read group string after `--in-fq`/`--in-se-fq`, or `--read-group-*` flags | Do not invent read group values. |
| `bwa mem -t` | `--bwa-cpu-thread-pool`, `--num-cpu-threads-per-stage`, `--bwa-primary-cpus` | Partial equivalent; Parabricks splits CPU controls across pipeline stages. |
| `bwa mem -M`, `-Y`, `-C`, `-T`, `-B`, `-U`, `-L`, `-I`, `-K` | `--bwa-options` | Pass supported BWA-MEM options as one string. |
| `bwa mem` alignment-only output | `--align-only` | Stops after BWA-MEM output; does not coordinate-sort or mark duplicates. |
| GATK/Picard `SortSam --OUTPUT`, `-O` | `--out-bam` | Final BAM/CRAM output path. |
| GATK/Picard `SortSam --SORT_ORDER coordinate` | Default `fq2bam` behavior | Coordinate sorting is part of the normal workflow. |
| GATK/Picard `MarkDuplicates -I` | Implicit sorted intermediate | `fq2bam` feeds its sorted alignment output into duplicate marking unless disabled. |
| GATK/Picard `MarkDuplicates -O` | `--out-bam` | Final output after duplicate marking unless `--no-markdups` or `--align-only` is used. |
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
| GATK/Picard `--arguments_file`, validation, compression, and cloud-auth common flags | No direct equivalent | Not exposed by current Parabricks docs for `fq2bam`. |

If a BWA-MEM, SortSam, MarkDuplicates, or BaseRecalibrator option is not listed
above, assume there is no direct `pbrun fq2bam` flag until the selected
Parabricks version's tool reference says otherwise.

## fq2bam Options Without BWA-MEM/GATK Equivalents

These options are Parabricks workflow, filtering, performance, runtime, or
filesystem wrapper controls and are not baseline BWA-MEM/GATK/Picard CLI
options already covered in the mapping above.

| `pbrun fq2bam` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--in-se-bam` | Parabricks can convert single-ended BAM/CRAM back to FASTQ as pipeline input. |
| `--out-qc-metrics-dir` | Parabricks workflow output for QC metrics. |
| `--max-read-length`, `--min-read-length` | Parabricks FASTQ filtering/alignment bounds. |
| `--no-warnings` | Parabricks warning suppression. |
| `--filter-flag` | Parabricks SAM flag-based filtering during output generation. |
| `--skip-multiple-hits` | Parabricks SA-tag-based output filtering. |
| `--fix-mate` | Parabricks mate-tag addition within this workflow. |
| `--monitor-usage` | Parabricks runtime resource monitoring. |
| `--standalone-bqsr` | Parabricks mode control for running BQSR as a standalone step inside this pipeline. |
| `--bwa-nstreams`, `--bwa-normalized-queue-capacity` | GPU pipeline stream and queue controls. Prefer `--bwa-nstreams auto` for default guidance; use integer stream counts only for benchmarked/manual tuning. |
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

After generating or reviewing a command, help the user verify:

- The reference FASTA and required indexes are present in the mounted path expected inside the container.
- FASTQ paths resolve inside the container.
- Output directory is writable and has enough free space.
- BAM or CRAM output exists after completion.
- BQSR report exists when `--knownSites` and `--out-recal-file` were requested.
- Logs do not show CUDA, Docker runtime, mount, reference-index, read-group, or out-of-memory errors.

## Guardrails

- Do not guess biological sample identifiers, read group fields, reference builds, known-sites files, or container tags.
- Do not claim a flag is supported across all Parabricks versions unless the user has provided version-specific documentation or the command has been verified for that version.
- Do not promise exact runtimes. Give qualitative estimates unless the user provides benchmark data for a comparable system, dataset, and Parabricks version.
- Keep generated commands reproducible: explicit mounts, explicit workdir, explicit output paths, and visible placeholders.
- Call out when local hardware inspection is irrelevant because the workflow will run on a different host.

## Troubleshooting

For GPU visibility errors:

- Check `nvidia-smi` on the target host.
- Check `docker run --rm --gpus all nvidia/cuda:<tag> nvidia-smi` if Docker runtime setup is in question.
- Confirm the host has NVIDIA drivers and NVIDIA Container Toolkit configured.

For mount/path errors:

- Compare host paths with container paths.
- Ensure every input referenced as `/workdir/...` is under the host directory mounted to `/workdir`.
- Ensure outputs are written under the directory mounted to `/outputdir`.

For memory pressure:

- Ask for GPU model, GPU memory, GPU count, system RAM, dataset size, and Parabricks version.
- Consider `--low-memory` for memory-constrained `fq2bam` runs when supported by the selected version.
- Reduce concurrency only when the user's version and workflow options support that change.

For slow runtime:

- Check whether input, output, and temporary directories are on slow or networked storage.
- Prefer fast local scratch for temporary files when available.
- Consider GPU count, CPU thread count, system RAM, compression/output format, and storage throughput before changing flags.
- Keep `--bwa-nstreams` on `auto` unless benchmarked tuning or memory-pressure troubleshooting justifies a fixed value for the selected version and hardware.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted/bestperformance.html>
- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_fq2bam.html>
- <https://docs.nvidia.com/clara/parabricks/latest/tutorials/fq2bam_tutorial.html>

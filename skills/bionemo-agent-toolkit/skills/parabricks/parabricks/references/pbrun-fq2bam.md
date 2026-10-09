# Parabricks fq2bam

Use this reference for NVIDIA Parabricks `pbrun fq2bam` — paired short-read FASTQ to aligned BAM/CRAM with sort and optional markdup/BQSR.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

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

See [performance.md](performance.md) for BWA stream defaults and optional
`fq2bam` tuning flags.

## BWA-MEM/GATK Option Mapping

Use this when translating BWA-MEM plus GATK/Picard preprocessing to
`pbrun fq2bam`. Parabricks folds alignment, coordinate sorting, duplicate
marking, and optional BQSR report generation into one workflow. Repeated
baseline mappings for `fq2bam` (--ref, FASTQ inputs, BWA pass-through,
markdup/BQSR, intervals, GPU write controls, and similar) are in
[shared-options.md](shared-options.md).

| Baseline option | `pbrun fq2bam` equivalent | Notes |
| --- | --- | --- |
| `bwa mem <read1> <read2>` | `--in-fq <read1> <read2>` | Paired-end FASTQ; repeat for multiple pairs. |
| Single-end FASTQ input | `--in-se-fq` | Single-end FASTQ input. |
| FASTQ manifest or file list | `--in-fq-list`, `--in-se-fq-list` | Parabricks manifest; no direct BWA-MEM flag. |
| `bwa mem -t` | `--bwa-cpu-thread-pool`, `--num-cpu-threads-per-stage`, `--bwa-primary-cpus` | Partial; CPU controls split across stages. |
| `bwa mem` alignment-only output | `--align-only` | Stops after BWA-MEM; no sort/markdup. |
| GATK/Picard `SortSam --SORT_ORDER coordinate` | Default `fq2bam` behavior | Coordinate sorting is part of the normal workflow. |
| GATK/Picard `MarkDuplicates -I` | Implicit sorted intermediate | Sorted alignments feed duplicate marking unless disabled. |
| GATK/Picard `MarkDuplicates -O` | `--out-bam` | Final output unless `--no-markdups` or `--align-only`. |
| GATK/Picard `--arguments_file`, validation, compression, and cloud-auth common flags | No direct equivalent | Not exposed for `fq2bam` in current docs. |

If a baseline option is not listed here or in [shared-options.md](shared-options.md)
for `fq2bam`, assume no direct flag until the selected release's tool reference
confirms it.

## fq2bam Options Without BWA-MEM/GATK Equivalents

Parabricks-only pipeline, filtering, and performance flags for `fq2bam` are in
[shared-options.md](shared-options.md) (**Duplicate marking**, **Execution
controls**, and related rows where **Tools** includes `fq2bam`). BWA stream and
multi-GPU partition guidance is in [performance.md](performance.md).

| `pbrun fq2bam` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--in-se-bam` | Convert single-ended BAM/CRAM back to FASTQ as pipeline input. |

Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

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

- <https://docs.nvidia.com/clara/parabricks/get-started/getting-the-best-performance>
- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/fq2bam>
- <https://docs.nvidia.com/clara/parabricks/tutorials/step-by-step-tutorials/fq-2-bam-tutorial>

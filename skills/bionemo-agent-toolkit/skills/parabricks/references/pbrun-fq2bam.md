# Parabricks fq2bam

Collect the reference FASTA, paired FASTQ sets, output BAM or CRAM, and host
directories to mount. Ask for sample, library, platform, and unit values when
read groups are needed. Optional BQSR requires known-sites VCFs and a
recalibration-report destination; also clarify requested metrics and output
format. Verify reference indexes and FASTQ pairing, inspect read-group errors,
and check for the recalibration report when both `--knownSites` and
`--out-recal-file` were requested. Assess hardware on the actual execution host,
which may differ from the machine used to prepare the command.

## Command Shape

Prefer Docker commands shaped like:

```bash
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

BWA-stream tuning (`--bwa-nstreams`) is shared with `fq2bam_meth`; see
[performance.md](performance.md).

## BWA-MEM/GATK Option Mapping

Parabricks v4.7.0 documents `fq2bam` as
a GPU BWA-MEM workflow that can sort, mark duplicates, and optionally generate
a BQSR report, so the CLI maps to several upstream commands rather than one
single tool.

| Baseline option | `pbrun fq2bam` equivalent | Notes |
| --- | --- | --- |
| `bwa mem <reference>` / GATK `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `bwa mem <read1> <read2>` | `--in-fq <read1> <read2>` | Paired-end FASTQ input. Repeat for multiple pairs. |
| Single-end FASTQ input | `--in-se-fq` | Single-end FASTQ input. |
| FASTQ manifest or file list | `--in-fq-list`, `--in-se-fq-list` | Manifest form; no direct BWA-MEM flag. |
| `bwa mem -R <read-group>` | read group string after `--in-fq`/`--in-se-fq`, or `--read-group-*` flags | Do not invent read group values. |
| `bwa mem -t` | `--bwa-cpu-thread-pool`, `--num-cpu-threads-per-stage`, `--bwa-primary-cpus` | Partial equivalent; Parabricks splits CPU controls across pipeline stages. |
| `bwa mem` alignment-only output | `--align-only` | Stops after BWA-MEM output; does not coordinate-sort or mark duplicates. |
| GATK/Picard `SortSam --SORT_ORDER coordinate` | Default `fq2bam` behavior | Coordinate sorting is part of the normal workflow. |
| GATK/Picard `MarkDuplicates -I` | Implicit sorted intermediate | `fq2bam` feeds its sorted alignment output into duplicate marking unless disabled. |
| GATK/Picard `MarkDuplicates -O` | `--out-bam` | Final output after duplicate marking unless `--no-markdups` or `--align-only` is used. |
| GATK/Picard `--arguments_file`, validation, compression, and cloud-auth common flags | No direct equivalent | Not documented for this tool. |
| — | `--in-se-bam` | Can convert single-ended BAM/CRAM back to FASTQ as pipeline input. |
| — | `--bwa-nstreams`, `--bwa-normalized-queue-capacity` | GPU pipeline stream and queue controls. Prefer `--bwa-nstreams auto` for default guidance; use integer stream counts only for benchmarked/manual tuning. |

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

- <https://docs.nvidia.com/clara/parabricks/latest/tutorials/fq2bam_tutorial.html>

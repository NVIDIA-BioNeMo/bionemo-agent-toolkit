# Parabricks fq2bam_meth

Confirm methylation or bisulfite sequencing; ordinary DNA reads belong with
[fq2bam](pbrun-fq2bam.md). Collect paired or single-end reads, a compatible
methylation reference, alignment destination, and required read groups. Ask
about duplicate marking and known-sites only when applicable. Verify reference
preparation against documentation or the user's pipeline standard, then check
index compatibility, pairing, read groups, and downstream methylation suitability.
The ordinary `fq2bam` option set is not automatically transferable here.

## Command Shape

```bash
pbrun fq2bam_meth \
  --ref /workdir/<reference.fa> \
  --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> \
  --out-bam /outputdir/<sample.meth.bam>
```

## Performance Guidance

BWA-stream tuning (`--bwa-nstreams`) is shared with `fq2bam`; see
[performance.md](performance.md).

## BWA-Meth/GATK Option Mapping

Parabricks v4.7.0
documents `fq2bam_meth` as a GPU-accelerated BWA-Meth-compatible workflow that
can sort, mark duplicates, and optionally generate a BQSR report, so the CLI
maps to several upstream commands rather than one single tool.

| Baseline option | `pbrun fq2bam_meth` equivalent | Notes |
| --- | --- | --- |
| BWA-Meth reference / GATK `--reference`, `-R` | `--ref` | Required reference FASTA path. Parabricks expects the converted `.bwameth.c2t` reference from prior baseline BWA-Meth conversion to exist. |
| Paired-end FASTQ input | `--in-fq <read1> <read2>` | Paired bisulfite FASTQ input. Repeat for multiple pairs. |
| Single-end FASTQ input | `--in-se-fq` | Single-end bisulfite FASTQ input. |
| FASTQ manifest or file list | `--in-fq-list`, `--in-se-fq-list` | Manifest form. |
| BWA-MEM/BWA-Meth read group option | read group string after `--in-fq`/`--in-se-fq`, or `--read-group-*` flags | Do not invent read group values. |
| BWA-MEM-compatible `-M`, `-Y`, `-C`, `-T`, `-B`, `-U`, `-L`, `-I`, `-K` | `--bwa-options` | Pass supported BWA-MEM options as one string. |
| Alignment-only output | `--align-only` | Stops after BWA-Meth-compatible alignment output; does not coordinate-sort or mark duplicates. |
| GATK/Picard `SortSam --SORT_ORDER coordinate` | Default `fq2bam_meth` behavior | Coordinate sorting is part of the normal workflow. |
| GATK/Picard `--arguments_file`, validation, compression, and cloud-auth common flags | No direct equivalent | Not documented for this tool. |
| — | `--set-as-failed` | Bisulfite-specific Parabricks control for flagging selected strands as QC failures. |
| — | `--do-not-penalize-chimeras` | Bisulfite-specific Parabricks control for disabling the chimeric-alignment QC heuristic. |
| — | `--bwa-nstreams`, `--bwa-cpu-thread-pool`, `--num-cpu-threads-per-stage`, `--bwa-normalized-queue-capacity`, `--bwa-primary-cpus` | CPU/GPU pipeline scheduling controls. Prefer `--bwa-nstreams auto` for default guidance; use integer stream counts only for benchmarked/manual tuning. |

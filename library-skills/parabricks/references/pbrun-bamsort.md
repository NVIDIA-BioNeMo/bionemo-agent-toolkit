# Parabricks bamsort

Collect the alignment input, destination, and CRAM reference where required.
Confirm coordinate, queryname, or template-coordinate order and the intended
output format before selecting flags. Large sorts also need an explicit scratch
directory and sufficient free space. Check the resulting sort order and
downstream readability; report an index only if one was requested and produced.
Duplicate marking is a separate [markdup](pbrun-markdup.md) operation.

## Command Shape

```bash
pbrun bamsort \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-bam /outputdir/<sorted.bam> \
  --sort-order coordinate
```

## SortSam Option Mapping

Parabricks v4.7.0 documents `bamsort` as Picard-compatible by
default and also exposes fgbio-compatible sort modes.

| GATK/Picard option | `pbrun bamsort` equivalent | Notes |
| --- | --- | --- |
| `--OUTPUT`, `-O` | `--out-bam` | Required sorted BAM/CRAM output path. |
| `--REFERENCE_SEQUENCE`, `-R` | `--ref` | Required by current Parabricks docs, especially for CRAM/header handling. |
| `--SORT_ORDER`, `-SO` | `--sort-order` | Supports `coordinate`, `queryname`, and `templatecoordinate`. |
| Picard-compatible comparator | `--sort-compatibility picard` | Default Parabricks comparator mode. |
| fgbio comparator behavior | `--sort-compatibility fgbio` | Parabricks-specific selector for fgbio-compatible sorting. |
| `--MAX_RECORDS_IN_RAM` | `--max-records-in-ram` | Applies to queryname/template coordinate sort modes. |
| — | `--num-zip-threads` | Compression worker count. |
| — | `--num-sort-threads` | Sorting worker count. |
| — | `--mem-limit` | Sort/postsort memory limit in GB. |
| — | `--gpusort` | GPU-accelerated sorting. |

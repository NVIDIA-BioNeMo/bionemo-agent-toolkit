# Parabricks markdup

Collect a queryname-sorted alignment, destination, and reference where needed
for CRAM or header checks. If necessary, first use [bamsort](pbrun-bamsort.md)
with `--sort-order queryname`. Ask whether duplicate metrics and an output
index are wanted; verify those artifacts only when requested and supported.
Inspect sort-order and CRAM-reference errors. Marking does not authorize
removing reads: duplicate removal requires an explicit request and a documented
option in the selected release.

## Command Shape

```bash
pbrun markdup \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<queryname_sorted.bam> \
  --out-bam /outputdir/<marked.bam> \
  <optional-metrics-output>
```
When duplicate metrics are requested, add
`--out-duplicate-metrics /outputdir/<marked.metrics.txt>`.

## MarkDuplicates Option Mapping

Parabricks v4.7.0 documents `markdup` as a duplicate-marking
tool that requires queryname-sorted input, while its default output behavior is
compatible with a coordinate-sort-order `MarkDuplicates` baseline.

| GATK/Picard option | `pbrun markdup` equivalent | Notes |
| --- | --- | --- |
| `SortSam --REFERENCE_SEQUENCE`, `-R` / `MarkDuplicates --REFERENCE_SEQUENCE`, `-R` | `--ref` | Required by Parabricks for CRAM support and BAM/CRAM header verification. |
| `MarkDuplicates --INPUT`, `-I` | `--in-bam` | Required input BAM/CRAM. Parabricks expects queryname-sorted input. |
| `MarkDuplicates --OUTPUT`, `-O` | `--out-bam` | Required duplicate-marked BAM/CRAM output. |
| `MarkDuplicates --METRICS_FILE`, `-M` | `--out-duplicate-metrics` | Duplicate metrics output. |
| `MarkDuplicates --ASSUME_SORT_ORDER coordinate`, `-ASO coordinate` | Default `pbrun markdup` behavior | Default matches coordinate-sort-order duplicate-marking behavior even though input must be queryname-sorted. |
| `MarkDuplicates --ASSUME_SORT_ORDER queryname`, `-ASO queryname` | `--markdups-assume-sortorder-queryname` | Matches queryname-sort-order duplicate-marking behavior. |
| `MarkDuplicates --OPTICAL_DUPLICATE_PIXEL_DISTANCE` | `--optical-duplicate-pixel-distance` | Same optical duplicate distance role. |
| Single-end duplicate marking by read ends | `--markdups-single-ended-start-end` | Single-end duplicate-marking control. |
| Ignore read group for single-end duplicate marking | `--ignore-rg-markdups-single-ended` | Must be used with `--markdups-single-ended-start-end`. |
| `SortSam --SORT_ORDER queryname` before marking | No direct `markdup` equivalent | Run `pbrun bamsort --sort-order queryname` first if input is not already queryname-sorted. |
| `SortSam --SORT_ORDER coordinate` after queryname baseline marking | No direct `markdup` equivalent | Use `pbrun bamsort` after `markdup` if the selected workflow requires a separate coordinate-sort step. |
| GATK/Picard `--java-options` | No direct equivalent | Java runtime settings do not apply to the Parabricks containerized GPU tool. |
| GATK/Picard `--arguments_file`, validation, compression, and cloud-auth common flags | No direct equivalent | Not documented for this tool. |
| — | `--num-zip-threads`, `--num-worker-threads` | CPU worker controls. |
| — | `--mem-limit` | Memory limit for sorting/postsorting. |
| — | `--gpuwrite`, `--gpuwrite-deflate-algo`, `--gpusort` | GPU-accelerated write/sort/marking controls. |

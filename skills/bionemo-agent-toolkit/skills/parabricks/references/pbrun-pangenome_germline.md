# Parabricks pangenome_germline

Confirm the user intends graph-aware germline calling. Collect the linear
reference, compatible graph and model bundles, supported FASTQ or alignment
input, and variant destination. Check the graph alignment and caller resource
requirements, and inspect graph-resource errors. Standard
linear-reference calling follows a different route. For graph alignment alone,
use [giraffe](pbrun-giraffe.md).

## vg giraffe/DeepVariant Option Mapping

Parabricks
combines graph alignment, preprocessing, and variant calling, so the mapping is
pipeline-level rather than one-to-one.

| Baseline option | `pbrun pangenome_germline` equivalent | Notes |
| --- | --- | --- |
| `vg giraffe --gbz-name`, `-Z` | `--gbz-name` or version-specific graph flag | Required GBZ graph input when documented. |
| `vg giraffe --dist-name`, `-d` | `--dist-name` or version-specific graph flag | Distance index input. |
| `vg giraffe --minimizer-name`, `-m` | `--minimizer-name` or version-specific graph flag | Minimizer index input. |
| `vg giraffe --zipcodes-name`, `-z` | `--zipcodes-name` or version-specific graph flag | Zipcodes input when required. |
| `vg giraffe --ref-paths` | `--ref-paths` or version-specific path-list flag | Path list/dictionary for headers and reference extraction. |
| FASTQ query input | `--in-fq` or selected input flag | Verify paired/single-end syntax for the selected version. |
| Giraffe-aligned BAM input | `--in-bam` or selected input flag | Use only if the selected version supports prepared alignment input. |
| Linear reference FASTA for variant calling | `--ref` | Reference must match graph-derived paths/build. |
| Intervals/regions | `--interval` or `--interval-file` | Verify pangenome workflow support for interval restriction. |
| Upstream `vg giraffe` or DeepVariant options not listed here | No direct equivalent | Not documented for this tool. |
| — | Version-specific bundled pangenome resource flags | Packages graph/resource handoff differently from a manual `vg` workflow. |
| — | GPU graph-alignment stream, batch, queue, and minimizer controls | GPU implementation tuning. |

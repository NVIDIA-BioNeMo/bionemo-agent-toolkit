# Parabricks giraffe

Collect FASTQs, graph indexes and auxiliary resources, alignment destination,
and required read groups. Establish that the graph resources come from the
same compatible pangenome bundle; a shared filename prefix is insufficient
evidence. Check missing graph components and read-group errors. This route
requires an intentional graph-alignment workflow; ordinary short-read BWA-MEM
alignment without graph resources belongs with [fq2bam](pbrun-fq2bam.md).

For **4.7.0**, the GBZ graph, distance index, minimizer index, and zipcodes file
are required inputs. Supply `--zipcodes-name` explicitly; do not infer a
compatible zipcodes file from a minimizer filename. Use `--ref-paths` when the
output BAM needs a supplied path order or sequence dictionary.

To produce a **coordinate-sorted BAM without duplicate marking**, use
`--no-markdups`. `--align-only` stops before coordinate sorting and therefore
does not meet that output requirement. Preserve the supplied sample and all
read-group fields using the Giraffe-specific flags in the mapping below.

## Performance Guidance

Prefer the documented automatic stream selection for general commands: leave
`--nstreams` unset, or set `--nstreams auto` only when making the default
explicit. In current NVIDIA Parabricks documentation, Giraffe auto mode chooses
the number of CUDA streams, batch size, and GPU acceleration options from
available GPU device memory, and can also account for host-memory limits.

Use integer `--nstreams` values only for benchmark-driven or GPU-specific
tuning after confirming the selected Parabricks version's docs. More streams
can improve throughput, but they also increase device and host memory use, so
fixed stream counts should not be part of conservative default command
templates.

## vg giraffe/GATK Option Mapping

Parabricks v4.7.0 documents
`giraffe` as a GPU pangenome graph aligner that can also sort and mark
duplicates, so not every upstream `vg giraffe` option has a Parabricks
equivalent.

| Baseline option | `pbrun giraffe` equivalent | Notes |
| --- | --- | --- |
| `vg giraffe -Z`, `--gbz-name` | `--gbz-name`, `-Z` | Required GBZ graph input. |
| `vg giraffe -d`, `--dist-name` | `--dist-name`, `-d` | Required distance index. |
| `vg giraffe -m`, `--minimizer-name` | `--minimizer-name`, `-m` | Required minimizer index. |
| `vg giraffe -z`, zipcodes index | `--zipcodes-name`, `-z` | Include when the selected Parabricks version requires a zipcodes file for clustering. |
| `vg giraffe -x`, `--xg-name` | `--xg-name`, `-x` | Optional XG graph used for BAM output. |
| `vg giraffe -g`, `--graph-name` | `--graph-name`, `-g` | Optional GBWTGraph input for mapping. |
| `vg giraffe -H`, `--gbwt-name` | `--gbwt-name`, `-H` | Optional GBWT index input. |
| FASTQ query input | `--in-fq`, `--in-se-fq` | Paired-end and single-end FASTQ inputs. |
| FASTQ input list | `--in-fq-list`, `--in-se-fq-list` | Manifest form. |
| `vg giraffe --read-group` | `--read-group` | Read group ID. |
| Read group sample/library/platform/platform-unit fields | `--sample`, `--read-group-library`, `--read-group-platform`, `--read-group-pu` | Explicit read group tag flags. |
| `vg giraffe --ref-paths` / path list for SAM headers | `--ref-paths` | Path list or HTSlib dictionary for `@SQ` headers. |
| `vg giraffe --prune-low-cplx` | `--prune-low-cplx` | Same low-complexity anchor pruning role. |
| `vg giraffe` fragment length controls | `--max-fragment-length`, `--fragment-mean`, `--fragment-stdev` | Same fragment-distribution role. |
| `vg giraffe --copy-comment` | `--copy-comment` | Appends FASTQ comment to BAM output via auxiliary tag. |
| Alignment-only output | `--align-only` | Stops after `vg giraffe` alignment output; does not coordinate-sort. |
| GATK/Picard `SortSam --OUTPUT`, `-O` | `--out-bam` | Final BAM output path. |
| GATK/Picard duplicate-marking behavior | `--markdups-*`, `--optical-duplicate-pixel-distance`, `--no-markdups` | Exposes the duplicate-marking controls documented for this pipeline. |
| Upstream `vg giraffe` options not listed here | No direct equivalent | Not documented for this tool. |
| — | `--nstreams`, `--num-cpu-threads-per-gpu`, `--batch-size`, `--write-threads`, `--work-queue-capacity` | GPU/CPU pipeline scheduling controls. Prefer `--nstreams auto` for default guidance; use integer stream counts only for benchmarked/manual tuning. |
| — | `--minimizers-gpu` | GPU offload for minimizers/seeds in supported single-end runs. |

## Key References

- [Parabricks 4.7.0 Giraffe manual](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_giraffe.html)

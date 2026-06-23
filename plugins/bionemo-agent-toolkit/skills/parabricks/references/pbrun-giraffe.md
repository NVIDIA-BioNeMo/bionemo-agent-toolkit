# Parabricks giraffe

Use this reference for NVIDIA Parabricks `pbrun giraffe` — pangenome graph alignment of short-read FASTQ to BAM/CRAM via vg giraffe.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the user is doing pangenome graph alignment. If they have ordinary
   short-read DNA FASTQs and no graph resources, route to `pbrun-fq2bam.md`.
3. Collect required inputs for the selected version:
   - FASTQ input paths.
   - Pangenome graph/index/resource files.
   - Reference or auxiliary files required by the workflow.
   - Output BAM/CRAM path and optional metrics/log paths.
4. Ask for read group values when needed.
5. For runtime readiness or installation questions, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun giraffe \
  <version-specific-graph-input-options> \
  --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> \
  --out-bam /outputdir/<sample.giraffe.bam>
```

Always verify exact graph resource flags and output options against the selected
version before finalizing. Do not guess graph/index file combinations.

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

Use this mapping when translating a baseline `vg giraffe` plus GATK/Picard
post-processing workflow to `pbrun giraffe`. Parabricks v4.7.0 documents
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
| FASTQ query input | `--in-fq`, `--in-se-fq` | Parabricks paired-end and single-end FASTQ inputs. |
| FASTQ input list | `--in-fq-list`, `--in-se-fq-list` | Parabricks manifest form. |
| `vg giraffe --read-group` | `--read-group` | Read group ID. |
| Read group sample/library/platform/platform-unit fields | `--sample`, `--read-group-library`, `--read-group-platform`, `--read-group-pu` | Parabricks explicit read group tag flags. |
| `vg giraffe --ref-paths` / path list for SAM headers | `--ref-paths` | Path list or HTSlib dictionary for `@SQ` headers. |
| `vg giraffe --prune-low-cplx` | `--prune-low-cplx` | Same low-complexity anchor pruning role. |
| `vg giraffe` fragment length controls | `--max-fragment-length`, `--fragment-mean`, `--fragment-stdev` | Same fragment-distribution role. |
| `vg giraffe --copy-comment` | `--copy-comment` | Appends FASTQ comment to BAM output via auxiliary tag. |
| Alignment-only output | `--align-only` | Stops after `vg giraffe` alignment output; does not coordinate-sort. |
| GATK/Picard `SortSam --OUTPUT`, `-O` | `--out-bam` | Final BAM output path. |
| GATK/Picard `MarkDuplicates -M` | `--out-duplicate-metrics` | Duplicate metrics output. |
| GATK/Picard duplicate-marking behavior | `--markdups-*`, `--optical-duplicate-pixel-distance`, `--no-markdups` | Parabricks exposes the duplicate-marking controls documented for this pipeline. |
| GATK/Picard `--TMP_DIR` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| GATK/Picard `--VERBOSITY` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag. |
| GATK/Picard `--version` | `--version` | Same version-reporting role. |
| GATK/Picard `--java-options` | No direct equivalent | Java runtime settings do not apply to the Parabricks containerized GPU pipeline. |
| Upstream `vg giraffe` options not listed here | No direct equivalent | Not exposed by current Parabricks docs for `pbrun giraffe`. |

If a `vg giraffe`, SortSam, or MarkDuplicates option is not listed above,
assume there is no direct `pbrun giraffe` flag until the selected Parabricks
version's tool reference says otherwise.

## giraffe Options Without vg giraffe/GATK Equivalents

| `pbrun giraffe` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--max-read-length`, `--min-read-length` | Parabricks FASTQ filtering/alignment bounds. |
| `--monitor-usage` | Parabricks runtime resource monitoring. |
| `--nstreams`, `--num-cpu-threads-per-gpu`, `--batch-size`, `--write-threads`, `--work-queue-capacity` | Parabricks GPU/CPU pipeline scheduling controls. Prefer `--nstreams auto` for default guidance; use integer stream counts only for benchmarked/manual tuning. |
| `--minimizers-gpu` | Parabricks GPU offload for minimizers/seeds in supported single-end runs. |
| `--gpuwrite`, `--gpuwrite-deflate-algo`, `--gpusort`, `--use-gds` | GPU-accelerated write/sort/storage controls. |
| `--memory-limit`, `--low-memory` | Parabricks host/GPU memory controls for the pipeline. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp` | Parabricks temporary-file retention. |
| `--no-seccomp-override` | Parabricks Docker/seccomp behavior. |
| `--preserve-file-symlinks` | Parabricks path handling behavior. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- FASTQ and graph resource paths resolve inside the container.
- Graph resources are from the same build/pangenome bundle expected by the
  workflow.
- Output BAM/CRAM is created.
- Logs do not show missing graph resources, read group, mount, CUDA, or
  out-of-memory errors.

## Guardrails

- Do not substitute `giraffe` for standard BWA-MEM alignment unless the user
  explicitly wants pangenome graph alignment.
- Do not invent pangenome resource paths or claim compatibility across graph
  bundles without evidence.
- Keep command options version-specific.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted/bestperformance.html>
- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_giraffe.html>

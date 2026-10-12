# Parabricks bamsort

Use this reference for NVIDIA Parabricks `pbrun bamsort` — coordinate-sorting BAM/CRAM alignment files.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

## First Steps

1. Confirm the Parabricks version or container tag.
2. Collect required inputs:
   - Input BAM or CRAM path.
   - Output sorted BAM or CRAM path.
   - Reference FASTA when CRAM input or the selected version requires it.
3. Ask whether coordinate sort or another sort order is required, then verify
   support in the selected version.
4. Ask for temporary directory and available storage if the input is large.
5. For runtime readiness or storage concerns, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun bamsort \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-bam /outputdir/<sorted.bam> \
  --sort-order coordinate
```

Verify exact option names for sort order, reference, temporary directory,
threading, and output format against the selected version.

## SortSam Option Mapping

Use this mapping when translating a GATK/Picard `SortSam` command to
`pbrun bamsort`. Parabricks documents `bamsort` as Picard-compatible by
default and also exposes fgbio-compatible sort modes.

| GATK/Picard option | `pbrun bamsort` equivalent | Notes |
| --- | --- | --- |
| `--INPUT`, `-I` | `--in-bam` | Required BAM/CRAM input path. |
| `--OUTPUT`, `-O` | `--out-bam` | Required sorted BAM/CRAM output path. |
| `--REFERENCE_SEQUENCE`, `-R` | `--ref` | Required by current Parabricks docs, especially for CRAM/header handling. |
| `--SORT_ORDER`, `-SO` | `--sort-order` | Parabricks supports `coordinate`, `queryname`, and `templatecoordinate`. |
| Picard-compatible comparator | `--sort-compatibility picard` | Default Parabricks comparator mode. |
| fgbio comparator behavior | `--sort-compatibility fgbio` | Parabricks-specific selector for fgbio-compatible sorting. |
| `--MAX_RECORDS_IN_RAM` | `--max-records-in-ram` | Applies to queryname/template coordinate sort modes. |
| `--arguments_file`, `--VALIDATION_STRINGENCY`, Picard compression/common flags | No direct equivalent | Not exposed by current Parabricks docs. |

If a Picard `SortSam` option is not listed above, assume there is no direct
`pbrun bamsort` flag until the selected Parabricks version's tool reference
says otherwise.

## bamsort Options Without SortSam Equivalents

| `pbrun bamsort` option | Why it has no SortSam equivalent |
| --- | --- |
| `--num-zip-threads` | Parabricks compression worker count. |
| `--num-sort-threads` | Parabricks sorting worker count. |
| `--mem-limit` | Parabricks sort/postsort memory limit in GB. |
| `--gpuwrite` | Parabricks GPU-accelerated final BAM/CRAM writing. |
| `--gpuwrite-deflate-algo` | Parabricks/nvCOMP DEFLATE algorithm selection for `--gpuwrite`. |
| `--gpusort` | Parabricks GPU-accelerated sorting. |
| `--keep-tmp` | Parabricks temporary-file retention. |


Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

## Validation

- Input alignment file resolves inside the container.
- Output sorted BAM/CRAM is created and is usable by downstream tools.
- Temporary directory has enough free space.
- Logs do not show mount, CRAM reference, temp-space, CUDA, or out-of-memory
  errors.

## Guardrails

- Do not claim the output is indexed unless an index was explicitly requested
  and produced.
- Do not change sort order or output format without user intent.
- Do not use this reference for duplicate marking; route to `pbrun-markdup.md`.

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/bamsort>

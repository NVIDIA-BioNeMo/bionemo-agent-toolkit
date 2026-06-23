# Parabricks pangenome_germline

Use this reference for NVIDIA Parabricks `pbrun pangenome_germline` — pangenome-aware germline pipeline from FASTQ or aligned inputs through vg giraffe and DeepVariant to VCF/gVCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the user wants pangenome-aware germline calling.
3. Collect required inputs:
   - Reference FASTA and pangenome graph/resource bundle.
   - FASTQ or aligned input as supported by the selected version.
   - Output VCF/gVCF or output directory.
   - Any model/resource bundle required by the selected version.
4. Ask whether `prepon` or `postpon` steps are part of the intended workflow.
5. For pangenome graph alignment only, consider
   `pbrun-fq2bam.md` and related FASTQ/BAM references; for runtime readiness, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun pangenome_germline \
  <version-specific-pangenome-resource-options> \
  <version-specific-input-options> \
  <version-specific-output-options>
```

Verify graph/resource, input, and output flags against the selected version.

## vg giraffe/DeepVariant Option Mapping

Use this mapping when translating a baseline pangenome workflow using
`vg giraffe` plus DeepVariant to `pbrun pangenome_germline`. Parabricks
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
| DeepVariant `--output_vcf` | `--out-variants` | VCF/gVCF output. |
| DeepVariant `--output_gvcf` / gVCF mode | `--gvcf` plus `--out-variants` | Output path extension controls VCF/gVCF naming when documented. |
| DeepVariant custom model | `--pb-model-file`, `--pb-small-model-file` | Parabricks TensorRT model files where supported. |
| Intervals/regions | `--interval` or `--interval-file` | Verify pangenome workflow support for interval restriction. |
| Upstream `vg giraffe` or DeepVariant options not listed here | No direct equivalent | Not exposed by current Parabricks docs for `pangenome_germline`. |

## pangenome_germline Options Without vg giraffe/DeepVariant Equivalents

| `pbrun pangenome_germline` option | Why it has no direct baseline equivalent |
| --- | --- |
| Version-specific bundled pangenome resource flags | Parabricks packages graph/resource handoff differently from a manual `vg` workflow. |
| `prepon`/`postpon` workflow handoff flags | Parabricks-specific pangenome preprocessing/postprocessing integration. |
| GPU graph-alignment stream, batch, queue, and minimizer controls | Parabricks GPU implementation tuning. |
| GPU write/sort/storage controls | Parabricks accelerated output pipeline. |
| DeepVariant channel/allele-counter flags exposed directly by Parabricks | Parabricks first-class controls for DeepVariant internals. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Pangenome resources are complete and compatible with the reference build.
- Inputs resolve inside the container.
- Output VCF/gVCF or output directory exists.
- Logs do not show graph resource, reference, model, mount, CUDA, or memory
  errors.

## Guardrails

- Do not use for standard linear-reference germline calling unless the user
  explicitly wants pangenome-aware analysis.
- Do not invent graph bundle paths or compatibility.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_pangenome_germline.html>

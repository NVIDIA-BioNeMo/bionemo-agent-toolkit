# Parabricks pangenome_aware_deepvariant

Use this reference for NVIDIA Parabricks `pbrun pangenome_aware_deepvariant` — pangenome-aware DeepVariant germline calling from reads/alignments and a pangenome graph to VCF/gVCF.

## First Steps

1. Confirm the Parabricks version or container tag and verify this tool is
   present in that version.
2. Confirm the user wants pangenome-aware DeepVariant rather than standard
   `deepvariant` or `pangenome_germline`.
3. Collect required inputs:
   - Reference FASTA and pangenome graph/resource bundle.
   - Input reads or alignments as supported by the selected version.
   - Output VCF/gVCF or output directory.
   - Model/resource bundle when required.
4. Ask whether `prepon`, `postpon`, or `giraffe` outputs are expected inputs.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun pangenome_aware_deepvariant \
  <version-specific-pangenome-resource-options> \
  <version-specific-input-options> \
  <version-specific-output-options>
```

Verify exact flags against the version-specific reference before finalizing;
this tool is listed separately in the current alphabetical tool index.

## DeepVariant/Pangenome Option Mapping

Use this mapping when translating a Google DeepVariant workflow that consumes
pangenome-aware inputs to `pbrun pangenome_aware_deepvariant`. This is not a
drop-in replacement for standard `pbrun deepvariant`; graph and pangenome
resource flags are part of the command surface.

| Baseline option | `pbrun pangenome_aware_deepvariant` equivalent | Notes |
| --- | --- | --- |
| DeepVariant `--ref` | `--ref` | Linear reference FASTA; must match pangenome resources. |
| DeepVariant `--reads` | `--in-bam` or selected input flag | Prepared pangenome-aware alignment input when supported. |
| Pangenome graph input | `--pangenome` or version-specific graph/resource flag | Verify exact resource flag names in the selected version. |
| DeepVariant `--output_vcf` | `--out-variants` | VCF/gVCF output. |
| DeepVariant `--output_gvcf` / gVCF mode | `--gvcf` plus `--out-variants` | Output path extension controls VCF/gVCF naming when documented. |
| DeepVariant custom model | `--pb-model-file`, `--pb-small-model-file` | Parabricks TensorRT model files where supported. |
| DeepVariant regions | `--interval` or `--interval-file` | Verify interval support for the selected pangenome workflow. |
| DeepVariant make-examples options | Matching explicit Parabricks flags where documented | Use only flags listed in the selected Parabricks tool reference. |
| Standard DeepVariant options not listed here | No direct equivalent | Not exposed by current Parabricks docs for this pangenome-aware tool. |

## pangenome_aware_deepvariant Options Without DeepVariant Equivalents

| `pbrun pangenome_aware_deepvariant` option | Why it has no standard DeepVariant equivalent |
| --- | --- |
| Pangenome graph/resource input flags | Standard DeepVariant is linear-reference based. |
| `prepon`/`postpon` workflow handoff flags | Parabricks-specific pangenome preprocessing/postprocessing integration. |
| GPU graph/pangenome runtime controls | Parabricks GPU implementation tuning. |
| Parabricks TensorRT model-file controls | Parabricks model deployment differs from Google DeepVariant's Keras/TensorFlow runtime. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Pangenome resources, reference, model/resources, and input files are
  compatible.
- Output VCF/gVCF or output directory exists.
- Logs do not show missing graph resources, model errors, reference mismatch,
  mount, CUDA, or memory errors.

## Guardrails

- Do not treat this as standard `deepvariant`.
- Do not infer resource compatibility across pangenome bundles.
- Verify current docs before recommending any optional flags.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_pangenome_aware_deepvariant.html>

# Parabricks pangenome_aware_deepvariant

Use this reference for NVIDIA Parabricks `pbrun pangenome_aware_deepvariant` — pangenome-aware DeepVariant germline calling from reads/alignments and a pangenome graph to VCF/gVCF.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

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

For Roche SBX-D or SBX-Fast BAMs, add `--sbx`. That selects the shipped
`deepvariant_pangenome_aware_sbx.eng` model unless `--pb-model-file` overrides
it, and applies SBX make-examples/postprocess defaults.

## Parabricks 4.7.0 command

For prepared BAM/CRAM input, the four required arguments are `--ref`,
`--pangenome` (the GBZ graph), `--in-bam`, and `--out-variants`:

```bash
pbrun pangenome_aware_deepvariant \
  --ref /workdir/<reference.fa> \
  --pangenome /workdir/<graph.gbz> \
  --in-bam /workdir/<sample.bam> \
  --out-variants /outputdir/<sample.vcf.gz>
```

Check that the linear reference, input alignments, graph paths, and selected
model belong to a compatible setup. This standalone caller consumes prepared
alignments; it does not require rerunning the `pangenome_germline` FASTQ pipeline.

## Comparing with Google's implementation

The 4.7.0 manual documents three sources of output differences. Investigate
them separately after matching inputs, model versions, and comparison settings:

- **CNN inference:** TensorRT and Keras can differ by about `10^-5` in predicted
  scores. The manual reports observed differing variants among zero-quality
  `RefCalls`; this is an observation, not a guarantee about every dataset.
- **Supplementary-read ordering:** with `--keep-supplementary-alignments`,
  equal sorting keys can leave reads in a different order. For a controlled
  upstream comparison, the manual recommends replacing `std::sort` with
  `std::stable_sort` in `BuildPileupForOneSample` in `pileup_image_native.cc`.
- **GBZ query caching:** Google's fast path can make graph-query results depend
  on prior query order. Parabricks disables it. For comparison only, the manual
  describes disabling **both** `updateCache` and the cached-range lookup in
  `GbzReader::Query()` in `deepvariant/third_party/nucleus/io/gbz_reader.cc`.
  Disabling only cache updates leaves the cache-hit path in place. This change
  can slow the upstream implementation substantially and is not routine tuning.

Keep any upstream patches in a separate comparison build, record versions and
settings, and measure output differences before claiming parity. Do not
present these C++ changes as `pbrun` flags, silently alter production software,
or promise that they remove TensorRT numerical differences.

## DeepVariant/Pangenome Option Mapping

Use this mapping when translating a Google DeepVariant workflow that consumes
pangenome-aware inputs to `pbrun pangenome_aware_deepvariant`. This is not a
drop-in replacement for standard `pbrun deepvariant`; graph and pangenome
resource flags are part of the command surface.

| Baseline option | `pbrun pangenome_aware_deepvariant` equivalent | Notes |
| --- | --- | --- |
| DeepVariant `--ref` | `--ref` | Linear reference FASTA; must match pangenome resources. |
| DeepVariant `--reads` | `--in-bam` | Prepared BAM/CRAM input. |
| Pangenome graph input | `--pangenome` | Required GBZ pangenome file. |
| DeepVariant `--output_vcf` | `--out-variants` | VCF/gVCF output path. |
| DeepVariant custom model | `--pb-model-file` | Optional TensorRT `.eng`. Default is `deepvariant_pangenome_aware.eng`, or `deepvariant_pangenome_aware_sbx.eng` when `--sbx` is set. |
| DeepVariant regions | `--interval` or `--interval-file` | Verify interval support for the selected pangenome workflow. |
| Roche SBX Google case-study settings | `--sbx` | Applies SBX model and make-examples/postprocess defaults. |
| DeepVariant make-examples options | Matching explicit Parabricks flags where documented | Use only flags listed in the selected Parabricks tool reference. |
| Standard DeepVariant options not listed here | No direct equivalent | Not exposed by current Parabricks docs for this pangenome-aware tool. |

## pangenome_aware_deepvariant Options Without DeepVariant Equivalents

| `pbrun pangenome_aware_deepvariant` option | Why it has no standard DeepVariant equivalent |
| --- | --- |
| `--pangenome` | Standard DeepVariant is linear-reference based. |
| `--sbx` | Parabricks Roche SBX mode and shipped SBX engine selection. |
| `--sample-name-pangenome`, `--ref-name-pangenome` | Parabricks pangenome sample/reference name controls (defaults `pangenome` and `GRCh38`). |
| GPU graph/pangenome runtime controls | Parabricks GPU implementation tuning. |
| Parabricks TensorRT model-file controls | Parabricks model deployment differs from Google DeepVariant's Keras/TensorFlow runtime. |
| `--num-gpus` | Parabricks GPU count. |


Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

## Validation

- Pangenome resources, reference, model/resources, and input files are
  compatible.
- Output VCF/gVCF or output directory exists.
- Logs do not show missing graph resources, model errors, reference mismatch,
  mount, CUDA, or memory errors.

## Guardrails

- Do not treat this as standard `deepvariant`.
- Do not infer resource compatibility across pangenome bundles.
- Do not invent Roche SBX sample names or case-study BAM paths; use `--sbx`
  only when the user has SBX-D or SBX-Fast alignments.
- Verify current docs before recommending any optional flags.

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/pangenome_aware_deepvariant>

# Parabricks deepsomatic

Use this reference for NVIDIA Parabricks `pbrun deepsomatic` — DeepSomatic-based somatic variant calling from tumor (and optional normal) BAM/CRAM to VCF/gVCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the somatic analysis design: tumor-normal or tumor-only if supported
   by the selected version.
3. Collect required inputs:
   - Reference FASTA.
   - Tumor BAM/CRAM.
   - Normal BAM/CRAM when applicable.
   - Output VCF/gVCF or output directory.
   - Model or resource bundle when required by the selected version.
4. Ask for intervals, sample names, optional candidate resources, and logs only
   when relevant.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun deepsomatic \
  --ref /workdir/<reference.fa> \
  <version-specific-tumor-normal-inputs> \
  <version-specific-output-options>
```

Verify exact input, model, output, interval, and sample-label flags against the
selected version before finalizing.

## Gotchas

Parabricks DeepSomatic `--gvcf` option actually produces both .g.vcf and .vcf files with the same name. Do not generate separate commands for gvcf and vcf outputs.

## DeepSomatic Option Mapping

Use this mapping when translating a Google DeepSomatic `run_deepsomatic`
command to `pbrun deepsomatic`. Parabricks v4.7.0 documents DeepSomatic as the
Google counterpart with TensorRT-accelerated model inference.

| Google DeepSomatic option | `pbrun deepsomatic` equivalent | Notes |
| --- | --- | --- |
| `--ref` | `--ref` | Required reference FASTA path. |
| `--reads_tumor` | `--in-tumor-bam` | Required tumor BAM/CRAM input. |
| `--reads_normal` | `--in-normal-bam` | Required normal BAM/CRAM input for paired mode. |
| `--output_vcf` | `--out-variants` | Required VCF/gVCF output. |
| `--model_type` | `--mode`, `--use-wes-model`, or selected model file | Parabricks documents short-read, PacBio, and ONT modes plus WES/model-file controls. |
| `--regions` | `--interval` or `--interval-file` | Parabricks separates inline intervals from BED interval files. |
| `--customized_model` | `--pb-model-file` | Non-default Parabricks model file. |
| `--make_examples_extra_args` for supported candidate/pileup/read controls | Matching explicit Parabricks flags such as `--vsc-*`, `--alt-aligned-pileup`, `--min-mapping-quality`, and `--channel-*` | Parabricks exposes many make-examples options as first-class flags. |
| `--num_shards` | `--num-streams-per-gpu`, `--num-cpu-threads-per-stream`, or related Parabricks performance flags | Partial equivalent only; Parabricks partitions work around GPU streams and CPU threads; Prefer using "auto" parameters |
| Google DeepSomatic options not listed here | No direct equivalent | Not exposed by current Parabricks docs for `pbrun deepsomatic`. |

If a Google DeepSomatic option is not listed above, assume there is no direct
`pbrun deepsomatic` flag until the selected Parabricks version's tool reference
says otherwise.

## deepsomatic Options Without DeepSomatic Equivalents

| `pbrun deepsomatic` option | Why it has no Google DeepSomatic equivalent |
| --- | --- |
| `--disable-use-window-selector-model` | Parabricks inverse/compatibility control for window selector behavior. |
| `--pb-model-file` | Parabricks TensorRT model file input. |
| GPU stream, CPU thread, and memory controls | Parabricks GPU runtime tuning. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Tumor and normal sample roles are explicit and correct.
- BAM/CRAM, reference, indexes, model/resources, and intervals match the same
  reference build.
- Output VCF/gVCF or output directory exists.
- Logs do not show model/resource, sample-label, reference mismatch, mount,
  CUDA, or out-of-memory errors.

## Guardrails

- Do not substitute `deepsomatic` for germline DeepVariant.
- Do not invent tumor/normal relationships or model files.
- Do not promise exact sensitivity/specificity without comparable validation.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_deepsomatic.html>

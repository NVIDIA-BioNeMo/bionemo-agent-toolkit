# Parabricks deepvariant

Use this reference for NVIDIA Parabricks `pbrun deepvariant` — DeepVariant germline variant calling from aligned BAM/CRAM to VCF and optional gVCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the input is prepared aligned reads. If starting from FASTQ and the
   user wants an end-to-end germline pipeline, consider
   `pbrun-deepvariant_germline.md`.
3. Collect required inputs:
   - Reference FASTA.
   - Input BAM/CRAM.
   - Output VCF and optional gVCF.
   - Model type or model file/resource when required.
4. Ask for intervals, sample name, haploid/sex chromosome handling, and logs
   only when relevant.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun deepvariant \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-variants /outputdir/<sample.vcf.gz>
```

Verify exact model, gVCF, interval, and output flags against the selected
version.

## Gotchas

Parabricks DeepVariant `--gvcf` option actually produces both .g.vcf and .vcf files with the same name. Do not generate separate commands for gvcf and vcf outputs.

## DeepVariant Option Mapping

Use this mapping when translating a Google DeepVariant `run_deepvariant`
command to `pbrun deepvariant`. Parabricks v4.7.0 documents DeepVariant as the
Google counterpart with TensorRT-accelerated model inference, but the CLI uses
Parabricks flag names and runtime controls.

| Google DeepVariant option | `pbrun deepvariant` equivalent | Notes |
| --- | --- | --- |
| `--ref` | `--ref` | Required reference FASTA path. |
| `--reads` | `--in-bam` | Required BAM/CRAM input. |
| `--output_vcf` | `--out-variants` | Required VCF/gVCF output. |
| `--model_type` | `--mode`, `--use-wes-model`, or selected model file | Parabricks documents short-read, PacBio, and ONT modes plus WES/model-file controls. |
| `--regions` | `--interval` or `--interval-file` | Parabricks separates inline intervals from BED interval files. |
| `--output_gvcf` / gVCF mode | `--gvcf` plus `--out-variants` | Output path extension controls whether the result is VCF/gVCF. |
| `--customized_model` | `--pb-model-file` | Non-default Parabricks model file. |
| Small model file/control | `--pb-small-model-file`, `--enable-small-model` | Google enables the small model by default; Parabricks makes it opt-in. |
| `--proposed_variants` | `--proposed-variants` | Candidate/importer VCF input. |
| `--make_examples_extra_args` for supported candidate/pileup/read controls | Matching explicit Parabricks flags such as `--vsc-*`, `--alt-aligned-pileup`, `--variant-caller`, `--min-*`, `--channel-*` | Parabricks exposes many make-examples options as first-class flags. |
| `--num_shards` | `--num-streams-per-gpu`, `--num-cpu-threads-per-stream`, or related Parabricks performance flags | Partial equivalent only; Parabricks partitions work around GPU streams and CPU threads; Prefer using "auto" parameters |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun deepvariant` flags. |
| Google DeepVariant options not listed here | No direct equivalent | Not exposed by current Parabricks docs for `pbrun deepvariant`. |

If a Google DeepVariant option is not listed above, assume there is no direct
`pbrun deepvariant` flag until the selected Parabricks version's tool reference
says otherwise.

## deepvariant Options Without DeepVariant Equivalents

| `pbrun deepvariant` option | Why it has no Google DeepVariant equivalent |
| --- | --- |
| `--disable-use-window-selector-model` | Parabricks inverse/compatibility control for window selector behavior. |
| `--keep-legacy-allele-counter-behavior` | Parabricks compatibility flag tied to a specific upstream behavior change. |
| `--max-read-size-512`, `--prealign-helper-thread`, `--filter-reads-too-long` | Parabricks read-size and helper-thread controls. |
| `--haploid-contigs` | Parabricks haploid-contig handling convenience. |
| `--pb-model-file`, `--pb-small-model-file` | Parabricks TensorRT model file inputs. |
| GPU stream, CPU thread, and memory controls | Parabricks GPU runtime tuning. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- BAM/CRAM and reference build match.
- Model/resource selection matches sequencing technology and assay.
- Output VCF/gVCF exists and is indexed when requested.
- Logs do not show model, reference mismatch, interval, mount, CUDA, or
  out-of-memory errors.

## Guardrails

- Do not use this as the end-to-end FASTQ pipeline unless the selected version
  documents that mode.
- Do not infer model type from filename alone.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_deepvariant.html>

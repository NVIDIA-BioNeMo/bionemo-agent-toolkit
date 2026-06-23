# Parabricks deepvariant_germline

Use this reference for NVIDIA Parabricks `pbrun deepvariant_germline` — end-to-end germline pipeline taking FASTQ or aligned BAM/CRAM through DeepVariant calling to VCF/gVCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm whether input is FASTQ or prepared BAM/CRAM for the selected
   pipeline mode.
3. Collect required inputs:
   - Reference FASTA.
   - Input FASTQ pairs or BAM/CRAM, depending on mode.
   - Output VCF/gVCF or output directory.
   - Model/resource settings required by the selected version.
4. Ask for read groups, known-sites/resources, intervals, temporary directory,
   and logs when relevant.
5. For alignment-only questions, route to
   `pbrun-fq2bam.md` and related FASTQ/BAM references; for runtime readiness, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun deepvariant_germline \
  --ref /workdir/<reference.fa> \
  <version-specific-input-options> \
  <version-specific-output-options>
```

Verify exact input mode, model, output, and preprocessing flags against the
selected version.

## BWA-MEM/GATK/DeepVariant Option Mapping

Use this mapping when translating a baseline BWA-MEM plus Google DeepVariant
germline workflow to `pbrun deepvariant_germline`. Parabricks v4.7.0 documents
this as an end-to-end pipeline with alignment, sorting, duplicate marking, and
DeepVariant calling.

| Baseline option | `pbrun deepvariant_germline` equivalent | Notes |
| --- | --- | --- |
| BWA-MEM/DeepVariant reference | `--ref` | Required reference FASTA path. |
| `bwa mem <read1> <read2>` | `--in-fq <read1> <read2>` | Paired FASTQ input. |
| Single-end FASTQ input | `--in-se-fq` | Parabricks single-end input. |
| `bwa mem -R <read-group>` | read group string after FASTQ inputs, or `--read-group-*` flags | Do not invent read group values. |
| `bwa mem -M`, `-Y`, `-C`, `-T`, `-B`, `-U`, `-L`, `-I`, `-K` | `--bwa-options` | Pass supported BWA-MEM options as one string. |
| GATK/Picard final sorted/marked BAM output | `--out-bam` | BAM after sorting/duplicate marking. |
| GATK/Picard `MarkDuplicates -M` | `--out-duplicate-metrics` | Duplicate metrics output. |
| GATK `BaseRecalibrator --known-sites` | `--knownSites` | Repeatable known-sites VCF input. |
| GATK `BaseRecalibrator --output` | `--out-recal-file` | BQSR report output. |
| DeepVariant `--output_vcf` | `--out-variants` | VCF/gVCF output. |
| DeepVariant `--model_type` | `--mode`, `--use-wes-model`, or selected model file | Parabricks documents short-read, PacBio, and ONT modes plus WES/model-file controls. |
| DeepVariant `--output_gvcf` / gVCF mode | `--gvcf` plus `--out-variants` | Output path extension controls VCF/gVCF naming. |
| DeepVariant custom model | `--pb-model-file`, `--pb-small-model-file` | Parabricks TensorRT model files. |
| DeepVariant `--proposed_variants` | `--proposed-variants` | Candidate/importer VCF input. |
| DeepVariant make-examples options | Matching explicit Parabricks flags such as `--vsc-*`, `--variant-caller`, `--min-*`, `--channel-*` | Parabricks exposes many make-examples options directly. |
| GATK/DeepVariant intervals | `--interval` or `--interval-file` | Parabricks separates inline intervals from interval files. |
| `--java-options`, DeepVariant/GATK engine flags not listed here | No direct equivalent | Not exposed by current Parabricks docs for this pipeline. |

If a baseline BWA-MEM, GATK, Picard, or DeepVariant option is not listed above,
assume there is no direct `pbrun deepvariant_germline` flag until the selected
Parabricks version's tool reference says otherwise.

## deepvariant_germline Options Without BWA-MEM/GATK/DeepVariant Equivalents

| `pbrun deepvariant_germline` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--disable-use-window-selector-model`, `--enable-small-model` | Parabricks compatibility/model behavior controls. |
| `--max-read-length`, `--min-read-length`, `--filter-flag`, `--skip-multiple-hits` | Parabricks pipeline read/SAM filtering controls. |
| `--align-only`, `--standalone-bqsr`, `--fix-mate` | Parabricks pipeline mode controls. |
| `--monitor-usage`, `--no-warnings` | Parabricks runtime reporting controls. |
| `--bwa-nstreams`, `--bwa-cpu-thread-pool`, `--bwa-primary-cpus`, `--bwa-normalized-queue-capacity` | Parabricks CPU/GPU alignment scheduling controls. |
| `--cigar-on-gpu`, `--gpuwrite`, `--gpuwrite-deflate-algo`, `--gpusort`, `--use-gds` | GPU-accelerated write/sort/storage controls. |
| `--memory-limit`, `--low-memory` | Parabricks host/GPU memory controls. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Input mode matches the command options.
- Reference, known resources, model/resources, and intervals match.
- Output VCF/gVCF or output directory is created.
- Logs do not show read group, model, reference, mount, CUDA, or memory errors.

## Guardrails

- Do not confuse this end-to-end/pipeline skill with standalone `deepvariant`.
- Do not invent read groups, model files, or known-sites resources.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_deepvariant_germline.html>

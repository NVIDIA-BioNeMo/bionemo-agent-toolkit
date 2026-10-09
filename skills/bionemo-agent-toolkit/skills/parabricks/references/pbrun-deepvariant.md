# Parabricks deepvariant

Collect aligned BAM or CRAM, reference FASTA, VCF destination, optional gVCF,
and model selection. Confirm assay and sequencing technology rather than
inferring a model from filenames. Ask about intervals, sample name, and
haploid or sex-chromosome handling when relevant; check model and interval
errors in the resulting run. Starting from raw FASTQ with an end-to-end goal
instead calls for [deepvariant_germline](pbrun-deepvariant_germline.md), unless
the selected standalone version explicitly supports that mode.

## Command Shape

```bash
pbrun deepvariant \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-variants /outputdir/<sample.vcf.gz>
```

## Gotchas

Parabricks DeepVariant `--gvcf` option actually produces both .g.vcf and .vcf files with the same name. Do not generate separate commands for gvcf and vcf outputs.

In **4.7.0**, combining `--run-partition`, `--proposed-variants`, and `--gvcf`
causes a warning and **`--run-partition` is ignored**; the manual also warns of
a substantial slowdown. If proposed candidates and gVCF output are required,
retain both and omit `--run-partition` from the revised command. Removing the
ignored flag makes the effective behavior explicit; it does not establish a
measured speedup. Increasing streams does not restore partition mode for this
combination. Keep `--num-streams-per-gpu` at its documented `auto` default
unless separate hardware-specific benchmarking supports an override.

## DeepVariant Option Mapping

Parabricks v4.7.0 documents DeepVariant as the
Google counterpart with TensorRT-accelerated model inference, but the CLI uses
Parabricks flag names and runtime controls.

| Google DeepVariant option | `pbrun deepvariant` equivalent | Notes |
| --- | --- | --- |
| `--reads` | `--in-bam` | Required BAM/CRAM input. |
| `--output_gvcf` / gVCF mode | `--gvcf` plus `--out-variants` | Output path extension controls whether the result is VCF/gVCF. |
| Small model file/control | `--pb-small-model-file`, `--enable-small-model` | Google enables the small model by default; Parabricks makes it opt-in. |
| `--proposed_variants` | `--proposed-variants` | Candidate/importer VCF input. |
| `--make_examples_extra_args` for supported candidate/pileup/read controls | Matching explicit Parabricks flags such as `--vsc-*`, `--alt-aligned-pileup`, `--variant-caller`, `--min-*`, `--channel-*` | Exposes many make-examples options as first-class flags. |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun deepvariant` flags. |
| Google DeepVariant options not listed here | No direct equivalent | Not documented for this tool. |
| — | `--keep-legacy-allele-counter-behavior` | Compatibility flag tied to a specific upstream behavior change. |
| — | `--max-read-size-512`, `--prealign-helper-thread`, `--filter-reads-too-long` | Read-size and helper-thread controls. |
| — | `--haploid-contigs` | Haploid-contig handling convenience. |
| — | `--pb-model-file`, `--pb-small-model-file` | TensorRT model file inputs. |

## Key References

- [Parabricks 4.7.0 DeepVariant manual](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_deepvariant.html)

# Parabricks collectmultiplemetrics

Collect aligned reads, reference FASTA, and an output QC directory. Establish
whether all metric families or a selected subset are needed; verify the
selection flags and filenames for that version. Check the directory for each
requested family and investigate reference-index or alignment-decoding errors.
Use project thresholds or explicitly stated assumptions for QC interpretation.
For WGS coverage alone, prefer [bammetrics](pbrun-bammetrics.md).

## Command Shape

```bash
pbrun collectmultiplemetrics \
  --ref /workdir/<reference.fa> \
  --bam /workdir/<input.bam> \
  --out-qc-metrics-dir /outputdir/<qc_metrics_dir> \
  --gen-all-metrics
```

## CollectMultipleMetrics Option Mapping

Parabricks v4.7.0 documents
`collectmultiplemetrics` as an accelerated GATK `CollectMultipleMetrics`
implementation, but the CLI is not one-to-one: GATK/Picard uses an output
basename and repeated `--PROGRAM` values, while Parabricks writes a metrics
directory and exposes dedicated `--gen-*` switches for each supported metric
family.

| GATK/Picard option | `pbrun collectmultiplemetrics` equivalent | Notes |
| --- | --- | --- |
| `--OUTPUT`, `-O` | `--out-qc-metrics-dir` | Not one-to-one: Picard uses an output basename; Parabricks uses an output directory for metric files. |
| Default/all metrics behavior | `--gen-all-metrics` | Use when the user wants every Parabricks-supported metric family. Verify exact generated files for the selected version. |
| `--PROGRAM CollectAlignmentSummaryMetrics` | `--gen-alignment` | Alignment summary metrics. |
| `--PROGRAM CollectInsertSizeMetrics` | `--gen-insert-size` | Insert-size metrics. |
| `--PROGRAM QualityScoreDistribution` | `--gen-quality-score` | Quality score distribution metrics. |
| `--PROGRAM MeanQualityByCycle` | `--gen-mean-quality-by-cycle` | Mean quality by cycle metrics. |
| `--PROGRAM CollectBaseDistributionByCycle` | `--gen-base-distribution-by-cycle` | Base distribution by cycle metrics. |
| `--PROGRAM CollectGcBiasMetrics` | `--gen-gc-bias` | GC bias metrics. |
| `--PROGRAM CollectSequencingArtifactMetrics` | `--gen-seq-artifact` | Sequencing artifact metrics. |
| `--PROGRAM CollectQualityYieldMetrics` | `--gen-quality-yield` | Quality yield metrics. |
| `--arguments_file` | No direct equivalent | GATK/Picard argument-file expansion is not documented. |
| `--ASSUME_SORTED`, `-AS` | No direct equivalent | Picard sort-order assumption is not exposed by current Parabricks docs. |
| `--DB_SNP` | No direct equivalent | Picard dbSNP resource option for some programs is not exposed by current Parabricks docs. |
| `--EXTRA_ARGUMENT` | No direct equivalent | Picard per-program extra arguments are not exposed by current Parabricks docs. |
| `--FILE_EXTENSION`, `-EXT` | No direct equivalent | Picard output extension customization is not exposed by current Parabricks docs. |
| `--IGNORE_SEQUENCE` | No direct equivalent | Picard ignored-sequence option is not exposed by current Parabricks docs. |
| `--INCLUDE_UNPAIRED`, `-UNPAIRED` | No direct equivalent | Picard sequencing-artifact option is not exposed by current Parabricks docs. |
| `--INTERVALS` | No direct equivalent | Picard interval restriction is not exposed by current Parabricks `collectmultiplemetrics` docs. |
| `--METRIC_ACCUMULATION_LEVEL`, `-LEVEL` | No direct equivalent | Picard accumulation-level control is not exposed by current Parabricks docs. |
| `--REF_FLAT` | No direct equivalent | Picard refFlat annotation input is not exposed by current Parabricks docs. |
| `--COMPRESSION_LEVEL` | No direct equivalent | GATK/Picard common output-compression option not exposed by current Parabricks docs. |
| `--CREATE_INDEX` | No direct equivalent | GATK/Picard common output-index option not exposed by current Parabricks docs. |
| `--QUIET` | No direct equivalent | GATK/Picard logging suppression is not documented. |
| `--showHidden` | No direct equivalent | Use `pbrun collectmultiplemetrics --help` or the selected Parabricks tool reference instead. |
| `--help`, `-h` | No direct equivalent | Use `pbrun collectmultiplemetrics --help` or the selected Parabricks tool reference instead. |
| — | `--bam-decompressor-threads` | BAM decompression worker count. Picard does not expose this tool-level decompressor thread flag. |
| — | `--num-gpus` | GPU count. Picard `CollectMultipleMetrics` is CPU-only. |

## Key References

- <https://gatk.broadinstitute.org/hc/en-us/articles/4413079276571-CollectMultipleMetrics-Picard>

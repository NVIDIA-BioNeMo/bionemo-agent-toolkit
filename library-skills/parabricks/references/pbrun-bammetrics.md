# Parabricks bammetrics

Collect the aligned BAM or CRAM, matching reference, and metrics destination.
Ask which intervals, minimum base and mapping qualities, and coverage cap the
analysis requires. Check reference-index, interval, and alignment-decoding errors.
Interpret the metrics using user-provided thresholds or stated assumptions;
coverage alone does not establish variant-calling quality. For multiple metric
families, use [collectmultiplemetrics](pbrun-collectmultiplemetrics.md).

## Command Shape

```bash
pbrun bammetrics \
  --ref /workdir/<reference.fa> \
  --bam /workdir/<input.bam> \
  --out-metrics-file /outputdir/<sample.bammetrics.txt>
```

## CollectWgsMetrics Option Mapping

Parabricks v4.7.0 documents `bammetrics` as an accelerated
GATK4 `CollectWgsMetrics` implementation, but the CLI is not one-to-one: many
Picard upper-case or underscore-separated flags become lower-case
hyphen-separated Parabricks flags, and some Picard/GATK common arguments are
not exposed by `pbrun bammetrics`.

| GATK/Picard option | `pbrun bammetrics` equivalent | Notes |
| --- | --- | --- |
| `--OUTPUT`, `-O` | `--out-metrics-file` | Required output metrics file path. |
| `--INTERVALS` | `--interval-file` | File-based interval restriction. The manual documents Picard-style, GATK-style, and BED interval files. |
| `--MINIMUM_BASE_QUALITY`, `-Q` | `--minimum-base-quality` | Same base-quality threshold role. |
| `--MINIMUM_MAPPING_QUALITY`, `-MQ` | `--minimum-mapping-quality` | Same mapping-quality threshold role. |
| `--COUNT_UNPAIRED` | `--count-unpaired` | Same role: count unpaired reads and paired reads with one end unmapped. |
| `--COVERAGE_CAP`, `-CAP` | `--coverage-cap` | Same coverage capping role. |
| `--arguments_file` | No direct equivalent | GATK/Picard argument-file expansion is not documented. |
| `--INCLUDE_BQ_HISTOGRAM` | No direct equivalent | Picard-specific metrics detail not exposed by current Parabricks docs. |
| `--LOCUS_ACCUMULATION_CAP` | No direct equivalent | Picard memory/accumulation cap not exposed by current Parabricks docs. |
| `--READ_LENGTH` | No direct equivalent | Picard theoretical sensitivity input not exposed by current Parabricks docs. |
| `--SAMPLE_SIZE` | No direct equivalent | Picard theoretical sensitivity sampling option not exposed by current Parabricks docs. |
| `--USE_FAST_ALGORITHM` | No direct equivalent | Picard algorithm-selection option not exposed by current Parabricks docs. |
| `--COMPRESSION_LEVEL` | No direct equivalent | GATK/Picard common output-compression option; `bammetrics` writes a metrics text file. |
| `--CREATE_INDEX` | No direct equivalent | GATK/Picard common output-index option not relevant to the metrics text output. |
| `--QUIET` | No direct equivalent | GATK/Picard logging suppression is not documented. |
| `--showHidden` | No direct equivalent | Use `pbrun bammetrics --help` or the selected Parabricks tool reference instead. |
| `--help`, `-h` | No direct equivalent | Use `pbrun bammetrics --help` or the selected Parabricks tool reference instead. |
| — | `--interval`, `-L` | Inline interval selector documented by Parabricks. Picard `CollectWgsMetrics` uses `--INTERVALS` for interval-list files. |
| — | `--num-threads` | Worker-thread count. Picard `CollectWgsMetrics` does not expose this tool-level thread flag. |

## Key References

- <https://gatk.broadinstitute.org/hc/en-us/articles/360037269351-CollectWgsMetrics-Picard>

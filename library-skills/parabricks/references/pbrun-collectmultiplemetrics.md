# Parabricks collectmultiplemetrics

Use this reference for NVIDIA Parabricks `pbrun collectmultiplemetrics` — accelerated CollectMultipleMetrics-style QC metrics on aligned BAM/CRAM.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Collect required inputs:
   - Reference FASTA path.
   - Input BAM or CRAM path.
   - Output QC metrics directory.
3. Ask whether the user wants all metrics or a selected subset.
4. Ask about temporary directory, log file, and optional version-specific metric
   flags when relevant.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun collectmultiplemetrics \
  --ref /workdir/<reference.fa> \
  --bam /workdir/<input.bam> \
  --out-qc-metrics-dir /outputdir/<qc_metrics_dir> \
  --gen-all-metrics
```

Verify exact metric-selection, threading, log, and temporary-directory flags
against the selected version.

## CollectMultipleMetrics Option Mapping

Use this mapping when translating a GATK/Picard `CollectMultipleMetrics`
command to `pbrun collectmultiplemetrics`. Parabricks v4.7.0 documents
`collectmultiplemetrics` as an accelerated GATK `CollectMultipleMetrics`
implementation, but the CLI is not one-to-one: GATK/Picard uses an output
basename and repeated `--PROGRAM` values, while Parabricks writes a metrics
directory and exposes dedicated `--gen-*` switches for each supported metric
family.

| GATK/Picard option | `pbrun collectmultiplemetrics` equivalent | Notes |
| --- | --- | --- |
| `--REFERENCE_SEQUENCE`, `-R` | `--ref` | Required reference FASTA path. |
| `--INPUT`, `-I` | `--bam` | Required input BAM/CRAM path. |
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
| `--TMP_DIR` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| `--VERBOSITY` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag, not Picard's log-level enum. |
| `--version` | `--version` | Same version-reporting role. |
| `--arguments_file` | No direct equivalent | GATK/Picard argument-file expansion is not documented for `pbrun collectmultiplemetrics`. |
| `--ASSUME_SORTED`, `-AS` | No direct equivalent | Picard sort-order assumption is not exposed by current Parabricks docs. |
| `--DB_SNP` | No direct equivalent | Picard dbSNP resource option for some programs is not exposed by current Parabricks docs. |
| `--EXTRA_ARGUMENT` | No direct equivalent | Picard per-program extra arguments are not exposed by current Parabricks docs. |
| `--FILE_EXTENSION`, `-EXT` | No direct equivalent | Picard output extension customization is not exposed by current Parabricks docs. |
| `--IGNORE_SEQUENCE` | No direct equivalent | Picard ignored-sequence option is not exposed by current Parabricks docs. |
| `--INCLUDE_UNPAIRED`, `-UNPAIRED` | No direct equivalent | Picard sequencing-artifact option is not exposed by current Parabricks docs. |
| `--INTERVALS` | No direct equivalent | Picard interval restriction is not exposed by current Parabricks `collectmultiplemetrics` docs. |
| `--METRIC_ACCUMULATION_LEVEL`, `-LEVEL` | No direct equivalent | Picard accumulation-level control is not exposed by current Parabricks docs. |
| `--REF_FLAT` | No direct equivalent | Picard refFlat annotation input is not exposed by current Parabricks docs. |
| `--STOP_AFTER` | No direct equivalent | Picard debugging option not exposed by current Parabricks docs. |
| `--COMPRESSION_LEVEL` | No direct equivalent | GATK/Picard common output-compression option not exposed by current Parabricks docs. |
| `--CREATE_INDEX` | No direct equivalent | GATK/Picard common output-index option not exposed by current Parabricks docs. |
| `--CREATE_MD5_FILE` | No direct equivalent | GATK/Picard common MD5 output option not exposed by current Parabricks docs. |
| `--GA4GH_CLIENT_SECRETS` | No direct equivalent | GATK/Picard cloud auth option not exposed by current Parabricks docs. |
| `--MAX_RECORDS_IN_RAM` | No direct equivalent | GATK/Picard common sort-memory option not exposed by current Parabricks docs. |
| `--QUIET` | No direct equivalent | GATK/Picard logging suppression is not documented for `pbrun collectmultiplemetrics`. |
| `--USE_JDK_DEFLATER` | No direct equivalent | GATK/Picard Java compression implementation option not applicable to Parabricks. |
| `--USE_JDK_INFLATER` | No direct equivalent | GATK/Picard Java decompression implementation option not applicable to Parabricks. |
| `--VALIDATION_STRINGENCY` | No direct equivalent | GATK/Picard SAM validation policy not exposed by current Parabricks docs. |
| `--showHidden` | No direct equivalent | Use `pbrun collectmultiplemetrics --help` or the selected Parabricks tool reference instead. |
| `--help`, `-h` | No direct equivalent | Use `pbrun collectmultiplemetrics --help` or the selected Parabricks tool reference instead. |

If a `CollectMultipleMetrics` option is not listed above, assume there is no
direct `pbrun collectmultiplemetrics` flag until the selected Parabricks
version's tool reference says otherwise.

## collectmultiplemetrics Options Without CollectMultipleMetrics Equivalents

These options are Parabricks performance, GPU, runtime, or filesystem wrapper
options and are not GATK/Picard `CollectMultipleMetrics` CLI options already
covered in the mapping above.

| `pbrun collectmultiplemetrics` option | Why it has no CollectMultipleMetrics equivalent |
| --- | --- |
| `--bam-decompressor-threads` | Parabricks BAM decompression worker count. Picard does not expose this tool-level decompressor thread flag. |
| `--num-gpus` | Parabricks GPU count. Picard `CollectMultipleMetrics` is CPU-only. |
| `--logfile` | Parabricks wrapper log file path. |
| `--x3` | Parabricks option to show full command-line arguments. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp` | Parabricks temporary-file retention. |
| `--no-seccomp-override` | Parabricks Docker/seccomp behavior. |
| `--preserve-file-symlinks` | Parabricks path handling behavior. |

## Validation

- Input BAM/CRAM and reference resolve inside the container.
- Output metrics directory exists and contains the requested metric families.
- Logs do not show reference-index, BAM/CRAM decode, mount, CUDA, or memory
  errors.
- QC interpretation is tied to user-provided thresholds or clearly stated
  assumptions.

## Guardrails

- Do not use this for WGS coverage-only metrics when `bammetrics` is the better
  fit.
- Do not invent which metric families are required for a project.
- Treat output filenames and metric-selection flags as version-sensitive.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_collectmultiplemetrics.html>
- <https://gatk.broadinstitute.org/hc/en-us/articles/4413079276571-CollectMultipleMetrics-Picard>

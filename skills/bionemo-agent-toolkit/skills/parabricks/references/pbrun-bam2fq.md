# Parabricks bam2fq

Collect the source alignment, output prefix, and reference for CRAM decoding.
Confirm separate paired files, single-end, or interleaved output; filenames
alone do not establish the read layout. Ask about compression, read group
splitting, QC filtering, and unmapped or orphan reads before choosing options.

Check FASTQ structure and sequence/quality lengths. For separate paired outputs,
compare record counts and corresponding read identifiers, allowing the expected
mate suffixes; account separately for orphan and unpaired outputs. Investigate
decode or compression errors. BAM-to-FASTQ conversion cannot guarantee recovery
of the original raw FASTQs.

## Command Shape

```bash
pbrun bam2fq \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-prefix /outputdir/<sample_prefix>
```

For BAM input, `--ref` may be optional depending on the version. For CRAM input,
keep the reference explicit. Check the tool reference before finalizing suffix,
read group splitting, QC filtering, temporary directory, or threading flags.

## SamToFastq Option Mapping

Parabricks v4.7.0 documents `bam2fq` as the GPU counterpart for
converting BAM/CRAM to FASTQ, but it uses an output prefix plus suffix flags
instead of Picard's individual output filenames.

| GATK/Picard option | `pbrun bam2fq` equivalent | Notes |
| --- | --- | --- |
| `--FASTQ`, `-F` | `--out-prefix` plus `--out-suffixF` | Builds first-in-pair output from prefix and suffix. |
| `--SECOND_END_FASTQ`, `-F2` | `--out-prefix` plus `--out-suffixF2` | Builds second-in-pair output from prefix and suffix. |
| `--UNPAIRED_FASTQ`, `-FU` | `--out-prefix` plus `--out-suffixS` | Single-end/unpaired output suffix. |
| `--UNPAIRED_FASTQ` / orphan handling | `--out-suffixO`, `--out-suffixO2` | Can emit orphan first/second reads with separate suffixes. |
| `--REFERENCE_SEQUENCE`, `-R` | `--ref` | Required for CRAM input; optional for BAM depending on version. |
| `--READ_GROUP_TAG` | `--rg-tag` | The manual documents `PU` or `ID` for splitting reads into different FASTQ files. |
| `--INCLUDE_NON_PF_READS false` | `--remove-qc-failure` | Partial equivalent: Parabricks removes reads marked as QC failure when set. |

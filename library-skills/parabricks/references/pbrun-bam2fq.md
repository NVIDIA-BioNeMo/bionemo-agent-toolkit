# Parabricks bam2fq

Use this reference for NVIDIA Parabricks `pbrun bam2fq` — converting aligned BAM/CRAM back to FASTQ output.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Collect required inputs:
   - Input BAM or CRAM path.
   - Output FASTQ path or output prefix/directory expected by the selected
     version.
   - Reference FASTA when CRAM input or the selected version requires it.
3. Ask whether reads are paired-end, single-end, interleaved, or should be
   emitted as separate FASTQ files.
4. Ask whether the user needs output compression, read group filtering, or
   unmapped read handling, then verify version-specific support.
5. For runtime readiness or installation questions, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun bam2fq \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-prefix /outputdir/<sample_prefix>
```

For BAM input, `--ref` may be optional depending on the version. For CRAM input,
keep the reference explicit. Check the tool reference before finalizing suffix,
read group splitting, QC filtering, temporary directory, or threading flags.

## SamToFastq Option Mapping

Use this mapping when translating a GATK/Picard `SamToFastq` command to
`pbrun bam2fq`. Parabricks v4.7.0 documents `bam2fq` as the GPU counterpart for
converting BAM/CRAM to FASTQ, but it uses an output prefix plus suffix flags
instead of Picard's individual output filenames.

| GATK/Picard option | `pbrun bam2fq` equivalent | Notes |
| --- | --- | --- |
| `--INPUT`, `-I` | `--in-bam` | Required BAM/CRAM input path. |
| `--FASTQ`, `-F` | `--out-prefix` plus `--out-suffixF` | Parabricks builds first-in-pair output from prefix and suffix. |
| `--SECOND_END_FASTQ`, `-F2` | `--out-prefix` plus `--out-suffixF2` | Parabricks builds second-in-pair output from prefix and suffix. |
| `--UNPAIRED_FASTQ`, `-FU` | `--out-prefix` plus `--out-suffixS` | Single-end/unpaired output suffix. |
| `--UNPAIRED_FASTQ` / orphan handling | `--out-suffixO`, `--out-suffixO2` | Parabricks can emit orphan first/second reads with separate suffixes. |
| `--REFERENCE_SEQUENCE`, `-R` | `--ref` | Required for CRAM input; optional for BAM depending on version. |
| `--READ_GROUP_TAG` | `--rg-tag` | Parabricks documents `PU` or `ID` for splitting reads into different FASTQ files. |
| `--INCLUDE_NON_PF_READS false` | `--remove-qc-failure` | Partial equivalent: Parabricks removes reads marked as QC failure when set. |
| `--TMP_DIR` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| `--VERBOSITY` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag. |
| `--version` | `--version` | Same version-reporting role. |
| `--arguments_file`, `--VALIDATION_STRINGENCY`, Picard compression/common flags | No direct equivalent | Not exposed by current Parabricks docs. |

If a Picard `SamToFastq` option is not listed above, assume there is no direct
`pbrun bam2fq` flag until the selected Parabricks version's tool reference says
otherwise.

## bam2fq Options Without SamToFastq Equivalents

| `pbrun bam2fq` option | Why it has no SamToFastq equivalent |
| --- | --- |
| `--num-threads` | Parabricks worker-thread count. |
| `--logfile` | Parabricks wrapper log file path. |
| `--x3` | Parabricks option to show full command-line arguments. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp` | Parabricks temporary-file retention. |
| `--no-seccomp-override` | Parabricks Docker/seccomp behavior. |
| `--preserve-file-symlinks` | Parabricks path handling behavior. |

## Validation

- BAM/CRAM input resolves inside the container.
- CRAM runs have the required reference available.
- Output FASTQ files are created where expected.
- Paired-end outputs preserve pairing expectations.
- Logs do not show BAM/CRAM decode, reference, mount, compression, CUDA, or
  out-of-memory errors.

## Guardrails

- Do not assume BAM-to-FASTQ reconstructs original raw FASTQs perfectly.
- Do not infer paired-end output mode from filename alone.
- Do not invent output prefixes or compression settings.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_bam2fq.html>

# Parabricks bqsr

Use this reference for NVIDIA Parabricks `pbrun bqsr` — generating a BQSR recalibration report from aligned BAM/CRAM reads.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Collect required inputs:
   - Reference FASTA path.
   - Input BAM or CRAM path.
   - One or more known-sites VCF paths.
   - Output recalibration report path.
3. Ask about optional interval files, temporary directory, logs, and GPU count
   only when relevant.
4. If the user wants to modify BAM qualities after report generation, route the
   next step to `pbrun-applybqsr.md`.
5. For runtime readiness or installation questions, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun bqsr \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --knownSites /workdir/<known-sites.vcf.gz> \
  --out-recal-file /outputdir/<sample.recal.txt>
```

Verify exact known-sites, interval, threading, logging, and temporary-directory
flags against the selected version before finalizing.

## BaseRecalibrator Option Mapping

Use this mapping when translating a GATK `BaseRecalibrator` command to
`pbrun bqsr`. Parabricks v4.7.0 documents `bqsr` as the GATK4 counterpart for
generating a recalibration report, but shortens several GATK option names.

| GATK option | `pbrun bqsr` equivalent | Notes |
| --- | --- | --- |
| `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `--input`, `-I` | `--in-bam` | Required BAM/CRAM input path. |
| `--known-sites` | `--knownSites` | Required known-sites VCF; can be repeated. |
| `--output`, `-O` | `--out-recal-file` | Required output recalibration report. |
| `--intervals`, `-L` | `--interval` or `--interval-file` | Parabricks separates inline intervals from interval files. |
| `--interval-padding`, `-ip` | `--interval-padding`, `-ip` | Same padding role. |
| `--tmp-dir` / `--TMP_DIR` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| `--verbosity` / `--VERBOSITY` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag. |
| `--version` | `--version` | Same version-reporting role. |
| `--java-options` | No direct equivalent | Java heap/runtime settings do not apply to the Parabricks containerized GPU tool. |
| `--arguments_file`, GATK engine/read-filter flags, covariate-control flags | No direct equivalent | Not exposed by current Parabricks docs. |

If a GATK `BaseRecalibrator` option is not listed above, assume there is no
direct `pbrun bqsr` flag until the selected Parabricks version's tool reference
says otherwise.

## bqsr Options Without BaseRecalibrator Equivalents

| `pbrun bqsr` option | Why it has no BaseRecalibrator equivalent |
| --- | --- |
| `--num-gpus` | Parabricks GPU count. |
| `--logfile` | Parabricks wrapper log file path. |
| `--x3` | Parabricks option to show full command-line arguments. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp` | Parabricks temporary-file retention. |
| `--no-seccomp-override` | Parabricks Docker/seccomp behavior. |
| `--preserve-file-symlinks` | Parabricks path handling behavior. |

## Validation

- Reference, BAM/CRAM, and known-sites paths resolve inside the container.
- Known-sites files match the reference build.
- Output recalibration report is created.
- Logs do not show reference mismatch, known-sites index, interval, mount, CUDA,
  or out-of-memory errors.

## Guardrails

- Do not invent known-sites files or reference builds.
- Do not present the recalibration report as an updated BAM; applying it is a
  separate step handled by `applybqsr`.
- Ask whether BQSR is appropriate for the organism/reference when the user is
  not working with a standard human reference workflow.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_bqsr.html>

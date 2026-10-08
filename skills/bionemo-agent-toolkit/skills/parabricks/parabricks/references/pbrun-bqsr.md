# Parabricks bqsr

Use this reference for NVIDIA Parabricks `pbrun bqsr` — generating a BQSR recalibration report from aligned BAM/CRAM reads.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

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

Use this when translating GATK `BaseRecalibrator` to `pbrun bqsr`. Shared
reference, BAM, and interval mappings for `bqsr` are in
[shared-options.md](shared-options.md).

| GATK option | `pbrun bqsr` equivalent | Notes |
| --- | --- | --- |
| `--known-sites` | `--knownSites` | Required known-sites VCF; can be repeated. |
| `--output`, `-O` | `--out-recal-file` | Required recalibration report output. |
| `--arguments_file`, GATK engine/read-filter flags, covariate-control flags | No direct equivalent | Not exposed in current docs. |

If a GATK `BaseRecalibrator` option is not listed here or in
[shared-options.md](shared-options.md) for `bqsr`, assume no direct flag until
the selected release's tool reference confirms it.

Parabricks execution and wrapper controls for `bqsr` are in
[shared-options.md](shared-options.md) and
[command-conventions.md](command-conventions.md#shared-wrapper-controls).

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

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/bqsr>

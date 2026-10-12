# Parabricks applybqsr

Use this reference for NVIDIA Parabricks `pbrun applybqsr` — applying a BQSR recalibration report to aligned BAM/CRAM reads.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the user already has a BQSR recalibration report. If not, route to
   `pbrun-bqsr.md`.
3. Collect required inputs:
   - Reference FASTA path.
   - Input BAM or CRAM path.
   - Input recalibration report path.
   - Output BAM or CRAM path.
4. Ask about optional interval files, temporary directory, logs, and GPU count
   only when relevant.
5. For runtime readiness or installation questions, use
   `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun applybqsr \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --in-recal-file /workdir/<input.recal.txt> \
  --out-bam /outputdir/<recalibrated.bam>
```

Verify option names against the tool reference for the selected version before
finalizing interval, threading, logging, or temporary-directory flags.

## ApplyBQSR Option Mapping

Use this when translating GATK `ApplyBQSR` to `pbrun applybqsr`. Shared
alignment and interval mappings for `applybqsr` are in
[shared-options.md](shared-options.md).

| GATK option | `pbrun applybqsr` equivalent | Notes |
| --- | --- | --- |
| `--bqsr-recal-file` | `--in-recal-file` | Recalibration report from `pbrun bqsr` or GATK `BaseRecalibrator`. |
| `--arguments_file` | No direct equivalent | Argument-file expansion is not documented for `pbrun applybqsr`. |
| `--read-index`, `--read-validation-stringency`, common GATK engine flags | No direct equivalent | GATK engine controls are not exposed in current docs. |

If a GATK `ApplyBQSR` option is not listed here or in
[shared-options.md](shared-options.md) for `applybqsr`, assume no direct flag
until the selected release's tool reference confirms it.

Parabricks execution and wrapper controls for `applybqsr` are in
[shared-options.md](shared-options.md) and
[command-conventions.md](command-conventions.md#shared-wrapper-controls).

## Validation

- Reference, BAM/CRAM, and recalibration report paths resolve inside the
  container.
- Output BAM/CRAM is created in the mounted output directory.
- Logs do not show reference mismatch, missing recalibration report, interval,
  Docker mount, CUDA, or out-of-memory errors.
- The output is used downstream instead of the original unrecalibrated input.

## Guardrails

- Do not generate a recalibration report here; use `bqsr` for that step.
- Do not apply a recalibration report from a different reference/sample unless
  the user explicitly confirms compatibility.
- Do not invent intervals, output names, or runtime estimates.

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/applybqsr>

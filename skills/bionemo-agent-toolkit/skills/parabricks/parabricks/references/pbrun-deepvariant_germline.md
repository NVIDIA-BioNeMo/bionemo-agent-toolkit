# Parabricks deepvariant_germline

Use this reference for NVIDIA Parabricks `pbrun deepvariant_germline` — end-to-end germline pipeline taking FASTQ or aligned BAM/CRAM through DeepVariant calling to VCF/gVCF.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

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

Use this when translating BWA-MEM plus Google DeepVariant germline workflows to
`pbrun deepvariant_germline`. Preprocessing and shared DeepVariant mappings for
`deepvariant_germline` are in [shared-options.md](shared-options.md). The small
model is enabled by default; use `--disable-small-model` to turn it off. For WES,
pass `--disable-small-model` with `--use-wes-model` to match Google DeepVariant.

| Baseline option | `pbrun deepvariant_germline` equivalent | Notes |
| --- | --- | --- |
| DeepVariant `--proposed_variants` | `--proposed-variants` | Candidate/importer VCF input. |
| DeepVariant make-examples options | Matching explicit Parabricks flags such as `--vsc-*`, `--variant-caller`, `--min-*`, `--channel-*` | Parabricks exposes many make-examples options directly. |
| `--java-options`, DeepVariant/GATK engine flags not listed here | No direct equivalent | Not exposed for this pipeline in current docs. |

If a baseline option is not listed here or in [shared-options.md](shared-options.md)
for `deepvariant_germline`, assume no direct flag until the selected release's
tool reference confirms it.

## deepvariant_germline Options Without BWA-MEM/GATK/DeepVariant Equivalents

Shared pipeline and GPU controls for `deepvariant_germline` are in
[shared-options.md](shared-options.md). BWA tuning is in [performance.md](performance.md).

| `pbrun deepvariant_germline` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--disable-use-window-selector-model`, `--disable-small-model` | Model/compatibility controls; small model is on by default. |

Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

## Validation

- Input mode matches the command options.
- Reference, known resources, model/resources, and intervals match.
- Output VCF/gVCF or output directory is created.
- Logs do not show read group, model, reference, mount, CUDA, or memory errors.

## Guardrails

- Do not confuse this end-to-end/pipeline skill with standalone `deepvariant`.
- Do not invent read groups, model files, or known-sites resources.

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/deepvariant_germline>

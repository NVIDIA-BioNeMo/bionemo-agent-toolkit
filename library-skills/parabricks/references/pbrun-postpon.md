# Parabricks postpon

Use this reference for NVIDIA Parabricks `pbrun postpon` — pangenome-aware panel-of-normals post-processing for somatic variant workflows.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the upstream pangenome-aware workflow that produced the inputs.
3. Collect required inputs for the selected version:
   - Upstream intermediate files.
   - Reference and pangenome graph/resource bundle if required.
   - Output VCF/gVCF or output directory.
4. Ask whether outputs are intended for evaluation, downstream annotation, or
   final reporting.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun postpon \
  <version-specific-input-options> \
  <version-specific-output-options>
```

Verify exact intermediate input, graph resource, and output flags against the
selected version.

## Panel-of-Normals Postprocessing Option Mapping

Use this mapping when translating panel-of-normals annotation around GATK
Mutect2 to `pbrun postpon`. Parabricks documents `postpon` as the postprocess
of calling `--pon` in `mutectcaller`, annotating variants based on a PON file.

| Baseline option | `pbrun postpon` equivalent | Notes |
| --- | --- | --- |
| Mutect2 output VCF to annotate | `--in-vcf` | Required input VCF. |
| Mutect2/GATK panel-of-normals VCF | `--in-pon-file` | Required PON VCF.GZ with tabix index. |
| Annotated VCF output | `--out-vcf` | Required output annotated VCF. |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun postpon` flags. |
| GATK engine/common flags | No direct equivalent | Not exposed by current Parabricks docs for `postpon`. |

If a PON-related GATK option is not listed above, assume there is no direct
`pbrun postpon` flag until the selected Parabricks version's tool reference
says otherwise.

## postpon Options Without Panel-of-Normals Equivalents

| `pbrun postpon` option | Why it has no direct GATK equivalent |
| --- | --- |
| PON annotation handoff from `mutectcaller` | Parabricks decomposes PON handling into `prepon`, `mutectcaller`, and `postpon`. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Upstream intermediate files match the expected pangenome workflow.
- Output VCF/gVCF or output directory exists.
- Logs do not show missing intermediate files, graph resource, reference, mount,
  CUDA, or memory errors.

## Guardrails

- Do not use for standard linear-reference variant post-processing.
- Do not invent upstream intermediate file compatibility.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_postpon.html>

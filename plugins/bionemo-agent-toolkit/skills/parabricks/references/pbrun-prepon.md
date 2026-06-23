# Parabricks prepon

Use this reference for NVIDIA Parabricks `pbrun prepon` — pangenome-aware panel-of-normals preprocessing for somatic variant workflows.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the user is preparing inputs for a pangenome-aware workflow.
3. Collect required inputs for the selected version:
   - Reference and pangenome graph/resource bundle.
   - Input reads/alignments or intermediate files.
   - Output directory or intermediate output paths.
4. Ask which downstream tool will consume the output:
   `pangenome_germline`, `pangenome_aware_deepvariant`, or another workflow.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun prepon \
  <version-specific-input-options> \
  <version-specific-output-options>
```

Verify exact resource and intermediate file flags against the selected version.

## Panel-of-Normals Preprocessing Option Mapping

Use this mapping when translating panel-of-normals setup around GATK Mutect2 to
`pbrun prepon`. Parabricks documents `prepon` as a preprocessing step for PON
use with `mutectcaller`, rather than a direct standalone GATK tool clone.

| Baseline option | `pbrun prepon` equivalent | Notes |
| --- | --- | --- |
| Mutect2 `--panel-of-normals`, `--pon` input VCF | `--in-pon-file` | Input PON VCF.GZ with tabix index when documented. |
| Generated PON index/intermediate | Default/version-specific `prepon` output | Verify output behavior in the selected version; some docs show no explicit output flag. |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun prepon` flags. |
| GATK `CreateSomaticPanelOfNormals` options | No direct equivalent | `prepon` preprocesses an existing PON resource for Parabricks use. |
| GATK engine/common flags | No direct equivalent | Not exposed by current Parabricks docs for `prepon`. |

If a PON-related GATK option is not listed above, assume there is no direct
`pbrun prepon` flag until the selected Parabricks version's tool reference says
otherwise.

## prepon Options Without Panel-of-Normals Equivalents

| `pbrun prepon` option | Why it has no direct GATK equivalent |
| --- | --- |
| Version-specific PON index/intermediate behavior | Parabricks creates resources consumed by `mutectcaller`. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- Required graph/reference resources are complete.
- Output intermediate files exist and match the downstream workflow.
- Logs do not show graph resource, reference, mount, CUDA, or memory errors.

## Guardrails

- Do not use for standard linear-reference preprocessing.
- Do not invent downstream compatibility; ask which pangenome workflow follows.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_prepon.html>

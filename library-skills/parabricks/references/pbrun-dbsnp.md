# Parabricks dbsnp

Use this reference for NVIDIA Parabricks `pbrun dbsnp` — dbSNP annotation of an input VCF against a dbSNP resource VCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the task is dbSNP annotation or processing of existing variant data.
   If the user needs to call variants from reads, route to
   variant-calling references in this skill.
3. Collect required inputs for the selected version:
   - Input VCF path.
   - dbSNP/resource VCF path.
   - Reference FASTA or reference build if required.
   - Output VCF path.
4. Ask about compression, indexing, intervals, and logs only when relevant.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun dbsnp \
  <version-specific-input-options> \
  <version-specific-dbsnp-resource-options> \
  <version-specific-output-options>
```

Verify exact input, dbSNP resource, reference, and output flags against the
selected version.

## dbSNP Annotation Option Mapping

Use this mapping when translating a VCF dbSNP annotation step to `pbrun dbsnp`.
Parabricks v4.7.0 documents `dbsnp` as a VCF annotation tool using a dbSNP VCF
resource.

| Baseline option | `pbrun dbsnp` equivalent | Notes |
| --- | --- | --- |
| Input VCF | `--in-vcf` | Required input VCF. |
| dbSNP/resource VCF | `--in-dbsnp-file` | Required dbSNP VCF.GZ with tabix index. |
| Output annotated VCF | `--out-vcf` | Required output VCF. |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun dbsnp` flags. |
| GATK/BCFtools annotation flags not listed here | No direct equivalent | Not exposed by current Parabricks docs for `dbsnp`. |

If a VCF annotation option is not listed above, assume there is no direct
`pbrun dbsnp` flag until the selected Parabricks version's tool reference says
otherwise.

## dbsnp Options Without dbSNP Annotation Equivalents

| `pbrun dbsnp` option | Why it has no direct baseline equivalent |
| --- | --- |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |

## Validation

- Input VCF and dbSNP resource paths resolve inside the container.
- dbSNP resource matches the same reference build as the input VCF.
- Output VCF exists and is indexed when requested.
- Logs do not show malformed VCF, resource mismatch, missing index, mount,
  CUDA, or memory errors.

## Guardrails

- Do not invent dbSNP resource paths or builds.
- Do not use this skill for BAM/FASTQ variant calling.
- Do not assume annotation semantics without checking the selected version docs.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_dbsnp.html>

# Parabricks indexgvcf

Use this reference for NVIDIA Parabricks `pbrun indexgvcf` — indexing a GVCF for downstream joint genotyping or annotation.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the input is a GVCF that needs indexing.
3. Collect required inputs:
   - Input GVCF path.
   - Output index path or output directory expected by the selected version.
4. Ask whether the output will be consumed by `genotypegvcf` or another tool.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun indexgvcf \
  <version-specific-gvcf-input-options> \
  <version-specific-index-output-options>
```

Verify exact input and index output flags against the selected version.

## IndexFeatureFile Option Mapping

Use this mapping when translating a GATK `IndexFeatureFile` command for GVCF
indexing to `pbrun indexgvcf`. Parabricks v4.7.0 documents `indexgvcf` as
creating a `.tbi` index by appending `.tbi` to the input GVCF filename.

| GATK option | `pbrun indexgvcf` equivalent | Notes |
| --- | --- | --- |
| `--input`, `-I` | `--input` | Required gVCF/gVCF.GZ input. |
| Implicit output index path | Implicit `.tbi` next to input | Parabricks docs state the output name is determined by appending `.tbi` to the input GVCF filename. |
| `--TMP_DIR` / `--tmp-dir` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| `--verbosity` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag. |
| `--version` | `--version` | Same version-reporting role. |
| GATK output path override, cloud flags, `--arguments_file`, and Java options | No direct equivalent | Not exposed by current Parabricks docs for `indexgvcf`. |

If a GATK `IndexFeatureFile` option is not listed above, assume there is no
direct `pbrun indexgvcf` flag until the selected Parabricks version's tool
reference says otherwise.

## indexgvcf Options Without IndexFeatureFile Equivalents

| `pbrun indexgvcf` option | Why it has no GATK IndexFeatureFile equivalent |
| --- | --- |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |

## Validation

- GVCF input resolves inside the container.
- Output index file is created.
- Index path is accessible to the downstream tool.
- Logs do not show malformed GVCF, mount, CUDA, or memory errors.

## Guardrails

- Do not use this for ordinary VCF indexing unless the selected version
  documents that use.
- Do not run genotyping here; route to `pbrun-genotypegvcf.md`.
- Do not invent output index suffixes; verify version behavior.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_indexgvcf.html>

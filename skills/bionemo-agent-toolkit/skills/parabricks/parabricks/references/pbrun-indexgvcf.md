# Parabricks indexgvcf

Use this reference for NVIDIA Parabricks `pbrun indexgvcf` — indexing a GVCF for downstream joint genotyping or annotation.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the input is a GVCF that needs indexing.
3. Collect required inputs:
   - Input GVCF path, and whether its directory is writable inside the container.
   - Where the index must end up. There is no documented output-path option; the
     `.tbi` is written next to the input (see Output Naming below).
4. Ask whether the output will be consumed by `genotypegvcf` or another tool.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/results:/results \
  --workdir /results \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun indexgvcf \
  --input /results/<sample.g.vcf.gz>
```

The GVCF must be on a writable mount because the index is created beside it.
Verify exact flags against the selected version.

## Output Naming and Read-Only Inputs

- The index name is the input filename with `.tbi` appended
  (`sample.g.vcf.gz` → `sample.g.vcf.gz.tbi`). Do not use or invent an `--out`
  flag; none is documented for `indexgvcf`.
- If the original GVCF is on a read-only mount (for example `/data`), indexing it
  in place fails. Index a **writable copy** instead and leave the original
  untouched.
- Before copying, check for existing destination files so nothing is silently
  overwritten:

  ```bash
  [ ! -e /results/<sample.g.vcf.gz> ] && [ ! -e /results/<sample.g.vcf.gz>.tbi ] \
    || { echo "destination exists; choose another name or confirm overwrite"; exit 1; }
  cp -p /data/<sample.g.vcf.gz> /results/<sample.g.vcf.gz>
  ```

  Ask the user before replacing an existing GVCF or `.tbi`, and make clear the
  commands are a plan until the user runs them.

## IndexFeatureFile Option Mapping

Use this mapping when translating a GATK `IndexFeatureFile` command for GVCF
indexing to `pbrun indexgvcf`. Parabricks documents `indexgvcf` as
creating a `.tbi` index by appending `.tbi` to the input GVCF filename.

| GATK option | `pbrun indexgvcf` equivalent | Notes |
| --- | --- | --- |
| `--input`, `-I` | `--input` | Required gVCF/gVCF.GZ input. |
| Implicit output index path | Implicit `.tbi` next to input | Parabricks docs state the output name is determined by appending `.tbi` to the input GVCF filename. |
| GATK output path override, cloud flags, `--arguments_file`, and Java options | No direct equivalent | Not exposed by current Parabricks docs for `indexgvcf`. |

If a GATK `IndexFeatureFile` option is not listed above, assume there is no
direct `pbrun indexgvcf` flag until the selected Parabricks version's tool
reference says otherwise.

## indexgvcf Options Without IndexFeatureFile Equivalents

| `pbrun indexgvcf` option | Why it has no GATK IndexFeatureFile equivalent |
| --- | --- |


Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

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
- Do not overwrite an existing GVCF or `.tbi`, and do not index a read-only
  original in place; use a writable copy after checking the destination.

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/indexgvcf>

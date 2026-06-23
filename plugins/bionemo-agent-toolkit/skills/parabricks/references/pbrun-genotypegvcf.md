# Parabricks genotypegvcf

Use this reference for NVIDIA Parabricks `pbrun genotypegvcf` — joint genotyping of one or more GVCFs into a multi-sample VCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the input is GVCF. If the user has BAM/CRAM or FASTQ, route to
   variant-calling references in this skill first.
3. Collect required inputs:
   - Input GVCF path or cohort input expected by the selected version.
   - Reference FASTA if required.
   - Output VCF path.
4. Ask about intervals, sample/cohort structure, temporary directory, and logs
   only when relevant.
5. If the GVCF is not indexed and the workflow requires an index, route to
   `pbrun-indexgvcf.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun genotypegvcf \
  <version-specific-gvcf-input-options> \
  <version-specific-output-options>
```

Verify exact GVCF input, reference, interval, and output flags against the
selected version.

## GenotypeGVCFs Option Mapping

Use this mapping when translating a GATK `GenotypeGVCFs` command to
`pbrun genotypegvcf`. Parabricks v4.7.0 documents this as an accelerated
GATK GenotypeGVCFs counterpart for converting one or more gVCF inputs to VCF.

| GATK option | `pbrun genotypegvcf` equivalent | Notes |
| --- | --- | --- |
| `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `--variant`, `-V` | `--in-gvcf` | Required input gVCF/gVCF.GZ. |
| `--output`, `-O` | `--out-vcf` | Required output VCF. |
| `--TMP_DIR` / `--tmp-dir` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| `--verbosity` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag. |
| `--version` | `--version` | Same version-reporting role. |
| GATK intervals, annotation controls, cloud flags, `--arguments_file`, and Java options | No direct equivalent | Not exposed by current Parabricks docs for `genotypegvcf`. |

If a GATK `GenotypeGVCFs` option is not listed above, assume there is no direct
`pbrun genotypegvcf` flag until the selected Parabricks version's tool
reference says otherwise.

## genotypegvcf Options Without GenotypeGVCFs Equivalents

| `pbrun genotypegvcf` option | Why it has no GATK GenotypeGVCFs equivalent |
| --- | --- |
| `--num-threads` | Parabricks worker-thread count. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |

## Validation

- GVCF input resolves inside the container.
- Required GVCF index and reference files exist.
- Output VCF exists and is indexed when requested.
- Logs do not show malformed GVCF, missing index, reference mismatch, mount,
  CUDA, or memory errors.

## Guardrails

- Do not present `genotypegvcf` as a read-level variant caller.
- Do not invent cohort/sample assumptions.
- Treat multi-sample behavior and input list formats as version-sensitive.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_genotypegvcf.html>

# Parabricks haplotypecaller

Use this reference for NVIDIA Parabricks `pbrun haplotypecaller` — GATK HaplotypeCaller-style germline variant calling from aligned BAM/CRAM to VCF or gVCF.

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the user has aligned BAM/CRAM input. If starting from FASTQ and
   wanting a pipeline, consider `pbrun-germline.md`.
3. Collect required inputs:
   - Reference FASTA.
   - Input BAM/CRAM.
   - Output VCF or gVCF.
4. Ask for intervals, ploidy, emit mode, gVCF mode, and logs only when relevant.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun haplotypecaller \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-variants /outputdir/<sample.vcf.gz>
```

Verify exact VCF/gVCF, interval, ploidy, and output flags against the selected
version.

## HaplotypeCaller Option Mapping

Use this mapping when translating a GATK `HaplotypeCaller` command to
`pbrun haplotypecaller`. Parabricks v4.7.0 documents this as a
GPU-accelerated HaplotypeCaller counterpart, but the CLI is not one-to-one:
some GATK flags are direct Parabricks flags, while other supported original
HaplotypeCaller options must be passed through `--haplotypecaller-options`.

| GATK option | `pbrun haplotypecaller` equivalent | Notes |
| --- | --- | --- |
| `--reference`, `-R` | `--ref` | Required reference FASTA path. |
| `--input`, `-I` | `--in-bam` | Required BAM/CRAM input. |
| `--output`, `-O` | `--out-variants` | Required VCF/gVCF output. |
| `--bqsr-recal-file` via prior `ApplyBQSR` | `--in-recal-file` | Optional BQSR report input; Parabricks applies updated qualities internally. |
| `--intervals`, `-L` | `--interval` or `--interval-file` | Parabricks separates inline intervals from interval files. |
| `--exclude-intervals`, `-XL` | `--exclude-intervals`, `-XL` | Same exclude-interval role. |
| `--interval-padding`, `-ip` | `--interval-padding`, `-ip` | Same padding role. |
| `--emit-ref-confidence GVCF` | `--gvcf` | Generate gVCF output. |
| `--sample-ploidy` | `--ploidy` | Parabricks currently documents haploid and diploid support. |
| `--annotation`, `-A`; `--annotations-to-exclude`, `-AX`; `--output-mode`; selected assembly/calling knobs | `--haplotypecaller-options` | Pass supported original HaplotypeCaller options as one string. |
| `--annotation-group`, `-G` | `--annotation-group`, `-G` | Supported annotation group output. |
| `--gvcf-gq-bands`, `-GQB` | `--gvcf-gq-bands`, `-GQB` | Reference-confidence GQ bands. |
| `--dont-use-soft-clipped-bases` | `--dont-use-soft-clipped-bases` | Same role. |
| `--minimum-mapping-quality` | `--minimum-mapping-quality` | Same read filtering role. |
| `--mapping-quality-threshold-for-genotyping` | `--mapping-quality-threshold-for-genotyping` | Same genotyping threshold role. |
| `--min-base-quality-score` | `--min-base-quality-score` | Same base quality role. |
| `--max-alternate-alleles` | `--max-alternate-alleles` | Same genotyping cap role. |
| `--disable-read-filter` | `--disable-read-filter` | Limited to filters documented by the selected Parabricks version. |
| `--TMP_DIR` / `--tmp-dir` | `--tmp-dir` | Same temporary-directory role, but Parabricks treats it as a wrapper/runtime path. |
| `--verbosity` | `--verbose` | Partial equivalent only: Parabricks exposes a boolean verbose flag. |
| `--version` | `--version` | Same version-reporting role. |
| `--native-pair-hmm-threads`, `--java-options`, GATK engine/common flags | No direct equivalent | Not exposed as GATK engine controls by current Parabricks docs. |

If a GATK `HaplotypeCaller` option is not listed above, assume there is no
direct `pbrun haplotypecaller` flag until the selected Parabricks version's
tool reference says otherwise.

## haplotypecaller Options Without HaplotypeCaller Equivalents

| `pbrun haplotypecaller` option | Why it has no GATK HaplotypeCaller equivalent |
| --- | --- |
| `--htvc-bam-output` | Parabricks output for assembled haplotypes. |
| `--htvc-alleles` | Parabricks force-call VCF input naming for the HTVC path. |
| `--rna` | Parabricks RNA-optimized mode. |
| `--adaptive-pruning` | Parabricks-exposed graph pruning control. |
| `--force-call-filtered-alleles` | Parabricks force-calling behavior tied to its documented allele input. |
| `--filter-reads-too-long`, `--no-alt-contigs` | Parabricks read/contig filtering conveniences. |
| `--sample-sex`, `--range-male`, `--range-female`, `--use-GRCh37-regions` | Parabricks sex-chromosome handling controls. |
| `--htvc-low-memory`, `--num-htvc-threads`, `--run-partition`, `--gpu-num-per-partition` | Parabricks GPU/partition performance controls. |
| `--logfile`, `--x3` | Parabricks wrapper logging and full-argument display. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks` | Parabricks wrapper filesystem/container controls. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- BAM/CRAM and reference match.
- Output VCF/gVCF exists and is indexed when requested.
- Logs do not show reference mismatch, malformed intervals, mount, CUDA, or
  memory errors.

## Guardrails

- Do not use for somatic tumor/normal calling.
- Do not claim BQSR was performed unless input was already recalibrated or the
  selected pipeline did so.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_haplotypecaller.html>

# Parabricks haplotypecaller

Collect prepared aligned reads, reference FASTA, and a VCF or gVCF destination.
Clarify intervals, ploidy, and emission mode as needed, and inspect interval
errors. Establish input recalibration history before stating that BQSR has
been performed. For a pipeline starting from FASTQ, use
[germline](pbrun-germline.md). Somatic tumor-normal analysis needs a somatic
caller rather than HaplotypeCaller.

## Command Shape

```bash
pbrun haplotypecaller \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --out-variants /outputdir/<sample.vcf.gz>
```

## HaplotypeCaller Option Mapping

Parabricks v4.7.0 documents this as a
GPU-accelerated HaplotypeCaller counterpart, but the CLI is not one-to-one:
some GATK flags are direct Parabricks flags, while other supported original
HaplotypeCaller options must be passed through `--haplotypecaller-options`.

| GATK option | `pbrun haplotypecaller` equivalent | Notes |
| --- | --- | --- |
| `--input`, `-I` | `--in-bam` | Required BAM/CRAM input. |
| `--output`, `-O` | `--out-variants` | Required VCF/gVCF output. |
| `--bqsr-recal-file` via prior `ApplyBQSR` | `--in-recal-file` | Optional BQSR report input; Parabricks applies updated qualities internally. |
| `--exclude-intervals`, `-XL` | `--exclude-intervals`, `-XL` | Same exclude-interval role. |
| `--emit-ref-confidence GVCF` | `--gvcf` | Generate gVCF output. |
| `--sample-ploidy` | `--ploidy` | Currently documents haploid and diploid support. |
| `--annotation`, `-A`; `--annotations-to-exclude`, `-AX`; `--output-mode`; selected assembly/calling knobs | `--haplotypecaller-options` | Pass supported original HaplotypeCaller options as one string. |
| `--annotation-group`, `-G` | `--annotation-group`, `-G` | Supported annotation group output. |
| `--gvcf-gq-bands`, `-GQB` | `--gvcf-gq-bands`, `-GQB` | Reference-confidence GQ bands. |
| `--dont-use-soft-clipped-bases` | `--dont-use-soft-clipped-bases` | Same role. |
| `--minimum-mapping-quality` | `--minimum-mapping-quality` | Same read filtering role. |
| `--mapping-quality-threshold-for-genotyping` | `--mapping-quality-threshold-for-genotyping` | Same genotyping threshold role. |
| `--min-base-quality-score` | `--min-base-quality-score` | Same base quality role. |
| `--max-alternate-alleles` | `--max-alternate-alleles` | Same genotyping cap role. |
| `--disable-read-filter` | `--disable-read-filter` | Limited to filters documented by the selected Parabricks version. |
| `--native-pair-hmm-threads`, `--java-options`, GATK engine/common flags | No direct equivalent | Not exposed as GATK engine controls by current Parabricks docs. |
| — | `--htvc-bam-output` | Output for assembled haplotypes. |
| — | `--htvc-alleles` | Force-call VCF input naming for the HTVC path. |
| — | `--rna` | RNA-optimized mode. |
| — | `--adaptive-pruning` | Parabricks-exposed graph pruning control. |
| — | `--force-call-filtered-alleles` | Force-calling behavior tied to its documented allele input. |
| — | `--filter-reads-too-long`, `--no-alt-contigs` | Read/contig filtering conveniences. |
| — | `--sample-sex`, `--range-male`, `--range-female`, `--use-GRCh37-regions` | Sex-chromosome handling controls. |
| — | `--htvc-low-memory`, `--num-htvc-threads`, `--run-partition`, `--gpu-num-per-partition` | GPU/partition performance controls. |

# Parabricks tool index

Use this reference for tool discovery, category comparison, and routing heuristics
when the user's data type or analysis goal is not yet mapped to a specific
`pbrun` command.

## Current Tool Categories

For NVIDIA Parabricks v4.7.0, the official Tool Reference lists these command
categories.

### FASTQ/BAM Processing

- `applybqsr`: apply base quality score recalibration to aligned reads.
- `bam2fq`: convert BAM input to FASTQ output.
- `bamsort`: sort BAM input.
- `bqsr`: generate base quality score recalibration data.
- `fq2bam`: align FASTQ reads and produce BAM/CRAM with common preprocessing.
- `fq2bam_meth`: methylation-oriented FASTQ-to-BAM workflow.
- `giraffe`: pangenome graph alignment using vg giraffe with GATK-style steps.
- `markdup`: mark duplicate reads in aligned data.
- `minimap2`: long-read alignment.

### Variant Calling

- `deepsomatic`: DeepSomatic-based somatic variant calling.
- `deepvariant`: DeepVariant variant calling.
- `deepvariant_germline`: germline pipeline using DeepVariant.
- `germline`: GATK-style germline short variant pipeline.
- `haplotypecaller`: GATK HaplotypeCaller-compatible calling.
- `mutectcaller`: Mutect2-compatible somatic calling.
- `ont_germline`: Oxford Nanopore germline workflow.
- `pacbio_germline`: PacBio germline workflow.
- `pangenome_aware_deepvariant`: pangenome-aware DeepVariant workflow listed
  in the alphabetical tool index.
- `pangenome_germline`: pangenome-aware germline workflow.
- `postpon`: post-processing for pangenome-aware workflows.
- `prepon`: pre-processing for pangenome-aware workflows.
- `somatic`: somatic variant calling pipeline.

### RNA

- `rna_fq2bam`: RNA-seq FASTQ-to-BAM workflow.
- `starfusion`: fusion detection with STAR-Fusion.

### Quality Control

- `bammetrics`: BAM metrics and QC.
- `collectmultiplemetrics`: collect multiple alignment metrics.

### Variant and GVCF Processing

- `dbsnp`: dbSNP annotation or processing support.
- `genotypegvcf`: genotype GVCF input.
- `indexgvcf`: index GVCF input.

## Routing Heuristics

- Raw paired FASTQ to aligned BAM/CRAM: start with `fq2bam`.
- Raw RNA-seq FASTQ to aligned BAM: consider `rna_fq2bam`.
- Methylation FASTQ workflows: consider `fq2bam_meth`.
- Long-read FASTQ alignment: consider `minimap2`.
- Pangenome graph alignment: consider `giraffe`.
- Short-read germline variant calling from FASTQ: consider `germline` or
  `deepvariant_germline` depending on the desired caller.
- Short-read germline variant calling from BAM: consider `haplotypecaller` or
  `deepvariant`.
- Tumor/normal or tumor-only somatic calling: consider `somatic`,
  `mutectcaller`, or `deepsomatic` depending on the caller requested.
- PacBio germline data: consider `pacbio_germline`.
- Oxford Nanopore germline data: consider `ont_germline`.
- Pangenome-aware alignment or calling: consider `giraffe`,
  `pangenome_germline`, `prepon`, `postpon`, or
  `pangenome_aware_deepvariant`.
- Existing BAM QC: consider `bammetrics` or `collectmultiplemetrics`.
- GVCF consolidation or genotyping: consider `indexgvcf` and `genotypegvcf`.
- dbSNP annotation or variant processing: consider `dbsnp`.

## Key References

- Tool index: <https://docs.nvidia.com/clara/parabricks/latest/toolreference.html>
- About and performance notes:
  <https://docs.nvidia.com/clara/parabricks/latest/overview.html>
- Getting started and deployment:
  <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted.html>

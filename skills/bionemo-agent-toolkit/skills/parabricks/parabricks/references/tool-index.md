# Parabricks tool index

Use this reference for tool discovery, category comparison, and routing heuristics
when the user's data type or analysis goal is not yet mapped to a specific
`pbrun` command.

## Tool Categories

The per-tool descriptions and their reference links live in the
**Tool Reference Index** table in the skill's `SKILL.md`. This file focuses on
routing rather than restating that table.

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
  `pangenome_germline`, or `pangenome_aware_deepvariant`.
- Mutect panel-of-normals preparation and annotation: use `prepon` before
  calling with `--pon`, and `postpon` for subsequent PON annotation.
- Existing BAM QC: consider `bammetrics` or `collectmultiplemetrics`.
- GVCF consolidation or genotyping: consider `indexgvcf` and `genotypegvcf`.
- dbSNP annotation or variant processing: consider `dbsnp`.

## Key References

- Tool index (4.7.0 baseline): <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/ToolReference.html>
- Performance notes (4.7.0):
  <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/GettingStarted/BestPerformance.html>
- Getting started and deployment (4.7.0):
  <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/GettingStarted.html>
- Other releases: <https://docs.nvidia.com/clara/parabricks/about-parabricks/release-notes>

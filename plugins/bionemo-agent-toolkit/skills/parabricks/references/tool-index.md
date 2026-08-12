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
  `pangenome_germline`, `prepon`, `postpon`, or
  `pangenome_aware_deepvariant`.
- Existing BAM QC: consider `bammetrics` or `collectmultiplemetrics`.
- GVCF consolidation or genotyping: consider `indexgvcf` and `genotypegvcf`.
- dbSNP annotation or variant processing: consider `dbsnp`.

## Container invocation

Every `pbrun` command runs inside the Parabricks container. Each command
reference's `## Command Shape` shows only the `pbrun …` line; wrap it with the
standard invocation below (adjust volumes/workdir to your host layout):

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  <pbrun command from the reference>
```

## Key References

- Tool index: <https://docs.nvidia.com/clara/parabricks/latest/toolreference.html>
- About and performance notes:
  <https://docs.nvidia.com/clara/parabricks/latest/overview.html>
- Getting started and deployment:
  <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted.html>

# Parabricks postpon

Annotate a Mutect VCF using a panel of normals after the `--pon` calling path.
Collect the input VCF, PON VCF.GZ with its tabix index, and annotated VCF
destination. Check reference compatibility and the resulting INFO annotations.
This is somatic PON postprocessing, not a pangenome workflow stage.

## Command Shape

```bash
pbrun postpon \
  --in-vcf /workdir/<mutect.vcf> \
  --in-pon-file /workdir/<panel_of_normals.vcf.gz> \
  --out-vcf /outputdir/<annotated.vcf>
```

## Panel-of-Normals Postprocessing Option Mapping

Parabricks documents `postpon` as the postprocess
of calling `--pon` in `mutectcaller`, annotating variants based on a PON file.

| Baseline option | `pbrun postpon` equivalent | Notes |
| --- | --- | --- |
| Mutect2 output VCF to annotate | `--in-vcf` | Required input VCF. |
| Mutect2/GATK panel-of-normals VCF | `--in-pon-file` | Required PON VCF.GZ with tabix index. |
| Annotated VCF output | `--out-vcf` | Required output annotated VCF. |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun postpon` flags. |
| GATK engine/common flags | No direct equivalent | Not documented for this tool. |
| — | PON annotation handoff from `mutectcaller` | Decomposes PON handling into `prepon`, `mutectcaller`, and `postpon`. |

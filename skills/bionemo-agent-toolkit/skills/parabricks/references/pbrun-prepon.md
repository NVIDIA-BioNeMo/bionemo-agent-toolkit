# Parabricks prepon

Prepare an existing panel-of-normals (PON) resource for `mutectcaller --pon`.
Collect the PON VCF.GZ and its tabix index. Check that contig headers include
chromosome names and lengths, and that the PON matches the calling reference.
Confirm the generated index location and its accessibility to Mutect. This
indexes a PON; it neither creates the panel from samples nor prepares a
pangenome graph.

## Command Shape

```bash
pbrun prepon \
  --in-pon-file /workdir/<panel_of_normals.vcf.gz>
```

## Panel-of-Normals Preprocessing Option Mapping

Parabricks documents `prepon` as a preprocessing step for PON
use with `mutectcaller`, rather than a direct standalone GATK tool clone.

| Baseline option | `pbrun prepon` equivalent | Notes |
| --- | --- | --- |
| Mutect2 `--panel-of-normals`, `--pon` input VCF | `--in-pon-file` | Input PON VCF.GZ with tabix index when documented. |
| Generated PON index/intermediate | Default/version-specific `prepon` output | Verify output behavior in the selected version; some docs show no explicit output flag. |
| Docker volume/workdir options | Docker `--volume` / `--workdir` outside `pbrun` | Container launch options, not `pbrun prepon` flags. |
| GATK `CreateSomaticPanelOfNormals` options | No direct equivalent | `prepon` preprocesses an existing PON resource for Parabricks use. |
| GATK engine/common flags | No direct equivalent | Not documented for this tool. |
| — | Version-specific PON index/intermediate behavior | Creates resources consumed by `mutectcaller`. |

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

## Header Repair and Calling Handoff

For **4.7.0**, a tabix index alone is insufficient: `prepon` creates the
additional `.pon` resource required by `mutectcaller --pon`. The calling flag
still takes the **PON VCF.GZ path**, not the generated `.pon` file.

If contig lengths are missing, use the matching reference's `.fai` to repair
the header in a new PON copy, for example with `bcftools reheader --fai
<reference.fa.fai> --output <new-panel.vcf.gz> <original-panel.vcf.gz>`.
Confirm the reference sequence/build and contig names agree before replacing
header metadata; reheadering cannot convert assemblies. Preserve the original,
choose unused output paths, and create a **new tabix index** for the changed
VCF, for example `bcftools index --tbi <new-panel.vcf.gz>`.

Run `prepon` on the repaired, indexed PON before
[mutectcaller](pbrun-mutectcaller.md). Then use
[postpon](pbrun-postpon.md) with the caller's VCF and the same PON VCF.GZ to
produce PON INFO annotations. These steps consume an existing panel; they do
not construct one from normal-sample BAMs.

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

## Key References

- [Parabricks 4.7.0 prepon manual](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_prepon.html)
- [Parabricks 4.7.0 mutectcaller manual](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_mutectcaller.html)
- [Parabricks 4.7.0 postpon manual](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_postpon.html)
- [bcftools reheader and index options](https://samtools.github.io/bcftools/bcftools.html)

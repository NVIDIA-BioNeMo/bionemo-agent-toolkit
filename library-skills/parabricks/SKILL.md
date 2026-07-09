---
name: parabricks
description: >-
  Route NVIDIA Parabricks pbrun tools, assess GPU/runtime readiness, and provide
  version-aware command guidance for FASTQ/BAM processing, RNA-seq, variant
  calling, BAM QC, and GVCF workflows. Do NOT use for inspecting or accelerating
  whole pipelines — use genomics-workflow-acceleration.
license: CC-BY-4.0 AND Apache-2.0
metadata:
  author: "Angel Pizarro <apizarro@nvidia.com>"
  version: "1.1.0"
  tags:
    - parabricks
    - genomics
    - nvidia
---

# Parabricks

## Purpose

Use this skill to discover the right NVIDIA Parabricks `pbrun` command, assess
runtime readiness, and generate version-aware command guidance for individual
tools and pipelines.

Do **not** use this skill for whole-workflow inspection, acceleration planning,
or wiring optional GPU branches. For pipeline-level work, use
`genomics-workflow-acceleration`.

## When to Use This Skill

- Which `pbrun` tool fits the user's data and goal
- GPU, driver, Docker, container, storage, or installation readiness
- Command shape, flags, and validation for a specific Parabricks tool
- Troubleshooting a single Parabricks command or tool family

## Prerequisites

Ask for input data type, sequencing technology, reference build, sample
structure, desired output, target Parabricks version/container tag, and runtime
target before recommending commands.

If the user is unsure which tool applies, read
[tool-index.md](references/tool-index.md) first, then load the matching
`references/pbrun-<tool>.md` file.

## Limitations

This skill routes and guides Parabricks commands. It does not install
Parabricks, infer missing sample metadata, guarantee output parity, provide
clinical interpretation, or promise exact runtime without benchmark data.

## Workflow

1. Confirm the Parabricks version or container tag. Verify the current NVIDIA
   docs when the user asks for the latest tool list or version-sensitive flags.
2. Classify the request:
   - **Runtime** → [runtime-environment.md](references/runtime-environment.md)
   - **Tool discovery** → [tool-index.md](references/tool-index.md)
   - **Specific command** → matching `references/pbrun-<tool>.md`
3. Collect missing biological and filesystem context before generating commands.
4. Generate conservative Docker commands with explicit mounts, workdir, and
   placeholders. Validate paths, indexes, and outputs after command generation.

## Tool Reference Index

Load only the reference file for the selected tool.

| Tool | Reference | Use when |
|------|-----------|----------|
| `applybqsr` | [pbrun-applybqsr.md](references/pbrun-applybqsr.md) | Apply BQSR table to aligned BAM |
| `bam2fq` | [pbrun-bam2fq.md](references/pbrun-bam2fq.md) | BAM → FASTQ conversion |
| `bamsort` | [pbrun-bamsort.md](references/pbrun-bamsort.md) | Standalone BAM sort |
| `bqsr` | [pbrun-bqsr.md](references/pbrun-bqsr.md) | Generate BQSR recalibration table |
| `fq2bam` | [pbrun-fq2bam.md](references/pbrun-fq2bam.md) | Short-read DNA paired FASTQ → BAM/CRAM |
| `fq2bam_meth` | [pbrun-fq2bam_meth.md](references/pbrun-fq2bam_meth.md) | Bisulfite/methylation FASTQ → BAM/CRAM |
| `giraffe` | [pbrun-giraffe.md](references/pbrun-giraffe.md) | Pangenome graph alignment |
| `markdup` | [pbrun-markdup.md](references/pbrun-markdup.md) | Standalone duplicate marking |
| `minimap2` | [pbrun-minimap2.md](references/pbrun-minimap2.md) | Long-read FASTQ alignment |
| `rna_fq2bam` | [pbrun-rna_fq2bam.md](references/pbrun-rna_fq2bam.md) | RNA-seq FASTQ(s) → splice-aware BAM (STAR alignment) |
| `starfusion` | [pbrun-starfusion.md](references/pbrun-starfusion.md) | Fusion detection from chimeric junction input + STAR-Fusion genome library |
| `germline` | [pbrun-germline.md](references/pbrun-germline.md) | GATK-style germline pipeline from FASTQ |
| `deepvariant_germline` | [pbrun-deepvariant_germline.md](references/pbrun-deepvariant_germline.md) | DeepVariant germline pipeline from FASTQ |
| `haplotypecaller` | [pbrun-haplotypecaller.md](references/pbrun-haplotypecaller.md) | Standalone HaplotypeCaller from BAM/CRAM |
| `deepvariant` | [pbrun-deepvariant.md](references/pbrun-deepvariant.md) | Standalone DeepVariant from BAM/CRAM |
| `somatic` | [pbrun-somatic.md](references/pbrun-somatic.md) | Tumor-normal somatic pipeline |
| `mutectcaller` | [pbrun-mutectcaller.md](references/pbrun-mutectcaller.md) | Mutect2-compatible somatic calling |
| `deepsomatic` | [pbrun-deepsomatic.md](references/pbrun-deepsomatic.md) | DeepSomatic-based somatic calling |
| `pacbio_germline` | [pbrun-pacbio_germline.md](references/pbrun-pacbio_germline.md) | PacBio long-read germline |
| `ont_germline` | [pbrun-ont_germline.md](references/pbrun-ont_germline.md) | Oxford Nanopore long-read germline |
| `pangenome_germline` | [pbrun-pangenome_germline.md](references/pbrun-pangenome_germline.md) | Pangenome-aware germline |
| `pangenome_aware_deepvariant` | [pbrun-pangenome_aware_deepvariant.md](references/pbrun-pangenome_aware_deepvariant.md) | Pangenome-aware DeepVariant |
| `prepon` | [pbrun-prepon.md](references/pbrun-prepon.md) | Pangenome-aware preprocessing |
| `postpon` | [pbrun-postpon.md](references/pbrun-postpon.md) | Pangenome-aware post-processing |
| `bammetrics` | [pbrun-bammetrics.md](references/pbrun-bammetrics.md) | Whole-genome coverage/depth metrics |
| `collectmultiplemetrics` | [pbrun-collectmultiplemetrics.md](references/pbrun-collectmultiplemetrics.md) | Multiple Picard/GATK-style alignment metrics |
| `genotypegvcf` | [pbrun-genotypegvcf.md](references/pbrun-genotypegvcf.md) | Joint-genotype GVCF input(s) into VCF |
| `indexgvcf` | [pbrun-indexgvcf.md](references/pbrun-indexgvcf.md) | Index GVCF input |
| `dbsnp` | [pbrun-dbsnp.md](references/pbrun-dbsnp.md) | dbSNP annotation on variant files |

For routing heuristics when multiple tools could apply, see
[tool-index.md](references/tool-index.md).

**QC vs variant calling:** `bammetrics` and `collectmultiplemetrics` are metrics
tools only — they do not fix coverage gaps or call variants. Route variant recall
goals to callers such as `haplotypecaller`, `germline`, or `deepvariant`, not QC
tools.

## Runtime Readiness

For GPU, driver, Docker, container, storage, or installation questions, read
[runtime-environment.md](references/runtime-environment.md) and prefer:

```bash
python3 skills/parabricks/scripts/check_parabricks_runtime.py
```

Add `--path <dir>` for known input/output/tmp paths. Run container probes only
with user consent.

## Command Shape

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun <selected-tool> \
  <tool-specific-options>
```

Check the version-specific tool reference before finalizing flags.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| Multiple plausible tools | Data type or goal underspecified | Ask for assay, inputs, caller preference, desired output; use tool-index |
| Exact flag requested | Options are version-sensitive | Check the selected tool reference and NVIDIA docs |
| Runtime question | GPU, Docker, drivers, or storage | Use runtime-environment reference and diagnostic script |
| Wrong tool family | Assay or input type unclear | Confirm DNA/RNA/methylation/long-read/pangenome before routing |
| CUDA or memory failure | Runtime not ready or GPU memory constrained | Assess runtime before tuning command flags |

## Guardrails

- Treat command availability and options as version-sensitive.
- Do not infer exact flags from command names alone.
- Do not collapse standalone tools and full pipelines when explaining tradeoffs.
- Do not substitute DNA `fq2bam` for RNA, or germline for somatic callers.
- Do not invent sample names, read groups, reference builds, known-sites files,
  model files, graph resources, container tags, or output paths.
- Do not install, upgrade, or modify packages. Label setup commands as user-run.
- Do not claim CPU execution of Parabricks tools.
- Do not claim biological or VCF parity without a comparison run.
- Prefer official NVIDIA docs for exact command syntax and option defaults.

## Key References

- Parabricks tool index:
  <https://docs.nvidia.com/clara/parabricks/latest/toolreference.html>
- Output accuracy and compatible CPU software versions:
  <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/outputaccuracyandcompatiblecpusoftwareversions.html>
- Getting started:
  <https://docs.nvidia.com/clara/parabricks/latest/gettingstarted.html>
- Overview:
  <https://docs.nvidia.com/clara/parabricks/latest/overview.html>

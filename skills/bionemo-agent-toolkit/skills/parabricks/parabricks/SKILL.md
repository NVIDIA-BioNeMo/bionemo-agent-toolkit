---
name: parabricks
description: >-
  Route NVIDIA Parabricks pbrun tools, assess GPU/runtime readiness, and provide
  version-aware command guidance for FASTQ/BAM processing, RNA-seq, variant
  calling, BAM QC, and GVCF workflows, including planning-only questions about a
  named pbrun tool. Do NOT use for inspecting or accelerating whole pipelines —
  use genomics-workflow-acceleration.
license: CC-BY-4.0 AND Apache-2.0
metadata:
  author: "Angel Pizarro <apizarro@nvidia.com>"
  version: "1.2.4"
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
- Planning-only or "do not run" questions about a named `pbrun` tool (for
  example reference/index compatibility, output naming, or flag validity). Use
  this skill's references to answer; do not skip it because nothing will be
  executed.

## Prerequisites

- **Command guidance:** No Parabricks/NGC credential or local GPU/container
  runtime is required to read references or generate commands.
- **Readiness helper:** Runs with Bash on the host being inspected; missing
  runtime components are reported as readiness gaps.
- **Execution:** The documented Docker commands require a supported Linux host,
  an NVIDIA GPU with sufficient memory, a compatible NVIDIA driver, Docker,
  NVIDIA Container Toolkit, and access to the selected Parabricks image.
  Pulling the image may require an NGC API key for authentication to `nvcr.io`.
  See [runtime-environment.md](references/runtime-environment.md) for
  version-specific requirements and checks.

For command guidance, identify the assay, inputs, reference build, desired
output, and target version. Ask only for missing facts that affect the answer;
an explicitly labeled template can use placeholders while those facts are
unresolved. Runtime-only questions do not need sample metadata.

If the user is unsure which tool applies, scan the **Tool Reference Index**
below, then load the matching `references/pbrun-<tool>.md` file.


## Limitations

This skill routes and guides Parabricks commands. It does not install
Parabricks, infer missing sample metadata, guarantee output parity, provide
clinical interpretation, or promise exact runtime without benchmark data.

## Workflow

1. Confirm the Parabricks version or container tag. These references track the
   current published docs and were last verified against v4.7.1. Use the user's
   container tag in generated commands. For another version, or if the NVIDIA
   Parabricks docs look newer, verify against those docs or `pbrun <tool>
   --help` on their container before answering.
2. Classify the request:
   - **Runtime** → [runtime-environment.md](references/runtime-environment.md)
   - **Tool discovery** → **Tool Reference Index** (below)
   - **Specific command** → matching `references/pbrun-<tool>.md`. Read it
     **before** any web search or MCP lookup; use those only to verify
     version-sensitive details the reference does not settle.
3. For command shape and option translation, follow
   [command-conventions.md](references/command-conventions.md) and
   [shared-options.md](references/shared-options.md) together with the
   per-tool reference.
4. Collect missing biological and filesystem context before generating commands.
5. Generate conservative Docker commands with explicit mounts, workdir, and
   placeholders. Validate paths, indexes, and outputs after command generation.

## Tool Reference Index

Use these tables for tool discovery when assay, input type, or goal is unclear.
After choosing a tool, load only its `references/pbrun-<tool>.md` for command
shape and flags.

### FASTQ/BAM Processing

| Parabricks Tool | Skill Reference | Use when |
|------|-----------|----------|
| [`applybqsr`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/applybqsr) | [pbrun-applybqsr.md](references/pbrun-applybqsr.md) | Apply a BQSR recalibration table to aligned BAM/CRAM after `bqsr`. |
| [`bam2fq`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/bam2fq) | [pbrun-bam2fq.md](references/pbrun-bam2fq.md) | Convert BAM input to FASTQ output. |
| [`bamsort`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/bamsort) | [pbrun-bamsort.md](references/pbrun-bamsort.md) | Standalone BAM sort (CRAM v3.1 read support documented for recent releases). |
| [`bqsr`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/bqsr) | [pbrun-bqsr.md](references/pbrun-bqsr.md) | Generate base quality score recalibration data for later `applybqsr`. |
| [`fq2bam`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/fq2bam) | [pbrun-fq2bam.md](references/pbrun-fq2bam.md) | Raw paired short-read DNA FASTQ → aligned BAM/CRAM with common preprocessing (align/sort/dedup/BQSR path). |
| [`fq2bam_meth`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/fq2bam_meth) | [pbrun-fq2bam_meth.md](references/pbrun-fq2bam_meth.md) | Bisulfite or methylation FASTQ workflows — not standard DNA `fq2bam`. |
| [`giraffe`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/giraffe) | [pbrun-giraffe.md](references/pbrun-giraffe.md) | Pangenome graph alignment (vg giraffe); pairs with pangenome-aware pre/post and callers. |
| [`markdup`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/markdup) | [pbrun-markdup.md](references/pbrun-markdup.md) | Mark duplicate reads in aligned BAM/CRAM when not folded into `fq2bam`. |
| [`minimap2`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/minimap2) | [pbrun-minimap2.md](references/pbrun-minimap2.md) | Long-read FASTQ alignment (CRAM v3.1 read support documented for recent releases). |

### Variant Calling

| Parabricks Tool | Skill Reference | Use when |
|------|-----------|----------|
| [`deepsomatic`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/deepsomatic) | [pbrun-deepsomatic.md](references/pbrun-deepsomatic.md) | Tumor/normal or tumor-only somatic calling with DeepSomatic (CRAM v3.1 reads documented for recent releases). |
| [`deepvariant`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/deepvariant) | [pbrun-deepvariant.md](references/pbrun-deepvariant.md) | DeepVariant from BAM/CRAM; short-read germline recall alternative to `haplotypecaller`. |
| [`deepvariant_germline`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/deepvariant_germline) | [pbrun-deepvariant_germline.md](references/pbrun-deepvariant_germline.md) | FASTQ-in DeepVariant germline pipeline when the user wants DeepVariant end-to-end from reads. |
| [`germline`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/germline) | [pbrun-germline.md](references/pbrun-germline.md) | FASTQ-in GATK-style germline pipeline; do not route existing BAM/CRAM here without version-verified docs. |
| [`haplotypecaller`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/haplotypecaller) | [pbrun-haplotypecaller.md](references/pbrun-haplotypecaller.md) | GATK HaplotypeCaller-compatible germline calling from BAM/CRAM (primary short-read variant recall path). |
| [`mutectcaller`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/mutectcaller) | [pbrun-mutectcaller.md](references/pbrun-mutectcaller.md) | Tumor/normal or tumor-only somatic calling with Mutect2-compatible caller (CRAM v3.1 reads documented for recent releases). |
| [`ont_germline`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/ont_germline) | [pbrun-ont_germline.md](references/pbrun-ont_germline.md) | Oxford Nanopore long-read germline workflow. |
| [`pacbio_germline`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/pacbio_germline) | [pbrun-pacbio_germline.md](references/pbrun-pacbio_germline.md) | PacBio long-read germline workflow. |
| [`pangenome_aware_deepvariant`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/pangenome_aware_deepvariant) | [pbrun-pangenome_aware_deepvariant.md](references/pbrun-pangenome_aware_deepvariant.md) | Pangenome-aware DeepVariant; for Roche SBX-D/SBX-Fast BAMs use `--sbx` (verify in docs/MCP). CRAM v3.1 reads documented for recent releases. |
| [`pangenome_germline`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/pangenome_germline) | [pbrun-pangenome_germline.md](references/pbrun-pangenome_germline.md) | Pangenome-aware germline workflow with graph resources. |
| [`postpon`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/postpon) | [pbrun-postpon.md](references/pbrun-postpon.md) | Post-processing for pangenome-aware workflows (with `prepon` / graph alignment). |
| [`prepon`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/prepon) | [pbrun-prepon.md](references/pbrun-prepon.md) | Pre-processing for pangenome-aware workflows (with `postpon` / callers). |
| [`somatic`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/somatic) | [pbrun-somatic.md](references/pbrun-somatic.md) | Tumor/normal somatic variant calling pipeline (caller family alternative to `mutectcaller` / `deepsomatic`). |

### RNA

| Parabricks Tool | Skill Reference | Use when |
|------|-----------|----------|
| [`rna_fq2bam`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/rna_fq2bam) | [pbrun-rna_fq2bam.md](references/pbrun-rna_fq2bam.md) | RNA-seq FASTQ → splice-aware aligned BAM (STAR-based workflow). `--ref` and the STAR `--genome-lib-dir` must be the same assembly (contig renaming cannot fix a mismatch); STAR 2.7.2a compatibility baseline. |
| [`starfusion`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/starfusion) | [pbrun-starfusion.md](references/pbrun-starfusion.md) | Fusion detection with STAR-Fusion from chimeric junction input and genome library. |

### Quality Control

| Parabricks Tool | Skill Reference | Use when |
|------|-----------|----------|
| [`bammetrics`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/bammetrics) | [pbrun-bammetrics.md](references/pbrun-bammetrics.md) | BAM metrics and QC on existing alignments — not variant calling or coverage repair. |
| [`collectmultiplemetrics`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/collectmultiplemetrics) | [pbrun-collectmultiplemetrics.md](references/pbrun-collectmultiplemetrics.md) | Multiple Picard/GATK-style alignment metrics — not variant recall from BAM/CRAM. |

### Variant and GVCF Processing

| Parabricks Tool | Skill Reference | Use when |
|------|-----------|----------|
| [`dbsnp`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/dbsnp) | [pbrun-dbsnp.md](references/pbrun-dbsnp.md) | dbSNP annotation or variant file processing support. |
| [`genotypegvcf`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/genotypegvcf) | [pbrun-genotypegvcf.md](references/pbrun-genotypegvcf.md) | Joint-genotype GVCF input(s) into VCF after indexing. |
| [`indexgvcf`](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/indexgvcf) | [pbrun-indexgvcf.md](references/pbrun-indexgvcf.md) | Index GVCF before `genotypegvcf` or consolidation workflows. Writes `<input>.tbi` beside the input (no `--out`); for read-only inputs, index a writable copy after checking for existing files. |

**CRAM v3.1 reads:** Documented for `bamsort`, `deepsomatic`, `deepvariant`,
`haplotypecaller`, `minimap2`, `mutectcaller`, and `pangenome_aware_deepvariant`
for recent Parabricks releases. Verify in NVIDIA docs or MCP before routing
CRAM v3.1 inputs to other tools.

## Runtime Readiness

For GPU, driver, Docker, container, storage, or installation questions, read
[runtime-environment.md](references/runtime-environment.md) and prefer:

```bash
bash skills/parabricks/scripts/check_parabricks_runtime.sh
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
| Multiple plausible tools | Data type or goal underspecified | Ask for assay, inputs, caller preference, desired output; use Tool Reference Index |
| Exact flag requested | Options are version-sensitive | Check the selected tool reference, NVIDIA docs, or `pbrun <tool> --help` |
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
- Use the Parabricks documentation MCP server for exact command syntax and
  option defaults whenever it is available; do not present version-sensitive
  details as verified if the lookup failed.

## Key References

- Parabricks documentation MCP server:
  <https://docs.nvidia.com/clara/parabricks/_mcp/server>
- Parabricks tool index:
  <https://docs.nvidia.com/clara/parabricks/tool-reference>
- Output accuracy and compatible CPU software versions:
  <https://docs.nvidia.com/clara/parabricks/about-parabricks/software-overview/output-accuracy-and-compatible-cpu-software-versions>
- Getting started:
  <https://docs.nvidia.com/clara/parabricks/get-started>
- Overview:
  <https://docs.nvidia.com/clara/parabricks/about-parabricks>

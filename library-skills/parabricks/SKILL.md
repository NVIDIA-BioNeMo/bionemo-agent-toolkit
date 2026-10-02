---
name: parabricks
description: >-
  Select NVIDIA Parabricks pbrun tools, assess GPU/runtime readiness, and provide
  version-aware commands for FASTQ/BAM processing, RNA-seq, variant calling,
  BAM QC, and GVCF workflows. Use for individual pbrun commands, including
  packaged germline/somatic pipelines; not Nextflow/Snakemake orchestration.
license: CC-BY-4.0 AND Apache-2.0
allowed-tools: Bash, Read, WebFetch, AskUserQuestion
metadata:
  author: Ohad Mosafi (@ohadmo)
  version: "1.2.1"
  tags:
    - parabricks
    - genomics
    - nvidia
---

# Parabricks

## Purpose

Use this skill to discover the right NVIDIA Parabricks `pbrun` command, assess
runtime readiness, and generate version-aware command guidance for individual
tools and packaged `pbrun` pipelines.

Do **not** use this skill for whole-workflow inspection, acceleration planning,
or wiring optional GPU branches. For pipeline-level work, use an available
workflow skill such as `genomics-workflow-acceleration`, or provide ordinary
Nextflow/Snakemake guidance when no suitable skill is installed. Do not load
Parabricks references or run its helper solely for orchestration settings.

## When to Use This Skill

- Which `pbrun` tool fits the user's data and goal
- GPU, driver, Docker, container, storage, or installation readiness
- Command shape, flags, and validation for a specific Parabricks tool
- Troubleshooting a single Parabricks command or tool family

## Prerequisites

- **Command guidance:** No Parabricks/NGC credential or local GPU/container
  runtime is required to read references or generate commands.
- **Readiness helper:** Python 3 is required on the host being inspected;
  missing runtime components are reported as readiness gaps.
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

If the user is unsure which tool applies, read
[tool-index.md](references/tool-index.md) first, then load the matching
`references/pbrun-<tool>.md` file.

## Limitations

This skill routes and guides Parabricks commands. It does not install
Parabricks, infer missing sample metadata, guarantee output parity, provide
clinical interpretation, or promise exact runtime without benchmark data.

## Tool Scope

Use `Read` for the selected skill references, `WebFetch` for official NVIDIA
documentation, and `AskUserQuestion` for missing inputs or probe consent.
Limit `Bash` to the bundled readiness helper and the diagnostic commands in
[runtime-environment.md](references/runtime-environment.md). Generating a
`pbrun` command does not authorize running a genomics workload.

## Instructions

1. Classify the request and load only the reference needed:
   - **Runtime** → [runtime-environment.md](references/runtime-environment.md)
   - **Tool discovery** → [tool-index.md](references/tool-index.md)
   - **Specific command** → matching `references/pbrun-<tool>.md`
2. Establish the target version before making version-specific claims. Local
   option mappings use **4.7.0**. For another release, follow its manual from
   the [documentation archive](https://docs.nvidia.com/clara/parabricks/about-parabricks/release-notes).
   Verify requested flags against that release; do not substitute the latest
   requirements for an older image. Reuse sources already verified for this task.
3. For a command template, load [command-conventions.md](references/command-conventions.md)
   once. Consult [shared-options.md](references/shared-options.md) only for
   options not covered by the selected tool reference, using rows naming that
   tool. A simple tool-selection answer does not need every command reference.
4. Generate a Docker command with explicit input/index/output mounts, workdir,
   and placeholders for unresolved values. Explain relevant validation checks
   and distinguish proposed checks from observations of a completed run.
   Command guidance for a remote host does not require probing this workstation.

## Tool Reference Index

Load only the reference file for the selected tool. Manual links below are for
the 4.7.0 reference baseline; select another release when requested.

| Tool / NVIDIA manual | Reference | Use when |
|------|-----------|----------|
| [`applybqsr`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_applybqsr.html) | [pbrun-applybqsr.md](references/pbrun-applybqsr.md) | Apply BQSR table to aligned BAM |
| [`bam2fq`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_bam2fq.html) | [pbrun-bam2fq.md](references/pbrun-bam2fq.md) | BAM → FASTQ conversion |
| [`bamsort`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_bamsort.html) | [pbrun-bamsort.md](references/pbrun-bamsort.md) | Standalone BAM sort |
| [`bqsr`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_bqsr.html) | [pbrun-bqsr.md](references/pbrun-bqsr.md) | Generate BQSR recalibration table |
| [`fq2bam`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_fq2bam.html) | [pbrun-fq2bam.md](references/pbrun-fq2bam.md) | Short-read DNA paired FASTQ → BAM/CRAM |
| [`fq2bam_meth`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_fq2bam_meth.html) | [pbrun-fq2bam_meth.md](references/pbrun-fq2bam_meth.md) | Bisulfite/methylation FASTQ → BAM/CRAM |
| [`giraffe`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_giraffe.html) | [pbrun-giraffe.md](references/pbrun-giraffe.md) | Pangenome graph alignment |
| [`markdup`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_markdup.html) | [pbrun-markdup.md](references/pbrun-markdup.md) | Standalone duplicate marking |
| [`minimap2`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_minimap2.html) | [pbrun-minimap2.md](references/pbrun-minimap2.md) | Long-read FASTQ alignment |
| [`rna_fq2bam`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_rna_fq2bam.html) | [pbrun-rna_fq2bam.md](references/pbrun-rna_fq2bam.md) | RNA-seq FASTQ(s) → splice-aware BAM (STAR alignment) |
| [`starfusion`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_starfusion.html) | [pbrun-starfusion.md](references/pbrun-starfusion.md) | Fusion detection from chimeric junction input + STAR-Fusion genome library |
| [`germline`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_germline.html) | [pbrun-germline.md](references/pbrun-germline.md) | GATK-style germline pipeline from FASTQ |
| [`deepvariant_germline`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_deepvariant_germline.html) | [pbrun-deepvariant_germline.md](references/pbrun-deepvariant_germline.md) | DeepVariant germline pipeline from FASTQ |
| [`haplotypecaller`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_haplotypecaller.html) | [pbrun-haplotypecaller.md](references/pbrun-haplotypecaller.md) | Standalone HaplotypeCaller from BAM/CRAM |
| [`deepvariant`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_deepvariant.html) | [pbrun-deepvariant.md](references/pbrun-deepvariant.md) | Standalone DeepVariant from BAM/CRAM |
| [`somatic`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_somatic.html) | [pbrun-somatic.md](references/pbrun-somatic.md) | Tumor-normal somatic pipeline |
| [`mutectcaller`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_mutectcaller.html) | [pbrun-mutectcaller.md](references/pbrun-mutectcaller.md) | Mutect2-compatible somatic calling |
| [`deepsomatic`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_deepsomatic.html) | [pbrun-deepsomatic.md](references/pbrun-deepsomatic.md) | DeepSomatic-based somatic calling |
| [`pacbio_germline`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_pacbio_germline.html) | [pbrun-pacbio_germline.md](references/pbrun-pacbio_germline.md) | PacBio long-read germline |
| [`ont_germline`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_ont_germline.html) | [pbrun-ont_germline.md](references/pbrun-ont_germline.md) | Oxford Nanopore long-read germline |
| [`pangenome_germline`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_pangenome_germline.html) | [pbrun-pangenome_germline.md](references/pbrun-pangenome_germline.md) | Pangenome-aware germline |
| [`pangenome_aware_deepvariant`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_pangenome_aware_deepvariant.html) | [pbrun-pangenome_aware_deepvariant.md](references/pbrun-pangenome_aware_deepvariant.md) | Pangenome-aware DeepVariant |
| [`prepon`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_prepon.html) | [pbrun-prepon.md](references/pbrun-prepon.md) | Prepare a panel-of-normals index for Mutect |
| [`postpon`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_postpon.html) | [pbrun-postpon.md](references/pbrun-postpon.md) | Annotate Mutect variants using a panel of normals |
| [`bammetrics`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_bammetrics.html) | [pbrun-bammetrics.md](references/pbrun-bammetrics.md) | Whole-genome coverage/depth metrics |
| [`collectmultiplemetrics`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_collectmultiplemetrics.html) | [pbrun-collectmultiplemetrics.md](references/pbrun-collectmultiplemetrics.md) | Multiple Picard/GATK-style alignment metrics |
| [`genotypegvcf`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_genotypegvcf.html) | [pbrun-genotypegvcf.md](references/pbrun-genotypegvcf.md) | Joint-genotype GVCF input(s) into VCF |
| [`indexgvcf`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_indexgvcf.html) | [pbrun-indexgvcf.md](references/pbrun-indexgvcf.md) | Index GVCF input |
| [`dbsnp`](https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_dbsnp.html) | [pbrun-dbsnp.md](references/pbrun-dbsnp.md) | dbSNP annotation on variant files |

For routing heuristics when multiple tools could apply, see
[tool-index.md](references/tool-index.md).

## Runtime Readiness

For GPU, driver, Docker, container, storage, or installation questions, read
[runtime-environment.md](references/runtime-environment.md). Confirm that the
current machine is the intended execution host before probing it. Run the
bundled [readiness helper](scripts/check_parabricks_runtime.py) with this skill's
directory as the working directory. Run it in a separate tool call and read its
output before selecting any follow-up diagnostics:

```bash
python3 scripts/check_parabricks_runtime.py
```

Run it once, including known storage paths, and use the report. Select an
additional diagnostic only for a fact the report leaves unresolved. Missing
`nvidia-smi` or Docker is a readiness gap to report; finish the other available
checks without searching for host access through devices or daemon sockets.
Report GPU hardware as unverified when `nvidia-smi` cannot run.
For a remote target, assess supplied diagnostics or request target-host output;
local results cannot establish its readiness. The helper collects facts, not a
release-specific certification.

For readiness, check Docker through its CLI. Do not inspect, connect to, mount,
or change permissions on host Docker daemon sockets.
Do not dump environment variables or read authentication files to diagnose
readiness. Report missing components or access errors and give the target-host
administrator the next steps.

Add `--path <dir>` for known input/output/tmp paths. The default check does not
launch containers. Both `--run-container-check` and `--parabricks-version`
launch containers and may pull images; use either only when the user has
authorized container probes. A version supplied for command guidance alone is
not permission to launch that image.

## Examples

For a selected tool, wrap its `pbrun` command in this container invocation.
Replace every placeholder with confirmed values before execution:

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

- Parabricks 4.7.0 tool index:
  <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/ToolReference.html>
- Parabricks 4.7.0 getting started:
  <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/GettingStarted.html>
- Release notes and archived manuals:
  <https://docs.nvidia.com/clara/parabricks/about-parabricks/release-notes>

# Parabricks rna_fq2bam

Use this reference for NVIDIA Parabricks `pbrun rna_fq2bam` — RNA-seq FASTQ alignment that emulates the STAR RNA-Seq alignment application.

For shared wrapper mappings, cross-tool option rows, validation habits, and Parabricks wrapper controls, see [command-conventions.md](command-conventions.md) and [shared-options.md](shared-options.md) (filter the **Tools** column for this command).

## First Steps

1. Confirm the Parabricks version or container tag.
2. Confirm the input is RNA-seq FASTQ. If the data is DNA, route to
   `pbrun-fq2bam.md` and related FASTQ/BAM references.
3. Collect required inputs:
   - Paired or single-end RNA-seq FASTQ paths.
   - Reference FASTA path.
   - STAR genome library directory.
   - Output directory and expected BAM/output naming.
4. Ask for read group values, compression/read-files handling, temporary
   directory, and logs when relevant.
5. For runtime readiness, see `runtime-environment.md`.

## Command Shape

For Parabricks 4.7.0, every command needs a read-input mode, `--ref`,
`--genome-lib-dir`, **`--output-dir`**, and **`--out-bam`**. The output directory
and final BAM are separate required arguments; a BAM path or Docker mount does
not replace `--output-dir`. Check that both remain present after translating
upstream STAR flags, and use explicit placeholders for unresolved paths.

Paired-end RNA-seq FASTQs:

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun rna_fq2bam \
  --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> \
  --genome-lib-dir /workdir/<star_genome_library>/ \
  --output-dir /outputdir/<rna_output>/ \
  --out-bam /outputdir/<sample.bam> \
  --ref /workdir/<reference.fa>
```

Single-end RNA-seq FASTQ:

```bash
docker run --rm --gpus all \
  --volume /host/input:/workdir \
  --volume /host/output:/outputdir \
  --workdir /workdir \
  nvcr.io/nvidia/clara/clara-parabricks:<version> \
  pbrun rna_fq2bam \
  --in-se-fq /workdir/<sample.fastq.gz> \
  --genome-lib-dir /workdir/<star_genome_library>/ \
  --output-dir /outputdir/<rna_output>/ \
  --out-bam /outputdir/<sample.bam> \
  --ref /workdir/<reference.fa>
```

Verify exact FASTQ, read group, genome library, output, and log flags against
the selected version.

## Reference and Index Compatibility

`--ref` and `--genome-lib-dir` must describe the **same reference assembly**.

- **Same assembly and contigs:** The FASTA and the STAR genome library must be
  built from the same assembly (for example, both GRCh38) with matching contig
  names, and the annotation (GTF/GFF) used for the index must match too.
- **Different assemblies cannot be reconciled:** Mixing a GRCh37 FASTA with a
  GRCh38 STAR library is invalid. Renaming contigs fixes only naming-style
  differences (`chr1` vs `1`), not coordinates or sequence differences between
  assemblies. Choose one reference, then rebuild or obtain a STAR library for it.
- **STAR version baseline:** Parabricks documents compatibility with
  **STAR 2.7.2a**. Build or obtain the genome library with that STAR version
  unless the selected release's tool reference says otherwise; do not assume the
  latest STAR index format works. Verify the baseline for the user's release.
- **Planning questions:** Explain what must match and give a command template
  with matching `--ref` and `--genome-lib-dir` placeholders. Do not present the
  mismatched assets as runnable, and do not modify reference assets.

## STAR Option Mapping

Use this mapping when translating a STAR command to `pbrun rna_fq2bam`.
Parabricks documents compatibility with STAR 2.7.2a, but the CLI is not
one-to-one: many STAR camelCase flags become hyphen-separated Parabricks flags,
some STAR behavior is fixed by the pipeline, and many STAR parameters are not
exposed by `rna_fq2bam`.

| STAR option | `rna_fq2bam` equivalent | Notes |
| --- | --- | --- |
| `--genomeDir` | `--genome-lib-dir` | Use a STAR genome resource library directory already built for the same reference. |
| `--readFilesIn` | `--in-fq`, `--in-se-fq`, `--in-fq-list`, `--in-se-fq-list` | Parabricks splits paired, single-ended, and list-file inputs across separate flags. |
| `--readFilesCommand` | `--read-files-command` | Same role: command that emits FASTQ/FASTA text to stdout, such as `zcat`. |
| `--readNameSeparator` | `--read-name-separator` | Same role. |
| `--outFileNamePrefix` | `--output-dir`, `--out-prefix` | `--output-dir` controls the generated output directory; `--out-prefix` controls the prefix for output data. |
| `--outSAMtype BAM SortedByCoordinate` | Implicit pipeline behavior plus `--out-bam` | `rna_fq2bam` outputs a sorted BAM path via `--out-bam`; it does not expose generic `--outSAMtype`. |
| `--outSAMattrRGline` | Read group in `--in-fq` / `--in-se-fq`, or `--read-group-sm`, `--read-group-lb`, `--read-group-pl`, `--read-group-id-prefix` | Not a full one-to-one replacement for arbitrary STAR read group lines. |
| `--runThreadN` | No direct equivalent; tune separately | STAR specifies total threads; Parabricks `--num-threads` specifies workers per GPU stream. Omit it from the base translation to retain release-specific auto/default behavior. Do not copy the STAR value; an explicit setting needs a separate tuning rationale. |
| `--genomeSAindexNbases` | `--num-sa-bases` | Same SA pre-indexing length concept. |
| `--alignIntronMax` | `--max-intron-size` | Same role. |
| `--alignIntronMin` | `--min-intron-size` | Same role. |
| `--outFilterMatchNmin` | `--min-match-filter` | Same role. |
| `--outFilterMatchNminOverLread` | `--min-match-filter-normalized` | Same role, normalized to read length. |
| `--outFilterIntronMotifs` | `--out-filter-intron-motifs` | Same role. |
| `--outFilterMismatchNmax` | `--max-out-filter-mismatch` | Same role. |
| `--outFilterMismatchNoverLmax` | `--max-out-filter-mismatch-ratio` | Same role, ratio to mapped length. |
| `--outFilterMultimapNmax` | `--max-out-filter-multimap` | Same role. |
| `--outReadsUnmapped` | `--out-reads-unmapped` | Same role. |
| `--outSAMunmapped` | `--out-sam-unmapped` | Parabricks documents a reduced behavior for sorted SAM/BAM output; verify allowed values for the selected version. |
| `--outSAMattributes` | `--out-sam-attributes` | Same role. |
| `--outSAMstrandField` | `--out-sam-strand-field` | Same role. |
| `--outSAMmode` | `--out-sam-mode` | Same role. |
| `--outSAMmapqUnique` | `--out-sam-mapq-unique` | Same role. |
| `--outFilterScoreMinOverLread` | `--min-score-filter` | Same role, normalized to read length. |
| `--alignSplicedMateMapLminOverLmate` | `--min-spliced-mate-length` | Same role, normalized to mate length. |
| `--alignSJstitchMismatchNmax` | `--max-junction-mismatches` | Same four-value splice-junction mismatch concept. |
| `--limitOutSAMoneReadBytes` | `--max-out-read-size` | Same role. |
| `--alignTranscriptsPerReadNmax` | `--max-alignments-per-read` | Same role. |
| `--scoreGap` | `--score-gap` | Same role. |
| `--seedSearchStartLmax` | `--seed-search-start` | Same role. |
| `--limitBAMsortRAM` | `--max-bam-sort-memory` | Same role for BAM sorting memory. |
| `--alignEndsType` | `--align-ends-type` | Same role. |
| `--alignInsertionFlush` | `--align-insertion-flush` | Same role. |
| `--alignMatesGapMax` | `--max-align-mates-gap` | Same role. |
| `--alignSplicedMateMapLmin` | `--min-align-spliced-mate-map` | Same role. |
| `--limitOutSJcollapsed` | `--max-collapsed-junctions` | Same role. |
| `--alignSJoverhangMin` | `--min-align-sj-overhang` | Same role. |
| `--alignSJDBoverhangMin` | `--min-align-sjdb-overhang` | Same role. |
| `--sjdbOverhang` | `--sjdb-overhang` | Same role. |
| `--chimJunctionOverhangMin` | `--min-chim-overhang` | Same role. |
| `--chimSegmentMin` | `--min-chim-segment` | Same role. |
| `--chimMultimapNmax` | `--max-chim-multimap` | Same role. |
| `--chimMultimapScoreRange` | `--chim-multimap-score-range` | Same role. |
| `--chimScoreJunctionNonGTAG` | `--chim-score-non-gtag` | Same role. |
| `--chimNonchimScoreDropMin` | `--min-non-chim-score-drop` | Same role. |
| `--chimOutJunctionFormat` | `--out-chim-format` | Same role. |
| `--chimOutType` | `--out-chim-type` | Same role, but verify accepted values because Parabricks documents combined values such as `WithinBAM_HardClip`. |
| `--twopassMode` | `--two-pass-mode` | Example mixed-case to hyphenated conversion: STAR `--twopassMode Basic` becomes `--two-pass-mode Basic`. |
| `--soloType` | `--soloType` | Same flag spelling in current Parabricks docs. Verify allowed values for the selected version. |
| `--soloBarcodeReadLength` | `--soloBarcodeReadLength` | Same flag spelling in current Parabricks docs. |
| `--soloCBwhitelist` | `--soloCBwhitelist` | Same flag spelling in current Parabricks docs. |
| `--soloCBstart` | `--soloCBstart` | Same flag spelling in current Parabricks docs. |
| `--soloCBlen` | `--soloCBlen` | Same flag spelling in current Parabricks docs. |
| `--soloUMIstart` | `--soloUMIstart` | Same flag spelling in current Parabricks docs. |
| `--soloUMIlen` | `--soloUMIlen` | Same flag spelling in current Parabricks docs. |
| `--soloFeatures` | `--soloFeatures` | Same flag spelling in current Parabricks docs. |
| `--soloStrand` | `--soloStrand` | Same flag spelling in current Parabricks docs. |
| `--quantMode` | `--quantMode` | Same flag spelling in current Parabricks docs. |

If a STAR option is not listed above, assume there is no direct `rna_fq2bam`
flag until the selected Parabricks version's tool reference says otherwise.

### Translation example: preserve behavior without copying thread counts

For paired compressed FASTQs with STAR `--outSAMtype BAM SortedByCoordinate`,
`--outFilterMismatchNmax 5`, `--twopassMode Basic`, and `--runThreadN 16`, use
this `pbrun` fragment inside the Docker command shape above, after verifying
the selected release's flags:

```bash
pbrun rna_fq2bam \
  --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> \
  --read-files-command zcat \
  --genome-lib-dir /workdir/<star_genome_library>/ \
  --ref /workdir/<reference.fa> \
  --output-dir /outputdir/<rna_output>/ \
  --out-bam /outputdir/<sample.bam> \
  --max-out-filter-mismatch 5 \
  --two-pass-mode Basic
```

The fragment deliberately omits `--num-threads`: STAR's total thread count of
16 does not determine Parabricks workers per GPU stream. Keep release-specific
auto/default behavior unless the user requests separate resource tuning. Sorted
BAM output is expressed through `--out-bam`, not a passed-through `--outSAMtype`.
This translates the listed options; other pipeline behavior, such as duplicate
marking, still needs review before claiming equivalence to the CPU workflow.

## rna_fq2bam Options Without STAR Equivalents

These options are Parabricks pipeline, GPU, runtime, or wrapper options and are
not STAR CLI options already covered in the mapping above.

| `rna_fq2bam` option | Why it has no STAR equivalent |
| --- | --- |
| `--ref` | Parabricks pipeline input for the reference FASTA; STAR alignment consumes the prebuilt genome directory. You can create the STAR genome index using STAR `--runMode genomeGenerate` as a separate step.  |
| `--out-bam` | Final pipeline BAM path after STAR alignment, coordinate sorting, and optional duplicate marking. |
| `--out-duplicate-metrics` | Duplicate metrics from the Parabricks/GATK-style mark-duplicates step, not STAR. |
| `--out-qc-metrics-dir` | Parabricks QC metrics directory, not STAR. |
| `--no-markdups` | Controls whether the Parabricks pipeline skips duplicate marking after STAR. |
| `--enable-gpu-helper-threads` | Parabricks GPU/CPU scheduling option. |
| `--num-streams-per-gpu` | Parabricks GPU stream configuration. |
| `--gpuwrite` | Parabricks GPU-accelerated final BAM/CRAM writing. |
| `--gpuwrite-deflate-algo` | Parabricks/nvCOMP DEFLATE algorithm selection for `--gpuwrite`. |
| `--gpusort` | Parabricks GPU-accelerated sorting and marking. |
| `--use-gds` | Parabricks GPUDirect Storage option. |
| `--memory-limit` | Parabricks sorting/postsorting system-memory limit. |
| `--low-memory` | Parabricks low-memory mode. |
| `--verbose` | Parabricks runtime verbosity. |
| `--logfile` | Parabricks log file path. STAR writes its own log files under the STAR output prefix. |
| `--tmp-dir` | Parabricks temporary directory. STAR has `--outTmpDir`, but this wrapper option applies to the pipeline. |
| `--keep-tmp` | Parabricks temporary-file retention. STAR has `--outTmpKeep`, but this wrapper option applies to the pipeline. |
| `--version` | Parabricks compatible software version reporting. |
| `--num-gpus` | Parabricks GPU count. |


Parabricks wrapper controls (`--logfile`, `--x3`, `--with-petagene-dir`, `--keep-tmp`, `--no-seccomp-override`, `--preserve-file-symlinks`) are documented in [command-conventions.md](command-conventions.md#shared-wrapper-controls).

## Validation

- FASTQ, reference, and STAR genome library paths resolve inside the container.
- Genome library is compatible with the reference and RNA workflow.
- Output BAM and expected STAR/metrics/log outputs are present.
- Logs do not show genome library, FASTQ pairing, read group, mount, CUDA, or
  memory errors.

## Guardrails

- Do not substitute DNA `fq2bam` for RNA-seq alignment.
- Do not infer genome library compatibility from reference FASTA alone.
- Do not accept a renamed-contig workaround for a FASTA/STAR-library assembly
  mismatch; see Reference and Index Compatibility.
- Do not route fusion detection here unless the user is producing alignment
  outputs for downstream `starfusion`.

## Key References

- <https://docs.nvidia.com/clara/parabricks/tool-reference/tools/rna_fq2bam>
- <https://raw.githubusercontent.com/alexdobin/STAR/2.7.2a/source/parametersDefault>

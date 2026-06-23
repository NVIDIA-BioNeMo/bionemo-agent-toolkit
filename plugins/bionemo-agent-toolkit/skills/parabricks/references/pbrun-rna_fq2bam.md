# Parabricks rna_fq2bam

Use this reference for NVIDIA Parabricks `pbrun rna_fq2bam` — RNA-seq FASTQ alignment that emulates the STAR RNA-Seq alignment application.

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

## STAR Option Mapping

Use this mapping when translating a STAR command to `pbrun rna_fq2bam`.
Parabricks v4.7.0 documents compatibility with STAR 2.7.2a, but the CLI is not
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
| `--runThreadN` | `--num-threads` | Not one-to-one: Parabricks defines worker threads per GPU stream and may use GPU/system-memory auto tuning. |
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
| `--x3` | Parabricks option to show full command-line arguments. |
| `--logfile` | Parabricks log file path. STAR writes its own log files under the STAR output prefix. |
| `--tmp-dir` | Parabricks temporary directory. STAR has `--outTmpDir`, but this wrapper option applies to the pipeline. |
| `--with-petagene-dir` | Parabricks/PetaGene integration. |
| `--keep-tmp` | Parabricks temporary-file retention. STAR has `--outTmpKeep`, but this wrapper option applies to the pipeline. |
| `--no-seccomp-override` | Parabricks Docker/seccomp behavior. |
| `--version` | Parabricks compatible software version reporting. |
| `--preserve-file-symlinks` | Parabricks path handling behavior. |
| `--num-gpus` | Parabricks GPU count. |

## Validation

- FASTQ, reference, and STAR genome library paths resolve inside the container.
- Genome library is compatible with the reference and RNA workflow.
- Output BAM and expected STAR/metrics/log outputs are present.
- Logs do not show genome library, FASTQ pairing, read group, mount, CUDA, or
  memory errors.
- Refer to `parabricks-rna-validate.md` for differences between Parabricks version 4.7.0 vs 4.6.0
  
## Guardrails

- Do not substitute DNA `fq2bam` for RNA-seq alignment.
- Do not infer genome library compatibility from reference FASTA alone.
- Do not route fusion detection here unless the user is producing alignment
  outputs for downstream `starfusion`.

## Key References

- <https://docs.nvidia.com/clara/parabricks/latest/documentation/tooldocs/man_rna_fq2bam.html>
- <https://raw.githubusercontent.com/alexdobin/STAR/2.7.2a/source/parametersDefault>

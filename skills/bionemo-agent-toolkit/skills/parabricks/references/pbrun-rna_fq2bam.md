# Parabricks rna_fq2bam

Collect paired or single-end RNA FASTQs, reference FASTA, STAR genome library,
output location and naming, and any required read groups. Clarify compression
and read-file handling. Validate the STAR library against the RNA workflow;
the FASTA alone does not establish library compatibility. Check pairing,
read-group errors, and the requested BAM, STAR, metrics, and log outputs.
Use a STAR library built from the same reference sequence/build as `--ref`,
with consistent annotation and contig naming. Renaming contigs cannot reconcile
different assemblies such as GRCh37 and GRCh38; obtain or rebuild a matching
library using the STAR version compatible with the selected Parabricks release.
See [RNA validation notes](parabricks-rna-validate.md) for 4.7.0 versus 4.6.0
observations. DNA reads use [fq2bam](pbrun-fq2bam.md); fusion calling uses
[starfusion](pbrun-starfusion.md) after compatible junction input is produced.

## Command Shape

Paired-end RNA-seq FASTQs:

```bash
pbrun rna_fq2bam \
  --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> \
  --genome-lib-dir /workdir/<star_genome_library>/ \
  --output-dir /outputdir/<rna_output>/ \
  --out-bam /outputdir/<sample.bam> \
  --ref /workdir/<reference.fa>
```

Single-end RNA-seq FASTQ:

```bash
pbrun rna_fq2bam \
  --in-se-fq /workdir/<sample.fastq.gz> \
  --genome-lib-dir /workdir/<star_genome_library>/ \
  --output-dir /outputdir/<rna_output>/ \
  --out-bam /outputdir/<sample.bam> \
  --ref /workdir/<reference.fa>
```

## STAR Option Mapping

Parabricks v4.7.0 documents compatibility with STAR 2.7.2a, but the CLI is not
one-to-one: many STAR camelCase flags become hyphen-separated Parabricks flags,
some STAR behavior is fixed by the pipeline, and many STAR parameters are not
exposed by `rna_fq2bam`.

| STAR option | `rna_fq2bam` equivalent | Notes |
| --- | --- | --- |
| `--genomeDir` | `--genome-lib-dir` | Use a STAR genome resource library directory already built for the same reference. |
| `--readFilesIn` | `--in-fq`, `--in-se-fq`, `--in-fq-list`, `--in-se-fq-list` | Splits paired, single-ended, and list-file inputs across separate flags. |
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
| `--outSAMunmapped` | `--out-sam-unmapped` | The manual documents a reduced behavior for sorted SAM/BAM output; verify allowed values for the selected version. |
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
| `--chimOutType` | `--out-chim-type` | Same role, but verify accepted values because The manual documents combined values such as `WithinBAM_HardClip`. |
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
| — | `--ref` | Pipeline input for the reference FASTA; STAR alignment consumes the prebuilt genome directory. You can create the STAR genome index using STAR `--runMode genomeGenerate` as a separate step. |
| — | `--out-bam` | Final pipeline BAM path after STAR alignment, coordinate sorting, and optional duplicate marking. |
| — | `--out-duplicate-metrics` | Duplicate metrics from the Parabricks/GATK-style mark-duplicates step, not STAR. |
| — | `--out-qc-metrics-dir` | QC metrics directory, not STAR. |
| — | `--no-markdups` | Controls whether the Parabricks pipeline skips duplicate marking after STAR. |
| — | `--enable-gpu-helper-threads` | GPU/CPU scheduling option. |
| — | `--num-streams-per-gpu` | GPU stream configuration. |
| — | `--gpusort` | GPU-accelerated sorting and marking. |
| — | `--use-gds` | GPUDirect Storage option. |
| — | `--memory-limit` | Sorting/postsorting system-memory limit. |
| — | `--low-memory` | Low-memory mode. |
| — | `--verbose` | Runtime verbosity. |
| — | `--logfile` | Log file path. STAR writes its own log files under the STAR output prefix. |
| — | `--tmp-dir` | Temporary directory. STAR has `--outTmpDir`, but this wrapper option applies to the pipeline. |
| — | `--keep-tmp` | Temporary-file retention. STAR has `--outTmpKeep`, but this wrapper option applies to the pipeline. |
| — | `--version` | Compatible software version reporting. |

## Key References

- <https://raw.githubusercontent.com/alexdobin/STAR/2.7.2a/source/parametersDefault>
- Parabricks 4.7.0 manual: <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_rna_fq2bam.html>

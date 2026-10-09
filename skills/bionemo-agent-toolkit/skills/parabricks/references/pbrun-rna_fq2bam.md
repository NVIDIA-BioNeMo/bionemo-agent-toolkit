# Parabricks rna_fq2bam

Collect paired or single-end RNA FASTQs, reference FASTA, STAR genome library,
output location and naming, and any required read groups. Clarify compression
and read-file handling. Validate the STAR library against the RNA workflow;
the FASTA alone does not establish library compatibility. Check pairing,
read-group errors, and the requested BAM, STAR, metrics, and log outputs.

## Reference and Index Compatibility

Use a STAR library built from the same reference sequence/build as `--ref`,
with consistent annotation and contig naming. Renaming contigs cannot reconcile
different assemblies such as GRCh37 and GRCh38; obtain or rebuild a matching
library using the STAR version compatible with the selected Parabricks release.
For **Parabricks 4.7.0**, the documented CPU STAR compatibility baseline is
**STAR 2.7.2a**. When recommending an index rebuild or replacement, state both
the matching reference build and the compatible STAR version; matching the
assembly alone is insufficient. Verify the supported STAR version in the
selected release's manual when using another Parabricks release.

Treat index metadata separately from the executable version. Upstream STAR
2.7.2a writes `versionGenome 2.7.1a` as its compatibility marker; that value
does not mean the index was built by the wrong executable. Its loader compares
this marker with `versionGenome`, not with the executable's version string.
Do not rewrite the marker to make the numbers match or demand a rebuild solely
because those two strings differ. Check the actual build provenance too.

For an index containing saved splice junctions, upstream STAR 2.7.2a rejects
an explicitly supplied `sjdbOverhang` that differs from its build value. When
reusing that index, preserve the stored value in an explicit
`--sjdb-overhang`; longer new reads alone do not change the stored junctions.
To adopt a different overhang, build a separate index with it instead of editing
metadata. The upstream loader can adopt the stored value when the option is
unset, but verify the selected Parabricks release's default handling before
relying on that. The documented 4.7.0 option default is 100; a stored value such
as 99 belongs to that particular index, not to a universal default. These
source-level checks do not prove binary integrity,
reference/annotation identity, or successful execution in the target container.

See [RNA validation notes](parabricks-rna-validate.md) for 4.7.0 versus 4.6.0
observations. DNA reads use [fq2bam](pbrun-fq2bam.md); fusion calling uses
[starfusion](pbrun-starfusion.md) after compatible junction input is produced.

## Command Shape

For Parabricks 4.7.0, every command needs a read-input mode, `--ref`,
`--genome-lib-dir`, **`--output-dir`**, and **`--out-bam`**. The output directory
and final BAM are separate required arguments; a BAM path or Docker mount does
not replace `--output-dir`. Check that both remain present after translating
upstream STAR flags, and use explicit placeholders for unresolved paths.

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

For a supplied STAR argument array or several command drafts, use
`scripts/translate_star_to_parabricks.py` (Python 3, no dependencies or GPU).
It preserves lane pairs and explicit read groups, maps supported bulk-RNA
options, and reports unsupported options and semantic changes. It never runs
STAR, Parabricks, or a decompressor. From the skill directory:

```bash
python3 scripts/translate_star_to_parabricks.py --input request.json
```

The input is one JSON object or an array of these objects:

```json
{
  "name": "sample",
  "version": "4.7.0",
  "star_args": ["--genomeDir", "/ref/star", "--readFilesIn", "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "--outSAMtype", "BAM", "SortedByCoordinate"],
  "ref": "/ref/genome.fa",
  "output_dir": "/results/star",
  "out_bam": "/results/sample.bam",
  "mark_duplicates": false
}
```

Use argument tokens, not a shell command string; an optional leading `STAR`
is accepted. Comma-separated read lists become one input pair per lane.
Explicit read groups require one group per lane, separated by a standalone
comma token, preserving STAR's `ID:...` first-tag syntax. Missing metadata is
never guessed. `mark_duplicates` defaults to false for a CPU STAR translation.

Output contains `draft_argv`, a shell-quoted `command`, `notes`, `issues`, and
`untranslated` options. `needs_review` means a draft has unresolved differences;
`invalid` has no command and exits with code 2. Neither `draft` nor exit code 0
certifies readiness or parity. The helper supports only 4.7.0 bulk alignment;
single-cell options and unrecognized STAR options require manual review.
It does not validate paths, numeric ranges, or index compatibility. Preserve
its issues alongside any command artifact rather than publishing the command
alone as an equivalent replacement.

The CLI is not one-to-one: many STAR camelCase flags become hyphen-separated
Parabricks flags, some STAR behavior is fixed by the pipeline, and many STAR
parameters are not exposed by `rna_fq2bam`.

**Translate alignment settings separately from performance tuning.** STAR's
`--runThreadN` is a CPU thread count; Parabricks 4.7.0 `--num-threads` controls
worker threads **per GPU stream**. For a CPU STAR command translation, omit
`--num-threads` to retain its documented `auto` default, which uses GPU and
system memory. Do not copy the CPU thread count as an equivalent setting.
If tuning is requested, label any override separately and account for GPU
count, streams, and memory rather than promising equivalent parallelism.

**Check output semantics as well as flag spelling.** In 4.7.0,
`--out-sam-unmapped Within_KeepPairs` behaves like `Within` for the sorted output.
Distinguish ordinary unmapped-read inclusion from STAR's extra `KeepPairs`
behavior: for a multi-mapping mate, it records an unmapped-mate copy for each
alignment and, in unsorted output, keeps the records adjacent. STAR 2.7.2a's
sorted-BAM path emits the unmapped mate without these extra copies; the loss
of `KeepPairs` semantics does **not** establish that all unmapped mates vanish.
Ask which record-level behavior the consumer requires before rejecting a
migration. A required copy for every alignment needs a separate compatible
path or validated reconstruction; neither `Within` alone nor separate
`--out-reads-unmapped Fastx` files fulfills that contract.

`--out-chim-type` takes a single documented value, such as
`WithinBAM_HardClip`; do not copy STAR's two tokens `WithinBAM HardClip`.
Chimeric output is disabled when `--min-chim-segment` is zero, its default.
Use `--no-markdups` when the user requires a sorted BAM without duplicate
marking; normal `rna_fq2bam` includes duplicate marking. Describe any such
semantic limits beside the proposed command, without claiming full parity.

| STAR option | `rna_fq2bam` equivalent | Notes |
| --- | --- | --- |
| `--genomeDir` | `--genome-lib-dir` | Use a STAR genome resource library directory already built for the same reference. |
| `--readFilesIn` | `--in-fq`, `--in-se-fq`, `--in-fq-list`, `--in-se-fq-list` | Splits paired, single-ended, and list-file inputs across separate flags. |
| `--readFilesCommand` | `--read-files-command` | Same role: command that emits FASTQ/FASTA text to stdout, such as `zcat`. |
| `--readNameSeparator` | `--read-name-separator` | Same role. |
| `--outFileNamePrefix` | `--output-dir`, `--out-prefix` | `--output-dir` controls the generated output directory; `--out-prefix` controls the prefix for output data. |
| `--outSAMtype BAM SortedByCoordinate` | Implicit pipeline behavior plus `--out-bam` | `rna_fq2bam` outputs a sorted BAM path via `--out-bam`; it does not expose generic `--outSAMtype`. |
| `--outSAMattrRGline` | Read group in `--in-fq` / `--in-se-fq`, or `--read-group-sm`, `--read-group-lb`, `--read-group-pl`, `--read-group-id-prefix` | Not a full one-to-one replacement for arbitrary STAR read group lines. |
| `--runThreadN` | No direct equivalent; `--num-threads` is a separate tuning control | Keep the `auto` default for command translation; workers per GPU stream are not STAR's total CPU thread count. |
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
- STAR 2.7.2a unmapped-mate output: <https://github.com/alexdobin/STAR/blob/2.7.2a/source/ReadAlign_outputAlignments.cpp>
- STAR 2.7.2a index loader: <https://github.com/alexdobin/STAR/blob/2.7.2a/source/Genome.cpp>
- STAR 2.7.2a index metadata writer: <https://github.com/alexdobin/STAR/blob/2.7.2a/source/genomeParametersWrite.cpp>
- Parabricks 4.7.0 manual: <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_rna_fq2bam.html>

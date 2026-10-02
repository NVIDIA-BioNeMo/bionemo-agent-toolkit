# Parabricks minimap2

Confirm ONT, PacBio HiFi or CLR, or a supported splice-aware RNA use case.
Collect the reference or minimizer index, reads or supported alignment input,
and BAM or CRAM destination. Clarify presets, known-sites, intervals, and
read groups when needed. Validate the preset against the sequencing technology
and analysis goal, not a filename, and investigate index or preset errors.
This operation covers alignment and preprocessing, not completed variant
calling. Ordinary short-read BWA-MEM alignment uses [fq2bam](pbrun-fq2bam.md).

## Command Shape

```bash
pbrun minimap2 \
  --ref /workdir/<reference.fa> \
  --in-fq /workdir/<long_reads.fastq.gz> \
  --out-bam /outputdir/<aligned.bam>
```

## minimap2/GATK Option Mapping

Parabricks v4.7.0 documents
`minimap2` as a GPU long-read alignment workflow that can sort, mark
duplicates, and optionally run BQSR, so the CLI maps to several upstream
commands rather than one single tool.

| Baseline option | `pbrun minimap2` equivalent | Notes |
| --- | --- | --- |
| `minimap2 <reference>` | `--ref` | Required reference FASTA path. |
| BAM/CRAM input for preprocessing workflow | `--in-bam` | Input BAM/CRAM mode. |
| `minimap2 -x` | `--preset` | Supports documented presets such as `map-pbmm2`, `map-hifi`, `map-ont`, `lr:hq`, `splice`, `splice:hq`, and `splice:sr`. |
| `minimap2 -t` | `--num-threads` | Processing thread count. |
| `minimap2 -k` | `--minimizer-kmer-len`, `-k` | Minimizer k-mer length. |
| `minimap2 -uf` | `--forward-transcript-strand`, `-uf` | Splice preset strand control. |
| `minimap2 -ub` | `--both-strands`, `-ub` | Splice preset strand control. |
| minimap2 splice junction BED options | `--jump-bed`, `-j`; `--junc-bed` | Splice annotation inputs. |
| `minimap2 --MD` / `--md` | `--md` | Output MD tag. |
| `minimap2 --eqx` | `--eqx` | Write `=/X` CIGAR operators. |
| `minimap2 -y` | `--copy-comment`, `-y` | Append FASTQ comment to BAM output. |
| `minimap2 -R` | `--read-group-*` flags | Builds read group fields from explicit tags rather than accepting the raw minimap2 string. |
| `minimap2 -a` SAM output piped to sorting | `--out-bam` | Writes sorted BAM/CRAM output. |
| GATK/Picard `MarkDuplicates -M` | `--out-duplicate-metrics` | Duplicate metrics output after marking duplicates when applicable. |
| Upstream minimap2 options not listed here | No direct equivalent | Not documented for this tool. |
| — | `--pbmm2`, `--pbmm2-unmapped` | Compatibility mode for pbmm2-style output and unmapped records. |
| — | `--standalone-bqsr` | Mode control for running BQSR after sorted BAM generation. |
| — | `--nstreams`, `--max-queue-chunks`, `--max-queue-reads`, `--chunk-size` | GPU/CPU pipeline queue and chunk controls. |

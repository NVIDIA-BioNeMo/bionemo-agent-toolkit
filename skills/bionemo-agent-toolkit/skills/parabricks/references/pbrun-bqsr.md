# Parabricks bqsr

Collect aligned reads, reference FASTA, one or more known-sites VCFs, and a
recalibration-report destination. Known-sites resources and their indexes must
match the reference build. Ask about intervals and GPU count if relevant, and
whether BQSR is appropriate for a nonstandard organism or reference.
Review known-sites and interval errors before accepting the report. The report
does not change BAM qualities; [applybqsr](pbrun-applybqsr.md) applies it.

## Command Shape

```bash
pbrun bqsr \
  --ref /workdir/<reference.fa> \
  --in-bam /workdir/<input.bam> \
  --knownSites /workdir/<known-sites.vcf.gz> \
  --out-recal-file /outputdir/<sample.recal.txt>
```

## BaseRecalibrator Option Mapping

Parabricks v4.7.0 documents `bqsr` as the GATK4 counterpart for
generating a recalibration report, but shortens several GATK option names.

| GATK option | `pbrun bqsr` equivalent | Notes |
| --- | --- | --- |
| `--known-sites` | `--knownSites` | Required known-sites VCF; can be repeated. |
| `--output`, `-O` | `--out-recal-file` | Required output recalibration report. |
| `--arguments_file`, GATK engine/read-filter flags, covariate-control flags | No direct equivalent | Not documented for this tool. |

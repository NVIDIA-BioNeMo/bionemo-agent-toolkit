# Parabricks pacbio_germline

Establish HiFi or CLR before selecting a preset or model. Collect the supported
FASTQ or alignment input, reference, variant destination, and required PacBio
resources; ask about sample name and intervals when relevant. Confirm subtype
and model compatibility from provenance rather than filenames, and inspect
preset or model errors. ONT and short-read data need different routes. For
PacBio alignment alone, use [minimap2](pbrun-minimap2.md).

## minimap2/DeepVariant Option Mapping

Parabricks v4.7.0
documents this as a long-read pipeline using minimap2 alignment and
DeepVariant calling.

| Baseline option | `pbrun pacbio_germline` equivalent | Notes |
| --- | --- | --- |
| minimap2 `-x map-pbmm2` or PacBio preset | `--preset map-pbmm2` or `--preset map-hifi` | Confirm PacBio subtype and selected version before changing the default. |
| DeepVariant `--model_type PACBIO` | PacBio pipeline default, or `--mode`/model flags where documented | Use PacBio-specific mode/model settings from the selected version. |
| Upstream minimap2/DeepVariant options not listed here | No direct equivalent | Not documented for this tool. |
| — | `--pbmm2`, `--pbmm2-unmapped` | Compatibility controls for pbmm2-style output. |

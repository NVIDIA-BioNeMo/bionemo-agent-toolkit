# Parabricks ont_germline

Confirm Oxford Nanopore germline data and collect the supported FASTQ or
alignment input, reference, variant destination, and required ONT model bundle.
Ask about sample name and intervals when relevant. Validate the long-read
preset and model against ONT chemistry and assay; filenames alone cannot
establish compatibility. PacBio and short-read inputs need their own routes.
For ONT alignment alone, use [minimap2](pbrun-minimap2.md).

## minimap2/DeepVariant Option Mapping

Parabricks v4.7.0 documents
this as a long-read pipeline using minimap2 alignment and DeepVariant calling.

| Baseline option | `pbrun ont_germline` equivalent | Notes |
| --- | --- | --- |
| minimap2 `-x map-ont` or ONT preset | `--preset map-ont` or selected ONT preset | Confirm ONT chemistry/use case and selected version before changing defaults. |
| DeepVariant `--model_type ONT` | ONT pipeline default, or `--mode`/model flags where documented | Use ONT-specific mode/model settings from the selected version. |
| Upstream minimap2/DeepVariant options not listed here | No direct equivalent | Not documented for this tool. |

# Parabricks pangenome_aware_deepvariant

Verify this caller exists in the requested release. Collect the compatible
linear reference, graph bundle, reads or prepared alignments, model bundle,
and variant destination. Establish alignment provenance and check that the
inputs match the caller's documented requirements.
Inspect graph and model errors. Standard `deepvariant` and the full
`pangenome_germline` pipeline have different scopes and resource requirements;
compatibility cannot be inferred across graph bundles.

## DeepVariant/Pangenome Option Mapping

This is not a
drop-in replacement for standard `pbrun deepvariant`; graph and pangenome
resource flags are part of the command surface.

| Baseline option | `pbrun pangenome_aware_deepvariant` equivalent | Notes |
| --- | --- | --- |
| DeepVariant `--ref` | `--ref` | Linear reference FASTA; must match pangenome resources. |
| DeepVariant `--reads` | `--in-bam` or selected input flag | Prepared pangenome-aware alignment input when supported. |
| Pangenome graph input | `--pangenome` or version-specific graph/resource flag | Verify exact resource flag names in the selected version. |
| DeepVariant regions | `--interval` or `--interval-file` | Verify interval support for the selected pangenome workflow. |
| DeepVariant make-examples options | Matching explicit Parabricks flags where documented | Use only flags listed in the selected Parabricks tool reference. |
| Standard DeepVariant options not listed here | No direct equivalent | Not documented for this tool. |
| — | Pangenome graph/resource input flags | Standard DeepVariant is linear-reference based. |
| — | GPU graph/pangenome runtime controls | GPU implementation tuning. |
| — | Parabricks TensorRT model-file controls | Model deployment differs from Google DeepVariant's Keras/TensorFlow runtime. |

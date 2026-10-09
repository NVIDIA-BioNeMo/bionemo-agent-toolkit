# Parabricks pangenome_aware_deepvariant

Verify this caller exists in the requested release. Collect the compatible
linear reference, graph bundle, reads or prepared alignments, model bundle,
and variant destination. Establish alignment provenance and check that the
inputs match the caller's documented requirements.
Inspect graph and model errors. Standard `deepvariant` and the full
`pangenome_germline` pipeline have different scopes and resource requirements;
compatibility cannot be inferred across graph bundles.

## Parabricks 4.7.0 command

For prepared BAM/CRAM input, the four required arguments are `--ref`,
`--pangenome` (the GBZ graph), `--in-bam`, and `--out-variants`:

```bash
pbrun pangenome_aware_deepvariant \
  --ref /workdir/<reference.fa> \
  --pangenome /workdir/<graph.gbz> \
  --in-bam /workdir/<sample.bam> \
  --out-variants /outputdir/<sample.vcf.gz>
```

Check that the linear reference, input alignments, graph paths, and selected
model belong to a compatible setup. This standalone caller consumes prepared
alignments; it does not require rerunning the `pangenome_germline` FASTQ pipeline.

## Comparing with Google's implementation

The 4.7.0 manual documents three sources of output differences. Investigate
them separately after matching inputs, model versions, and comparison settings:

- **CNN inference:** TensorRT and Keras can differ by about `10^-5` in predicted
  scores. The manual reports observed differing variants among zero-quality
  `RefCalls`; this is an observation, not a guarantee about every dataset.
- **Supplementary-read ordering:** with `--keep-supplementary-alignments`,
  equal sorting keys can leave reads in a different order. For a controlled
  upstream comparison, the manual recommends replacing `std::sort` with
  `std::stable_sort` in `BuildPileupForOneSample` in `pileup_image_native.cc`.
- **GBZ query caching:** Google's fast path can make graph-query results depend
  on prior query order. Parabricks disables it. For comparison only, the manual
  describes disabling **both** `updateCache` and the cached-range lookup in
  `GbzReader::Query()` in `deepvariant/third_party/nucleus/io/gbz_reader.cc`.
  Disabling only cache updates leaves the cache-hit path in place. This change
  can slow the upstream implementation substantially and is not routine tuning.

Keep any upstream patches in a separate comparison build, record versions and
settings, and measure output differences before claiming parity. Do not
present these C++ changes as `pbrun` flags, silently alter production software,
or promise that they remove TensorRT numerical differences.

## DeepVariant/Pangenome Option Mapping

This is not a
drop-in replacement for standard `pbrun deepvariant`; graph and pangenome
resource flags are part of the command surface.

| Baseline option | `pbrun pangenome_aware_deepvariant` equivalent | Notes |
| --- | --- | --- |
| DeepVariant `--ref` | `--ref` | Linear reference FASTA; must match pangenome resources. |
| DeepVariant `--reads` | `--in-bam` | Required prepared BAM/CRAM input in 4.7.0. |
| Pangenome graph input | `--pangenome` | Required GBZ graph in 4.7.0. |
| DeepVariant `--output_vcf` | `--out-variants` | Required variant output in 4.7.0. |
| DeepVariant regions | `--interval` or `--interval-file` | Verify interval support for the selected pangenome workflow. |
| DeepVariant make-examples options | Matching explicit Parabricks flags where documented | Use only flags listed in the selected Parabricks tool reference. |
| Standard DeepVariant options not listed here | No direct equivalent | Not documented for this tool. |
| — | Pangenome graph/resource input flags | Standard DeepVariant is linear-reference based. |
| — | GPU graph/pangenome runtime controls | GPU implementation tuning. |
| — | Parabricks TensorRT model-file controls | Model deployment differs from Google DeepVariant's Keras/TensorFlow runtime. |

## Key References

- Parabricks 4.7.0 manual: <https://archive.docs.nvidia.com/clara/parabricks/4.7.0/Documentation/ToolDocs/man_pangenome_aware_deepvariant.html>

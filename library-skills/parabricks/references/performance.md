# Parabricks Alignment Performance Guidance

Shared BWA-stream tuning guidance for the `fq2bam` and `fq2bam_meth` commands.
(Giraffe uses `--nstreams`; see `pbrun-giraffe.md`.)

## BWA Streams

Prefer the documented automatic stream selection for general commands: leave
`--bwa-nstreams` unset, or set `--bwa-nstreams auto` only when making the
default explicit. Current NVIDIA Parabricks documentation says Parabricks
automatically chooses an optimal number of BWA streams from the GPU device
memory specification.

Use integer `--bwa-nstreams` values only for benchmark-driven tuning or
memory-pressure troubleshooting after confirming the selected Parabricks
version's docs. More streams increase device memory use, so fixed stream counts
should not be part of conservative default command templates.

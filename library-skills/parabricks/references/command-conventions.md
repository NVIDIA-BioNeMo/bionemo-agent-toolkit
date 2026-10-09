# Command conventions

Read this reference once when preparing or reviewing a Parabricks command.
Individual tool references contain biological constraints, concrete examples,
and unique options. [shared-options.md](shared-options.md) defines repeated
mappings once and lists the tools to which each applies.

## Preparing inputs

Confirm the target release, execution host or launcher, assay, sequencing
technology, reference build, sample relationships, and desired outputs. Use
explicit host mounts and container paths for inputs, indexes, output, and
scratch space. Collect optional intervals, logs, worker counts, and metrics
only when relevant. Leave unknown values as visible placeholders; obtain sample
names, read groups, reference resources, and model or graph bundles from the user.

For runtime or installation questions, use
[runtime-environment.md](runtime-environment.md). Probe the intended execution
host; local hardware does not describe a remote target. Follow the skill's probe
consent rules. Preparing a workload command does not authorize executing it.

## Translating options

The mapping tables primarily describe Parabricks 4.7.1. Check each selected
release's NVIDIA tool manual before finalizing syntax, defaults, optional flags,
input modes, or output naming. An upstream option without a documented mapping
has no assumed Parabricks equivalent; do not pass it through or borrow an option
from another `pbrun` tool. Flag availability does not establish biological parity.
In option tables, **—** in the baseline column denotes a Parabricks-only control.

Preserve an upstream option's value only when its meaning, units, and scope
match the Parabricks option. For partial mappings, omit the setting from the
base command or present it as a separate tuning choice with its own rationale.
An explanatory caveat does not make a copied value equivalent; check that the
generated command follows the mapping explanation.

GATK and Picard wrapper translations shared by `applybqsr`, `bam2fq`,
`bammetrics`, `bamsort`, `bqsr`, `collectmultiplemetrics`, `fq2bam`,
`fq2bam_meth`, `genotypegvcf`, `giraffe`, `haplotypecaller`, `indexgvcf`,
`markdup`, `minimap2`, and `mutectcaller` are:

| Baseline option | Parabricks option | Interpretation |
| --- | --- | --- |
| `--TMP_DIR` or `--tmp-dir` | `--tmp-dir` | Wrapper scratch directory; mount it explicitly. This translation also applies to `germline`. |
| `--VERBOSITY` or `--verbosity` | `--verbose` | Partial mapping: a boolean, not the upstream log-level enum. |
| `--version` | `--version` | Report compatible software versions. |

The RNA references retain their STAR-specific logging and scratch-directory
comparisons. For GPU, threading, memory, and algorithm controls, combine the
selected tool's table with its entries in the shared mappings. Respect the
listed tool scope because meanings and availability vary by command.

For BWA stream defaults on `fq2bam` and `fq2bam_meth`, see
[performance.md](performance.md). Giraffe `--nstreams` tuning stays in
`pbrun-giraffe.md`.

## Shared wrapper controls

These controls recur across the tool references. Include them only for an
identified need, after checking support in the chosen tool and release.

| Option | Role |
| --- | --- |
| `--logfile` | Wrapper log destination. |
| `--x3` | Display the full underlying command-line arguments. |
| `--with-petagene-dir` | PetaGene integration directory. |
| `--keep-tmp` | Retain temporary files. |
| `--no-seccomp-override` | Change the wrapper's Docker seccomp behavior; it is not a routine performance flag. |
| `--preserve-file-symlinks` | Control wrapper handling of symlinked paths. |

## Validating a run

Before presenting a command, check its required arguments as a complete set;
translating the user's upstream flags alone may omit required wrapper inputs
or outputs. For example, `rna_fq2bam` needs both `--output-dir` for generated
STAR outputs and `--out-bam` for the final BAM. A Docker output mount does not
supply either argument. Retain explicit placeholders when a required path is
unknown. Check this from the command text without launching a container.

Before execution, check that every input and required index resolves through
the mounts and that reference, known-sites, model, and graph resources are
compatible with the assay and each other. CRAM decoding needs the appropriate
reference. Confirm writable output and scratch directories with adequate space.

Treat inputs as read-only and never overwrite existing data. When a tool writes
beside its input (for example `indexgvcf` writes the `.tbi` next to the GVCF) and
the input mount is read-only, plan a copy to a writable mount and index the
copy. Check that destination files do not already exist before copying, ask
before replacing anything, and keep commands labeled as a plan until the user
runs them.

After an authorized run, verify completion and the requested output artifacts,
including optional metrics, recalibration reports, and indexes. An existing
directory alone is not evidence of success. Review logs for malformed inputs,
reference or resource mismatches, missing indexes, container mount failures,
CUDA errors, and exhausted memory or storage. Apply the selected tool's
additional biological checks, and report unverified checks as pending.

Do not claim exact performance, caller accuracy, or CPU/GPU output equivalence
without a comparable benchmark or validation run.

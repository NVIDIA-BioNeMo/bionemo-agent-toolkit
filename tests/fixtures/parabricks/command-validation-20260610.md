# Parabricks RNA Skill Command Validation — 4.7.0 vs 4.6.0

Generated: 2026-06-10

Scope: commands found under `/data/genomics-acceleration-skill/skills/parabricks-rna`.

Excluded from validation:

- Existing validation artifact: `VALIDATION-parabricks-4.7.0.md`.
- Non-command prose references to `pbrun ...`.

Validation method:

- The skill examples are Docker-wrapped commands. The validator tiers validate the inner `pbrun ...` command, so each row below reports the extracted inner command.
- **L0 / static** = `validate_command_static`.
- **L1 / help** = `validate_command_help`, which checks flags against the container help text.

## Results table

| File | Command | Parabricks 4.7.0 validator results | Parabricks 4.6.0 validator results | Explanation / possible action |
|---|---|---|---|---|
| `SKILL.md` | `pbrun rna_fq2bam --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> --genome-lib-dir /workdir/<genome_library>/ --output-dir /outputdir/<rna_output>/ --out-bam /outputdir/<sample.bam> --ref /workdir/<reference.fa>` | **L0: pass**. Warnings: placeholder output paths are not present/writable in this host context. **L1: pass**. | **L0: pass**. Same placeholder output-path warnings. **L1: skipped** with `help_capture_failed` for `rna_fq2bam --help` exit 255 in the validator capture path. | The command flags are valid by static inventory for both versions and accepted by 4.7.0 help. For 4.6.0, manual GPU-enabled help capture succeeds, so the L1 skip is a help-capture environment issue, not a command-flag failure. Replace placeholders and ensure `/outputdir/<rna_output>/` and `/outputdir` exist inside the container. |
| `SKILL.md` | `pbrun rna_fq2bam --in-se-fq /workdir/<sample.fastq.gz> --genome-lib-dir /workdir/<genome_library>/ --output-dir /outputdir/<rna_output>/ --out-bam /outputdir/<sample.bam> --ref /workdir/<reference.fa>` | **L0: pass**. Warnings: placeholder output paths are not present/writable in this host context. **L1: pass**. | **L0: pass**. Same placeholder output-path warnings. **L1: skipped** with `help_capture_failed` for `rna_fq2bam --help` exit 255 in the validator capture path. | Same as above. The single-end input mode is valid. For 4.6.0 L1, expose GPUs to the help-capture path or treat this as an environment limitation. Replace placeholders before use. |
| `SKILL.md` | `pbrun starfusion --chimeric-junction /workdir/<chimeric_junction.out> --genome-lib-dir /workdir/<genome_resource_library>/ --output-dir /outputdir/<starfusion_output>/` | **L0: pass**. Warning: placeholder output directory is not present/writable in this host context. **L1: pass**. | **L0: pass**. Same placeholder output-path warning. **L1: pass**. | Command flags are accepted for both Parabricks versions. Replace placeholders, provide a real `Chimeric.out.junction`, use the correct fusion genome resource library, and ensure the output directory exists inside the container. |
| `pbrun-rna_fq2bam.md` | `pbrun rna_fq2bam --in-fq /workdir/<sample_R1.fastq.gz> /workdir/<sample_R2.fastq.gz> --genome-lib-dir /workdir/<star_genome_library>/ --output-dir /outputdir/<rna_output>/ --out-bam /outputdir/<sample.bam> --ref /workdir/<reference.fa>` | **L0: pass**. Warnings: placeholder output paths are not present/writable in this host context. **L1: pass**. | **L0: pass**. Same placeholder output-path warnings. **L1: skipped** with `help_capture_failed` for `rna_fq2bam --help` exit 255 in the validator capture path. | Command flags are valid. The only difference from the `SKILL.md` paired-end command is the placeholder genome-library path name. Replace placeholders and create/mount output directories. |
| `pbrun-rna_fq2bam.md` | `pbrun rna_fq2bam --in-se-fq /workdir/<sample.fastq.gz> --genome-lib-dir /workdir/<star_genome_library>/ --output-dir /outputdir/<rna_output>/ --out-bam /outputdir/<sample.bam> --ref /workdir/<reference.fa>` | **L0: pass**. Warnings: placeholder output paths are not present/writable in this host context. **L1: pass**. | **L0: pass**. Same placeholder output-path warnings. **L1: skipped** with `help_capture_failed` for `rna_fq2bam --help` exit 255 in the validator capture path. | Command flags are valid. Replace placeholders and ensure output paths exist. 4.6.0 L1 skip is due to validator help capture without GPU exposure. |
| `pbrun-starfusion.md` | `pbrun starfusion --chimeric-junction /workdir/<chimeric_junction.out> --genome-lib-dir /workdir/<genome_resource_library>/ --output-dir /outputdir/<starfusion_output>/` | **L0: pass**. Warning: placeholder output directory is not present/writable in this host context. **L1: pass**. | **L0: pass**. Same placeholder output-path warning. **L1: pass**. | Command flags are valid for both versions. Runtime success still depends on valid input files/resources and writable mounted output. |

## Notes on repeated findings

### Placeholder path warnings

All L0 warnings are from placeholder output paths such as `/outputdir/<rna_output>/`, `/outputdir/<sample.bam>`, and `/outputdir/<starfusion_output>/`. These are expected in documentation examples because the paths are placeholders and are not actual directories on the validation host. They should be replaced with real mounted container paths before running.

### 4.6.0 `rna_fq2bam` L1 help-capture issue

For every `rna_fq2bam` command on Parabricks 4.6.0, L1 returned:

```text
verdict: skipped
rule: help_capture_failed
message: `docker run ... pbrun rna_fq2bam --help` failed (exit 255)
```

A manual GPU-enabled help capture succeeds:

```bash
docker run --rm --gpus all \
  nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1 \
  pbrun rna_fq2bam --help
```

Manual result: exit code `0`.

Interpretation: the 4.6.0 `rna_fq2bam` binary refuses to emit help unless GPUs are exposed. The validator's L1 capture path does not satisfy that condition for this tool/version. This is not evidence that the skill command flags are invalid.

## Overall conclusion

- All six extracted `pbrun` commands pass **L0 static validation** for both Parabricks **4.7.0** and **4.6.0**.
- All `starfusion` commands pass **L1 help validation** for both versions.
- All `rna_fq2bam` commands pass **L1 help validation** for **4.7.0**.
- All `rna_fq2bam` commands on **4.6.0** are blocked only by the L1 help-capture GPU-exposure issue; manual GPU-enabled help capture succeeds.

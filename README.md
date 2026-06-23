<img src="assets/image.jpg" alt="NVIDIA BioNeMo Agent Toolkit" width="100%"/>

# NVIDIA BioNeMo Agent Toolkit

**Turn any agent into a life science expert with NVIDIA BioNeMo skills.**

Protein folding, molecular docking, generative chemistry, genomics analysis,
protein design, and biomarker discovery — a decade of NVIDIA life sciences
libraries, tools, and models, packaged as ready-to-call agent skills.

Each skill gives a coding or scientific agent structured instructions, scripts,
and references to select a tool, prepare inputs, run it, inspect outputs, and
explain results — across both single tasks and multi-step scientific workflows.

## Install
Skills install with the [`skills` CLI](https://github.com/vercel-labs/skills):

```bash
# interactive — pick a skill + install destination
npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit

# one skill, no prompts
npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit --skill boltz2-nim --yes

# target a specific agent (repeatable)
npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit --skill boltz2-nim --agent claude-code
npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit --skill boltz2-nim --agent codex

# browse the catalog without installing
npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit --list
```

The repo also ships self-hosted plugin marketplaces:
 - **Codex:** [.agents/plugins/marketplace.json](.agents/plugins/marketplace.json)
 - **Claude Code:** [.claude-plugin/marketplace.json](.claude-plugin/marketplace.json)
so the `bionemo-agent-toolkit` plugin installs through each agent's native plugin
flow as well. Skills are also discoverable by partner harnesses directly from the repo.

## What's here

```
workflows/            Multi-step meta-skills that compose the skills below
  generative_protein_binder_design/ RFdiffusion -> ProteinMPNN -> OpenFold3

nim-skills/           BioNeMo NIM skills (OpenFold, Boltz-2, DiffDock, GenMol,
                      RFdiffusion, ProteinMPNN, Evo2, MSA-Search, MolMIM, ...)
open-models-skills/   Open-model skills (Proteina-Complexa, KERMT, ...)
library-skills/       CUDA-X library skills (nvMolKit, cuEquivariance, parabricks, ...)

plugins/bionemo-agent-toolkit/   Generated installable plugin (claude + codex
                                 manifests + a copy of every catalog skill)
.claude-plugin/marketplace.json  Claude Code marketplace
.agents/plugins/marketplace.json Codex marketplace
skills.sh.json                   `npx skills add` catalog grouping
```

Every skill is a directory with a `SKILL.md` (YAML frontmatter + instructions),
optional `references/`, and optional `scripts/`.

## License

This project is dual-licensed:

- **Source code** (scripts, tests, build tooling): [Apache-2.0](LICENSE-APACHE-2.0)
- **Skills and documentation** (SKILL.md, workflows, READMEs): [CC-BY-4.0](LICENSE-CC-BY-4.0)

See [LICENSE](LICENSE) for the full dual-license statement. Individual skills may reference third-party
data sources with their own terms; consult each skill's references and the [NOTICE](NOTICE) file.

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

## Skill Catalog

| Product | Description | Skills |
|---------|-------------|--------|
| **Protein Binder Design** | End-to-end de novo binder design workflows — a NIM route and a Proteina-Complexa route. | [`protein-binder-design`](workflows/generative-protein-binder-design/protein-binder-design), [`complexa-binder-design`](workflows/generative-protein-binder-design/complexa-binder-design) |
| **Generative Virtual Screening workflow** | Generate candidate molecules, dock them to a target, and score binding affinity (GenMol → DiffDock → Boltz-2). | [`drug-discovery-pipeline`](nim-skills/meta-skills/drug-discovery-pipeline) |
| **MSA-enabled protein structure prediction workflow** | Build a multiple sequence alignment, then predict structure (MSA-Search → OpenFold3). | [`msa-structure-prediction-pipeline`](nim-skills/meta-skills/msa-structure-prediction-pipeline) |
| **Boltz-2** | Biomolecular structure prediction + binding affinity (NIM). | [`boltz2-nim`](nim-skills/boltz2-nim) |
| **DiffDock** | Small-molecule docking and binding-pose prediction (NIM). | [`diffdock-nim`](nim-skills/diffdock-nim) |
| **Evo 2** | DNA sequence generation and variant scoring (NIM). | [`evo2-nim`](nim-skills/evo2-nim) |
| **GenMol** | De novo molecule generation, scaffold decoration, lead optimization (NIM). | [`genmol-nim`](nim-skills/genmol-nim) |
| **MolMIM** | Latent-space small-molecule generation and optimization (NIM). | [`molmim-nim`](nim-skills/molmim-nim) |
| **MSA-Search** | Multiple sequence alignments via ColabFold (NIM). | [`msa-search-nim`](nim-skills/msa-search-nim) |
| **OpenFold2** | Monomer protein structure prediction (NIM). | [`openfold2-nim`](nim-skills/openfold2-nim) |
| **OpenFold3** | Biomolecular complex structure prediction (NIM). | [`openfold3-nim`](nim-skills/openfold3-nim) |
| **ProteinMPNN** | Inverse folding / sequence design for a target backbone (NIM). | [`proteinmpnn-nim`](nim-skills/proteinmpnn-nim) |
| **RFdiffusion** | De novo protein backbone and binder design (NIM). | [`rfdiffusion-nim`](nim-skills/rfdiffusion-nim) |
| **Proteina-Complexa** | Protein binder design for protein and small molecule targets. Combines a pretrained flow-based generative model (built on La-Proteina) with inference-time optimization for high-quality binder generation. | [`complexa-setup`](open-models-skills/proteina-complexa/complexa-setup), [`complexa-target`](open-models-skills/proteina-complexa/complexa-target), [`complexa-design`](open-models-skills/proteina-complexa/complexa-design), [`complexa-sweep`](open-models-skills/proteina-complexa/complexa-sweep), [`complexa-evaluate-pdbs`](open-models-skills/proteina-complexa/complexa-evaluate-pdbs) |
| **KERMT** | Pretrained graph neural network for molecular property prediction (ADMET). Multi-task extension of GROVER with accelerated data loading via cuik-molmaker. SOTA on real-world ADMET data. | [`kermt-setup`](open-models-skills/kermt/skills/kermt-setup), [`kermt-infer`](open-models-skills/kermt/skills/kermt-infer), [`kermt-embed`](open-models-skills/kermt/skills/kermt-embed), [`kermt-finetune`](open-models-skills/kermt/skills/kermt-finetune), [`kermt-continue-pretrain`](open-models-skills/kermt/skills/kermt-continue-pretrain), [`kermt-pretrain-scratch`](open-models-skills/kermt/skills/kermt-pretrain-scratch), [`kermt-add-cmim-pretrain`](open-models-skills/kermt/skills/kermt-add-cmim-pretrain), [`kermt-monitor`](open-models-skills/kermt/skills/kermt-monitor) |
| **Parabricks** | Agent-ready skills built on Parabricks for accelerated genomic analysis and workflows. | [`parabricks`](library-skills/parabricks), [`genomics-workflow-acceleration`](library-skills/genomics-workflow-acceleration) |
| **nvMolKit** | GPU-accelerated cheminformatics library for molecular fingerprinting, Tanimoto/cosine similarity, Butina clustering, conformer generation (ETKDGv3), MMFF geometry optimization, and substructure search. | [`nvmolkit-usage`](library-skills/nvMolKit) |
| **cuEquivariance** | Build equivariant neural-network primitives (segmented tensor products, CG coefficients). | [`cuequivariance`](library-skills/cuequivariance) |

## Evaluating NIM Skill Lift

NIM skill evaluation has two levels:

1. **Hosted skill lift with ACES/SkillEvaluator.** Each NIM skill ships a
   single, bounded `evals/evals.json` case plus `evals/config.yml`.
   `astra-skill-eval` converts the case into Harbor tasks and runs the same
   prompt both with and without the skill. The task requires a call to the real
   hosted NVIDIA NIM endpoint; whether each agent successfully discovers and
   executes that call is part of the measurement. The ACES default grader
   combines deterministic trajectory checks with LLM judgments to report skill
   lift.
2. **Native Harbor tasks (TODO).** Deterministic RLVR-style graders are planned
   for workflows requiring local GPU deployment, custom scientific scoring, or
   additional infrastructure. They are not yet shipped as supported evaluation
   coverage. These tasks will live under `evals/harbor/` and provide their own
   verifier.

The hosted lift evaluations require `NGC_API_KEY` in the invoking shell; each
skill's `evals/config.yml` passes it into the Harbor tasks. No local NIM
deployment is required. The commands below disable the optional Astra viewer
upload, allow up to twice the default agent runtime, and write reports under
`.nv-aces-verify/`.

OpenFold3 and the MSA-Search to OpenFold3 workflow are pending validation. Their
current hosted runs timed out and should not yet be used for pass/fail or model
comparison.

- **Evo 2**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/evo2-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **OpenFold2**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/openfold2-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **OpenFold3 (pending validation)**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/openfold3-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **Boltz-2**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/boltz2-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **DiffDock**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/diffdock-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **GenMol**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/genmol-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **MolMIM**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/molmim-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **RFdiffusion**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/rfdiffusion-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **MSA-Search**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/msa-search-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **ProteinMPNN**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/proteinmpnn-nim --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **MSA-Search to OpenFold3 workflow (pending validation)**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/meta-skills/msa-structure-prediction-pipeline --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

- **Generative virtual screening workflow**

  ```bash
  ASTRA_HARBOR_VIEWER_UPLOAD=0 astra-skill-eval evaluate nim-skills/meta-skills/drug-discovery-pipeline --agent-eval -a claude-code --n-attempts 1 --n-concurrent 1 --timeout-multiplier 2.0 --results-dir "$PWD/.nv-aces-verify"
  ```

Every skill is a directory with a `SKILL.md` (YAML frontmatter + instructions),
optional `references/`, and optional `scripts/`. The generated, installable plugin
lives in [`plugins/bionemo-agent-toolkit/`](plugins/bionemo-agent-toolkit).

## License

This project is dual-licensed:

- **Source code** (scripts, tests, build tooling): [Apache-2.0](LICENSE-APACHE-2.0)
- **Skills and documentation** (SKILL.md, workflows, READMEs): [CC-BY-4.0](LICENSE-CC-BY-4.0)

See [LICENSE](LICENSE) for the full dual-license statement. Individual skills may reference third-party
data sources with their own terms; consult each skill's references and the [NOTICE](NOTICE) file.

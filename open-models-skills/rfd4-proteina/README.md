# RFD4-Proteina Open-Model Skills

These nine open-model skills operate the native RFProteina runtime. Model commands,
configuration files, checkpoints, and inputs belong to the separate model
checkout at `RFPROTEINA_ROOT`; this catalog supplies instructions and helpers.
Generation requires the GPU and dependencies documented by the chosen model
revision. For NIM service access, use the separate
[`rfd4-proteina-nim`](../../nim-skills/rfd4-proteina-nim/SKILL.md) skill.

| Skill | Purpose |
| --- | --- |
| [`rfd4-proteina-setup`](rfd4-proteina-setup/SKILL.md) | Install the runtime, obtain checkpoints, check readiness, and run a monomer smoke test. |
| [`rfd4-proteina-annotated-cif`](rfd4-proteina-annotated-cif/SKILL.md) | Author, inspect, and validate annotated CIF inputs and conditions. |
| [`rfd4-proteina-generate`](rfd4-proteina-generate/SKILL.md) | Generate designs with task-specific settings and metrics. |
| [`rfd4-proteina-search`](rfd4-proteina-search/SKILL.md) | Run reward-guided search with the selected oracle or structural reward. |
| [`rfd4-proteina-evaluate`](rfd4-proteina-evaluate/SKILL.md) | Compute and aggregate design quality, refolding, and diversity metrics. |
| [`rfd4-proteina-autoresearch`](rfd4-proteina-autoresearch/SKILL.md) | Plan exploration waves, refine rewards, and promote promising branches. |
| [`rfd4-proteina-commitment-curves`](rfd4-proteina-commitment-curves/SKILL.md) | Use partial diffusion to measure when design properties become committed. |
| [`rfd4-proteina-campaign`](rfd4-proteina-campaign/SKILL.md) | Track an end-to-end campaign, artifacts, measured criteria, and recovery in a SQLite ledger. |
| [`rfd4-proteina-package`](rfd4-proteina-package/SKILL.md) | Deliver selected designs, aligned refolds, metrics, and filtering results in a TAR. |

Start with **setup → annotated-cif → generate → optional search → evaluate**.
Use **campaign** to coordinate the program, **autoresearch** and
**commitment-curves** for exploration, and **package** for delivery.

The bundles and regression tests were imported from `bionemo/rfd4-skill`,
branch `omosafi/skills-rosetta`, commit
`c18cff052273bb3dec30ae51e4f3a5793cfe0788`. The source author is
Ohad Mosafi (`omosafi@nvidia.com`). Instructions, helpers, skill cards, and
evaluation datasets retain their source content with helper and test paths
adapted to the toolkit layout. These bundles are unsigned; no benchmark or
signing artifacts have been generated for this import. Skill text and
documentation retain CC-BY-4.0, and source helpers retain BSD-3-Clause as
declared upstream. Each skill's frontmatter and card record its license.

The canonical copies are `open-models-skills/rfd4-proteina/rfd4-proteina-*/` (the nine names above).
The generated plugin copies are under `skills/bionemo-agent-toolkit/skills/`.
After editing a canonical bundle or adding a catalog entry, run
`python scripts/plugin_sync.py --write`, then `python scripts/plugin_sync.py --check`.
When running model commands from `RFPROTEINA_ROOT`, resolve helper paths to
their absolute installed skill locations first.

Install one skill through the toolkit catalog:

```bash
npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit --skill rfd4-proteina-setup
```

From the toolkit root in a separate Python 3.12 test environment, run the
offline regressions:

```bash
python -m pip install -r tests/requirements-rfd4-rosetta.txt
python -B -m pytest -q -p no:cacheprovider \
    tests/test_rosetta_helpers.py tests/test_campaign_workflows.py \
    tests/test_setup_preflight.py
```

These tests cover configuration generation, analysis helpers, campaign
provenance, packaging, and preflight behavior with temporary data and test
doubles. Actual annotated-CIF and packaging commands use AtomWorks and
RFProteina from the model environment; the test dependencies do not install
that runtime.

The bundled `evals/evals.json` files describe live agent tasks. Their `setup`
metadata does not provision input fixtures, GPUs, or model access. In
particular, [setup evaluation prerequisites](rfd4-proteina-setup/evals/EVAL.md)
must be provisioned for both the with-skill and baseline trials, including
`RFPROTEINA_ROOT` at the sandbox's model path. Offline tests do not substitute
for that live evaluation.

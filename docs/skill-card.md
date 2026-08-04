# Skill Card — NVIDIA BioNeMo Agent Toolkit

<sub>Covers all 31 skills in this repository at tag `v0.1.0`.
Internal NVIDIA product-security and product-lifecycle review records for this
card are tracked separately and are not referenced here.</sub>

## Description: <br>
The NVIDIA BioNeMo Agent Toolkit gives coding and scientific agents 31 life-science skills that select, configure, invoke, and interpret NVIDIA BioNeMo NIM microservices, CUDA-X libraries, and open models across protein structure prediction, molecular docking, generative chemistry, accelerated genomics, and de novo protein binder design. <br>

This skill is ready for commercial or non-commercial use. <br>

## Owner: [NVIDIA] <br>

## Third-Party Community Consideration <br>
Not applicable — this toolkit is owned and developed by NVIDIA (NVIDIA-BioNeMo GitHub organization). <br>

Skills are aggregated from public NVIDIA-owned source repositories declared in
`components.d/*.yml` by a reviewed nightly sync; no third-party-owned skill is
vendored into the catalog. The skills do reference third-party open-source tools
and public data sources at runtime (see Known Risks and Mitigations). <br>

### License/Terms of Use: <br>
Dual-licensed `Apache-2.0 OR CC-BY-4.0` — source code (scripts, tooling) under
Apache-2.0; skills, documentation, and content files (`SKILL.md`, workflow
definitions, README files) additionally available under CC-BY-4.0. See
[`LICENSE`](../LICENSE), [`LICENSE-APACHE-2.0`](../LICENSE-APACHE-2.0),
[`LICENSE-CC-BY-4.0`](../LICENSE-CC-BY-4.0), and [`NOTICE`](../NOTICE). <br>

Contributions require DCO sign-off (`git commit -s`); see [`CONTRIBUTING.md`](../CONTRIBUTING.md). <br>

Released under OSRB approval for the NVIDIA-BioNeMo organization. Third-party OSS
dependencies of the shipped Python helper scripts are declared in
[`pyproject.toml`](../pyproject.toml) / [`uv.lock`](../uv.lock) for nSpect / Black Duck scanning. <br>

## Use Case: <br>
**Developers (Coding Agents)** and **External (Open Sourced Agents)**. <br>

Computational biologists, cheminformaticians, bioinformaticians, and ML engineers
who drive an agent through life-science work: predicting biomolecular structure
and binding affinity, docking small molecules, generating and optimizing candidate
molecules, scoring genomic variants, running accelerated secondary genomic
analysis, and designing de novo protein binders. The skills carry the domain
knowledge — endpoint contracts, input preparation, parameter selection, output
interpretation — that a general-purpose agent lacks, so a user can express intent
in scientific terms rather than API terms. <br>

Not intended for clinical decision-making, diagnosis, treatment selection, or any
regulated medical use. <br>

### Compatible Agents/Recommended Deployment Environments: <br>
* [Claude Code] <br> -> Repo Verified — native plugin marketplace at [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json)
* [Codex] <br> -> Repo Verified — native plugin marketplace at [`.agents/plugins/marketplace.json`](../.agents/plugins/marketplace.json)
* [Any agent supporting the portable `SKILL.md` skill format] <br> -> Installable via the [`skills` CLI](https://github.com/vercel-labs/skills) (`npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit`) and discoverable directly from the repo by partner harnesses. Not individually verified.

Deployment environment: the user's own developer workstation, notebook, or
cluster login node. Skills execute as agent-invoked shell commands and HTTP
requests in the user's environment; the toolkit itself hosts nothing. <br>

### Requirements/Dependencies: <br>
* [Agent harness supporting the `SKILL.md` format] <br> -> Repo Verified <br>
* [`NGC_API_KEY` or `NVIDIA_API_KEY` — for hosted NIM endpoints on `health.api.nvidia.com` / `build.nvidia.com`] <br> -> Repo Verified <br>
* [Python >= 3.10 with `gemmi`, `numpy`, `pyyaml` — for the binder-design helper scripts] <br> -> Repo Verified (`pyproject.toml` + `uv.lock`) <br>
* [Docker + NVIDIA Container Toolkit — for self-hosted NIMs, Parabricks, and the KERMT container skills] <br> -> Repo Verified <br>
* [NVIDIA GPU — for Parabricks, nvMolKit, cuEquivariance, KERMT, and Proteina-Complexa; not needed for hosted-NIM paths] <br> -> Repo Verified <br>
* [External model/tool repositories cloned by the user — Proteina-Complexa, KERMT, ColabDesign/AF2, RF3, ESMFold, Foldseek, MMseqs2, HBPLUS] <br> -> Repo Verified <br>
* [Optional: `WANDB_API_KEY` for KERMT training run tracking] <br> -> Repo Verified <br>

No credentials are stored in the repository. `.env` is git-ignored and secrets are
read from the environment at call time. <br>

### Release Management: <br>
Distributed as a public open-source repository; skills are installed by the user
into their own agent, not hosted or served by NVIDIA. <br>

Github 06/23/2026 via https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit (tag `v0.1.0`) <br>
Other 06/23/2026 via `npx skills add NVIDIA-BioNeMo/bionemo-agent-toolkit` (skills.sh CLI) <br>
Other 06/23/2026 via native Claude Code and Codex plugin marketplaces vendored in-repo <br>

Build.Nvidia.com — not published <br>
Hugging Face — not published <br>
NGC — not published (the NIMs the skills call are on NGC/build.nvidia.com and are released separately) <br>

### Deployment Geography for Use: <br>
Global: Asia-Pacific (APAC); Europe, Middle East, and Africa (EMEA); Latin America
(LATAM); North America (NAM) — subject to the export-classification determination
recorded on the PLC ticket. <br>

## Known Technical Limitations: <br>
* **Context budget.** Individual `SKILL.md` files run ~2,000–9,000 tokens; the largest workflow skills (`complexa-binder-design`, `protein-binder-design`) exceed that again in their `references/` files. Loading many skills at once measurably consumes an agent's context window and can crowd out task content.
* **Trigger accuracy.** Skill selection is description-matching, not classification. Adjacent skills overlap (`openfold2-nim` vs `openfold3-nim` vs `boltz2-nim` all "predict structure"; `complexa-binder-design` vs `protein-binder-design` are two routes to the same goal), and an agent can pick the wrong route or activate on tangentially related optimization queries. Trigger evals (220 cases across 12 skills) exist specifically to bound this; the other 19 skills have no trigger-eval coverage.
* **Harness truncation.** Several harnesses truncate skill descriptions to ~60 characters, so disambiguation depends on the opening clause alone (`SRC-6` in `CONTRIBUTING.md`).
* **No MCP tooling.** Skills drive `curl`/CLI/Docker through the agent's shell. An agent without shell execution — or sandboxed without network or Docker — can read the instructions but cannot run the tools.
* **Environment-dependent execution.** GPU skills (Parabricks, nvMolKit, cuEquivariance, KERMT, Proteina-Complexa) require the user to have provisioned CUDA hardware, drivers, container runtime, model checkpoints, and reference data. The skills instruct and verify; they do not provision. Setup preconditions are the most common failure point.
* **Upstream drift.** 24 of 31 skills are vendored from separate source repositories by a nightly sync. Between sync runs the catalog copy can lag its upstream, and NIM API contracts can change under a pinned skill description.
* **Scientific accuracy is bounded by the underlying models.** The skills add no predictive capability; structure-prediction confidence, docking poses, affinity estimates, generated molecules, and designed binders inherit all accuracy limits of the underlying models. Outputs are computational hypotheses requiring wet-lab validation.
* **Aggregate results not published.** Per-skill eval definitions are committed; eval run results are git-ignored (`**/evals/results/`) and no aggregate `BENCHMARK.md` is published yet (`SRC-10`).

## Known Risks and Mitigations: <br>
* **Prompt susceptibility / indirect injection.** Skills instruct agents to fetch and reason over external content — UniProt and RCSB PDB records, PDB/mmCIF files, and (in `complexa-binder-design`) literature-mined hotspot text. Hostile or malformed content in those inputs is untrusted data reaching an agent that also has shell access. *Mitigation:* skills scope commands narrowly and use structured parsers (`gemmi`) rather than free-form interpretation; SkillSpector runs offline on every PR (see Testing Completed); users should keep the agent's shell approval gates on. *Residual risk accepted for R&D use.*
* **Third-party install path.** `complexa-binder-design`'s optional hotspot fallback documents installing and authenticating against a third-party literature-mining CLI that is not distributed by NVIDIA. Installing it executes a vendor-supplied install script and creates a third-party account session. *Mitigation:* the path is an optional fallback and is not on any default route; users who do not need literature-mined hotspots never invoke it. Users electing to use it should review the vendor's install script and terms before running it, and treat the resulting tool as third-party software under their own organization's software-acquisition policy.
* **Dependency risk.** The repo's own Python surface is small (`gemmi`, `numpy`, `pyyaml`, locked in `uv.lock`), but skills direct users to clone and `pip install -e .` external research repositories (Proteina-Complexa, KERMT, ColabDesign, RF3) whose transitive dependency trees are outside this repo's scan boundary. *Mitigation:* those repos carry their own nSpect entries; this card scopes to the toolkit.
* **File and network access.** Skills read and write in the user's working directory (structures, checkpoints, sweep outputs, training artifacts) and make outbound calls to `*.nvidia.com`, `uniprot.org`, and `files.rcsb.org`. A misdirected path in a sweep or training skill can overwrite user data. *Mitigation:* skills write under explicit output directories; destructive operations are not scripted.
* **Cost.** Hosted NIM calls, and especially the sweep (`complexa-sweep`) and pretraining (`kermt-pretrain-scratch`, `kermt-continue-pretrain`) skills, can consume substantial API credits or GPU-hours from a single agent instruction. *Mitigation:* long runs launch detached with an explicit monitoring skill (`kermt-monitor`) so the user retains visibility and can terminate.
* **Credential handling.** Skills read `NGC_API_KEY` / `NVIDIA_API_KEY` / `WANDB_API_KEY` from the environment and may echo command lines into agent transcripts. *Mitigation:* keys are referenced by variable name, never inlined; `.env` is git-ignored; no credentials are committed. *Users should treat agent transcripts as sensitive.*
* **Misapplication to regulated use.** Life-science outputs could be mistaken for clinical guidance. *Mitigation:* R&D-only designation stated above; no skill accepts patient data or produces clinical output.
* **Unsigned skills.** `skill.oms.sig` OpenSSF model signatures (`SRC-11`) are not yet attached, so an installed skill's integrity cannot currently be verified offline. *Mitigation:* `nvskills-ci` signing is wired (`.github/workflows/request-nvskills-ci.yml`); signing is the tracked remediation.

## Reference(s): <br>
* Repository — https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit
* BioNeMo documentation — https://docs.nvidia.com/bionemo-framework/
* NVIDIA BioNeMo NIMs (Boltz-2, DiffDock, Evo 2, GenMol, MolMIM, MSA-Search, OpenFold2, OpenFold3, ProteinMPNN, RFdiffusion) — https://build.nvidia.com — model cards for each underlying model are published with the respective NIM
* NVIDIA Parabricks — https://docs.nvidia.com/clara/parabricks/latest
* nvMolKit — https://github.com/NVIDIA-Digital-Bio/nvmolkit
* cuEquivariance — https://docs.nvidia.com/cuda/cuequivariance/
* Proteina-Complexa — built on La-Proteina; see the component source repo declared in `components.d/proteina-complexa.yml`
* KERMT — multi-task GROVER extension with cuik-molmaker data loading; see `components.d/kermt.yml`
* SkillSpector — https://github.com/NVIDIA/skillspector
* `SKILL.md` skill format / installer — https://github.com/vercel-labs/skills

## Skill Output: <br>
**Output Type(s):** [Analysis, Application Programming Interface (API) Calls, Code, Files] <br>
**Output Format:** [String — agent-authored natural-language analysis; plus generated files: mmCIF/PDB structures, SMILES/CSV molecule tables, `.npy` embeddings, FASTA/A3M alignments, BAM/VCF genomic outputs, JSON/YAML run manifests and metrics] <br>
**Output Parameters:** [1D for scalar metrics (confidence, pLDDT, ipTM, predicted affinity, docking score); 2D for tabular molecule/variant/metric sets; 3D for atomic coordinates] <br>
**Other Properties Related to Output:** Outputs are computational predictions, not measurements. Confidence scores are model-reported and are not calibrated probabilities of experimental success. Generative skills are stochastic — repeated invocations with identical inputs produce different molecules or backbones unless a seed is fixed. All outputs require experimental validation before any downstream decision. <br>

## Fail Operation: <br>
* [Human-In-the-Loop] — every skill executes through the agent harness's own command-approval gate; no skill runs unattended by design. Long-running training and sweep skills launch detached with a dedicated monitoring skill (`kermt-monitor`) so the user can inspect and terminate. <br>
* [Shut-Down] — the user terminates the agent session or the underlying container/job; the toolkit holds no persistent state or background service. <br>

## Evaluation Agent(s): <br>
NVIDIA ACES (`nv-aces`) evaluation harness, `aces_default` grading mode, driving
a coding agent end-to-end per task (`evals/config.yml`, `harbor.task_source: evals_json`). <br>

## Evaluation Task(s): <br>
Purpose-built, non-public eval suites authored per skill and committed alongside
it — 31 of 31 skills covered: <br>

* **Functional task evals — 103 cases** across all 31 skills (`evals/evals.json`). Each case is a realistic natural-language scientific request paired with an expected outcome and 4–8 machine-checkable assertions covering endpoint correctness, authentication handling, payload construction, actual execution (not merely code authoring), and artifact production. Example (`boltz2-nim`): predict insulin structure via the hosted API, asserting the `health.api.nvidia.com/v1/biology/mit/boltz2/predict` endpoint, `Bearer`/`NGC_API_KEY` auth header, `molecule_type: protein` payload, real response-derived confidence values, and a saved `.cif` artifact.
* **Trigger evals — 220 labeled queries** across 12 skills (`evals/trigger_evals.json`), each labeled `should_trigger: true|false`, measuring whether the skill activates on in-scope requests and stays silent on out-of-scope ones.
* **Static skill security scan** — every `SKILL.md` in the catalog, on every pull request.

## Evaluation Metric(s): <br>
* Assertion pass rate per functional eval case (ACES `aces_default` grading over the agent trajectory and final response). <br>
* End-to-end task success rate — did the agent actually execute the tool and report response-derived values, rather than only writing a script. <br>
* Trigger precision and recall against the `should_trigger` labels. <br>
* SkillSpector finding count and severity per skill. <br>

## Evaluation Result(s): <br>
Eval **definitions** are committed and reproducible; eval **run results** are
regenerated per run and git-ignored (`**/evals/results/`), so no aggregate scores
are published in-repo. A consolidated `BENCHMARK.md` report (`SRC-10`) is not yet
present and is tracked as an open compliance gap in
[`docs/sync-findings.md`](sync-findings.md). <br>

Skills were admitted to the catalog only after their evals passed in the reviewed
sync/merge gate. SkillSpector runs advisory (non-blocking) on every PR and on
pushes to `main`; findings are reviewed before merge. <br>

A consolidated `BENCHMARK.md` with per-skill assertion pass rates and trigger
precision/recall from a pinned run is planned. <br>

## Testing Completed: <br>
**[x] Product Security** — [SkillSpector](https://github.com/NVIDIA/skillspector) static scan of every skill on every pull request and push to `main`, run fully offline (`--no-llm`, deterministic, no API key). Currently advisory (`continue-on-error: true`), not merge-blocking. <br>
**[ ] Agent Red-Teaming** — not performed. Recommended given the indirect-prompt-injection surface noted above. <br>
**[ ] Network Security** — not performed. <br>

## Skill Version: <br>
`v0.1.0` (repository tag, 06/23/2026). <br>

Signing Identifier: **not yet assigned.** Per-skill `skill.oms.sig` OpenSSF model
signatures (`SRC-11`) are not attached. The `nvskills-ci` signing workflow is
wired in [`.github/workflows/request-nvskills-ci.yml`](../.github/workflows/request-nvskills-ci.yml)
and signature attachment is the tracked remediation. <br>

## Ethical Considerations:
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications.  When downloaded or used in accordance with our terms of service, developers should work with their internal team to ensure this skill meets requirements for the relevant industry and use case and addresses unforeseen product misuse. <br>

Additionally, for this toolkit: outputs are computational predictions in a
biological domain and must not be used for clinical decision-making, diagnosis,
or treatment selection. Generative protein-design and molecule-generation skills
should be used consistent with applicable biosecurity norms and export-control
obligations; users are responsible for screening designed sequences and compounds
before synthesis. <br>

(For Release on NVIDIA Platforms Only) <br>
Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/).
See also [`SECURITY.md`](../SECURITY.md) — report vulnerabilities to psirt@nvidia.com, not via GitHub. <br>

<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Source-repo requirements for the BioNeMo Agent Toolkit aggregator

This repo is an **aggregator**: it vendors skills from other GitHub repos (see
`components.d/*.yml`) into its grouped catalog via `.github/workflows/sync-skills.yml`.

These are the requirements a source repo must meet to be vendored **cleanly**.
The stance is **aggregator-first**: the aggregator's expectations are the
standard. Sources that don't yet comply still sync (the divergence shows up in
the sync PR), and we fix the source repo upstream over time. Each requirement
below is tagged with the current violators found in the first sync audit
(`docs/sync-findings.md`).

## Hard requirements — the sync misbehaves without them

- **SRC-1 · Public GitHub.** The source must be a public `github.com` repo; the
  aggregator's GitHub Actions clone anonymously. Internal GitLab / private repos
  cannot be sourced (they'd need a token in a public repo).
  _Violators: parabricks, genomics-workflow-acceleration (internal only → held native)._

- **SRC-2 · Skills under one declared subpath.** All skills live under a single,
  stable subpath declared as `path:` in `components.d` — ideally the canonical
  `skills/`. A repo may declare multiple, but a stable container is required.
  _Current sources use three different conventions: `agent/skills/` (KERMT),
  `.claude/skills/` (Proteina), `agent-skills/nvmolkit-usage/` (nvMolKit, points
  at a single skill dir, not a container)._

- **SRC-3 · A skill is a self-contained directory with `SKILL.md` at its root.**
  Not a lone `SKILL.md` embedded inside unrelated source code. The directory
  contains only skill assets (`SKILL.md`, `reference/`, `scripts/`, `assets/`,
  `evals/`).
  _Violator: cuEquivariance — `SKILL.md` lives inside the Python package dir
  `cuequivariance/cuequivariance/`; a dir-vendor would drag in the package.
  Held native until upstream exposes a real skill dir._

- **SRC-4 · No references outside the vendored subtree.** `SKILL.md` and assets
  must not point at paths that won't be vendored (no `../../../docs/...`, no
  repo-root files). Shared assets must live **inside** the skills subpath (e.g. a
  `_shared/` dir under the skills container — this pattern is supported).
  _Violator: Proteina `complexa-sweep/SKILL.md` references `../../../docs/SWEEP.md`
  (outside `.claude/skills/`) → broken link once vendored._

- **SRC-5 · Stable, current publishing branch.** The declared `ref:` must be the
  branch/tag where skills are actually published and current — not one that lags.
  _Violator: Proteina `dev` is missing `complexa-slurm`, which exists in the
  current catalog. Either `dev` lags or the skill was intentionally dropped._

## Format requirements — harness compatibility

- **SRC-6 · Valid `SKILL.md` frontmatter.** `name` + `description`; keep the first
  ~60 chars of `description` self-sufficient (some harnesses truncate when many
  skills are installed, and that prefix is all the router sees).

- **SRC-7 · Globally-unique, product-prefixed skill dir names.** The catalog is a
  flat skill namespace; prefix by product from day one (renames later are painful).

- **SRC-8 · No `AGENTS.md` / `CLAUDE.md` inside a skill dir.** These are
  auto-loaded instruction channels in some harnesses and activate without the
  skill being invoked.

- **SRC-9 · No stray non-skill files in the skills container.** A `README.md` or
  similar at the skills-container root is vendored as catalog noise; keep the
  container to skill dirs (+ an optional `_shared/`).
  _Violator: Proteina `.claude/skills/README.md`._

## Eval requirements — POLICY DECISION PENDING

- **SRC-10 · Co-located evals.** If evals are to ship as part of the released
  skill, each skill carries `evals/evals.json`. **Today NO public source carries
  evals** — decide between: **(a)** make co-located evals a source requirement, or
  **(b)** keep evals pulled separately by the internal eval pipeline (the current
  model; evals live in dedicated eval repos, not the skill).
  _Violators (if (a)): every skill in every current source._

## Future — NVCARPS (deferred)

- **SRC-11 · Signed + carded.** Each skill ships `skill.oms.sig` +
  `skill-card.md`, produced by onboarding the source repo to NVIDIA `nvskills-ci`.
  Not enforced in v1; the review PR is the current gate.

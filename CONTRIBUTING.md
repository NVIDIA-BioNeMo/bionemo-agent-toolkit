# Contributing to BioNeMo Agent Toolkit

Thank you for your interest in contributing to the BioNeMo Agent Toolkit. We welcome bug reports, feature requests, and pull requests from the community.

## How to Contribute

### Reporting Issues

- Search [existing issues](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/issues) before opening a new one.
- Include a clear description, steps to reproduce, and any relevant context.

### Submitting a Pull Request

1. Read the [README](README.md) to understand the repo structure and skill format.
2. Fork the repository and create your branch from `main`.
3. Make your changes, following the existing skill and file conventions.
4. Ensure your commits are signed off (see [Signing Your Work](#signing-your-work) below).
5. Open a pull request against `main` with a clear description of the change and its motivation.
6. Address any review feedback. A maintainer will merge once approved.

### Branch Naming

Use a short descriptive prefix followed by a slug:

```
feat/boltz2-multi-chain-support
fix/diffdock-nim-timeout
docs/improve-workflow-readme
```

## How the catalog is assembled (aggregation)

This repo is an **aggregator**. Most skills are authored in *other* GitHub repos
and **vendored** in by the nightly sync (`.github/workflows/sync-skills.yml`),
which reads `components.d/*.yml`, clones each source repo at its declared `ref`,
and `rsync`s the declared skill folders into this repo's grouped catalog dirs
(`nim-skills/`, `library-skills/`, `open-models-skills/`, `workflows/`), then
opens a PR a maintainer reviews.

A skill lives here in exactly one of two ways:

- **Sourced** — authored in another repo, declared in `components.d/<slug>.yml`.
  **That repo is the source of truth.** The sync overwrites the vendored copy
  every run (`rsync --delete`), so **do not edit a sourced skill dir in this
  repo** — the change reverts on the next sync. Fix it upstream.
- **Native** — authored directly here and listed in `catalog-exceptions.yml`
  (e.g. the NIM skills and the `workflows/` meta-skills).

Every skill directory must be claimed by **exactly one** registry
(`components.d` or `catalog-exceptions.yml`), or the orphan pruner
(`.github/scripts/prune-orphans.sh`) deletes it.

### Onboarding a source repo

Add `components.d/<slug>.yml`, meet the requirements below, and open a PR:

```yaml
name: My Product
repo: NVIDIA-BioNeMo/my-product      # owner/repo — PUBLIC GitHub
ref: main                            # branch the skills are published on
skills:
  - path: skills/my-skill            # dir in the source repo
    catalog_dir: library-skills/my-skill   # grouped dest (depth-1 under a group root)
```

### Source-repo requirements — what can be ingested

Tagged `SRC-*` (referenced in review and in `docs/sync-findings.md`). These are
the same conventions `NVIDIA/skills` uses, so a compliant repo is ingestible by
**both** this toolkit and `NVIDIA/skills` (verified against `rapidsai/cudf`,
`NVIDIA-NeMo/RL`, `NVIDIA/cuopt`, `nvidia-holoscan/holoscan-sdk`).

**Hard — the sync breaks or corrupts without these:**
- **SRC-1 · Public GitHub** repo (the sync clones anonymously; internal/private can't be sourced).
- **SRC-3 · A skill is a self-contained directory with `SKILL.md` at its root** — not a lone `SKILL.md` embedded in package code. Contains only skill assets (`SKILL.md`, `reference/`, `scripts/`, `assets/`, `evals/`).
- **SRC-4 · No references outside the vendored subtree** (no `../../../docs/...`); shared assets go in a `_shared/` dir under the skills subpath. Runtime refs to a repo the user clones (`$MY_REPO/...`) are fine.

**Structure — for a clean, discoverable catalog:**
- **SRC-2 · Skills under one stable subpath**, ideally `skills/`.
- **SRC-5 · `ref` is the current publishing branch** (not lagging).
- **SRC-6 · Valid `SKILL.md` frontmatter** (`name` + `description`; first ~60 chars self-sufficient — harnesses truncate).
- **SRC-7 · Globally-unique, product-prefixed skill dir names.**
- **SRC-8 · No `AGENTS.md` / `CLAUDE.md` inside a skill dir** (auto-loaded by some harnesses).
- **SRC-9 · No stray non-skill files** in the skills container.

**Compliance — enforced by `NVIDIA/skills`; deferred here (NVCARPS):**
- **SRC-10 · Co-located `evals/evals.json`** per skill + a `BENCHMARK.md` report.
  Eval definitions for a **sourced** skill must live under `evals/` **in the
  source component repo** — never authored into the catalog copy here. The sync
  overwrites vendored dirs (`rsync --delete`), so catalog-only evals are
  silently wiped on the next run. (This is exactly what happened to the KERMT
  evals — they had been added to the catalog and had to be moved upstream into
  `evals/` in the KERMT repo. See `docs/sync-findings.md`.)
- **SRC-11 · Signed + carded** — `skill.oms.sig` (OpenSSF model signature) + `skill-card.md`, via NVIDIA `nvskills-ci`.

> This toolkit is currently **tolerant**: it syncs skills that don't yet meet
> SRC-2/5/6/9/10/11 and records the gaps in `docs/sync-findings.md` for upstream
> fixing — the reviewed sync PR is the gate. `NVIDIA/skills` **enforces** the full
> set. Aim for full compliance so a skill is ready for both.

## Signing Your Work

All contributors must sign off on their commits. This certifies that the contribution is your original work, or that you have the right to submit it under the same license or a compatible one.

Any contribution containing unsigned commits will not be accepted.

To sign off, use the `--signoff` (or `-s`) flag when committing:

```bash
git commit -s -m "Add cool feature."
```

This appends the following line to your commit message:

```
Signed-off-by: Your Name <your@email.com>
```

### Developer Certificate of Origin

By signing off your commits you agree to the following:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

Full text available at [https://developercertificate.org](https://developercertificate.org).

## License

By contributing, you agree that your contributions will be dual-licensed under the terms described in the [LICENSE](LICENSE) file (`Apache-2.0 OR CC-BY-4.0`).

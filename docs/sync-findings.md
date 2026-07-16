<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Sync findings — source compatibility problems

Problems found running the aggregator against each source, mapped to the
requirements in [`source-repo-requirements.md`](source-repo-requirements.md).
**Aggregator-first:** these are tracked to be fixed **upstream** later; the
aggregator syncs regardless and the divergence appears in the sync PR.

Audit date: 2026-07-16 (first dry-run sync, off `origin/main`).

## Sourced components (public GitHub)

### nvMolKit — `NVIDIA-BioNeMo/nvMolKit@main`, path `agent-skills/nvmolkit-usage`
- ✅ 1 clean, self-contained skill.
- ⚠️ **SRC-2**: `path` points directly at a single skill dir, not a `skills/`
  container. Works, but non-standard; prefer `skills/nvmolkit-usage/` upstream.
- ⚠️ **SRC-10**: no `evals/`.
- Content differs from the current catalog copy (+46/-77) — expected divergence.

### KERMT — `NVIDIA-BioNeMo/KERMT@main`, path `agent/skills`
- ✅ 8 clean, self-contained skill dirs; **no** stray non-skill siblings under
  `agent/skills/`. (The −10.3k-line diff vs the catalog is because the *current*
  catalog over-vendored the whole `agent/` tree — `config/`, `tests/`,
  `scripts/`. The corrected `agent/skills` path drops that cruft. Desirable.)
- ⚠️ **SRC-2**: skills under `agent/skills/`, not canonical `skills/`.
- ⚠️ **SRC-10**: none of the 8 skills carry `evals/`.

### Proteina-Complexa — `NVIDIA-BioNeMo/Proteina-Complexa@dev`, path `.claude/skills`
- ✅ 5 skills; uses a supported `_shared/` dir for cross-skill assets.
- 🔴 **SRC-5**: `complexa-slurm` (a skill in the current catalog) is **absent** on
  `dev`. Syncing deletes it. Confirm whether `dev` lags or the skill was dropped.
- 🔴 **SRC-4**: `complexa-sweep/SKILL.md` references `../../../docs/SWEEP.md`
  (outside `.claude/skills/`) → broken link once vendored.
- ⚠️ **SRC-9**: stray `.claude/skills/README.md` vendored as noise.
- ⚠️ **SRC-2**: skills under `.claude/skills/`, not canonical `skills/`.
- ⚠️ **SRC-10**: no `evals/` on any of the 5 skills.

## Held native (not sourced) — reasons

### cuEquivariance — `NVIDIA/cuEquivariance`
- 🔴 **SRC-3**: `SKILL.md` is embedded in the Python package dir
  `cuequivariance/cuequivariance/` with no clean skill folder. Cannot be
  dir-vendored without dragging in the package. **Ask upstream to expose a
  `skills/cuequivariance/` dir**, then move to `components.d`.

### parabricks, genomics-workflow-acceleration
- 🔴 **SRC-1**: only exist on internal GitLab (`apizarro/genomics-acceleration-skill`).
  Need a public GitHub home before they can be sourced.

## Systemic themes (fix once, upstream)
1. **Evals absent everywhere (SRC-10)** — resolve the policy: co-located in the
   skill (source requirement) vs pulled separately by the eval pipeline.
2. **Subpath inconsistency (SRC-2)** — three conventions across three repos;
   standardize on `skills/`.
3. **Self-containment (SRC-3/4)** — cuEquivariance embedding + Proteina's
   out-of-tree doc reference are the two concrete break cases.

## Suggested next step
Add a lightweight **source linter** to the sync workflow that checks each
vendored skill against SRC-2…SRC-9 and lists violations in the PR body (warn,
don't drop) — so every future sync auto-highlights new problems instead of a
manual audit.

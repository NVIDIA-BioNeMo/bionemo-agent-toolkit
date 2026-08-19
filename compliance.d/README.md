<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# `compliance.d/` — compliance artifacts for sourced skills

Skills vendored from a source repo are rsynced with `--delete` (see
[`../.github/workflows/sync-skills.yml`](../.github/workflows/sync-skills.yml)),
so **a file committed directly into a sourced catalog dir is deleted on the next
nightly sync.** That is what happened to the KERMT evals (see
[`../docs/sync-findings.md`](../docs/sync-findings.md)).

This directory holds `skill-card.md` files for sourced skills, mirroring the
catalog path, outside every rsync target and every prune root:

```
compliance.d/<catalog_dir>/<skill>/skill-card.md
   ↓ backfilled after the rsync, only if absent
<catalog_dir>/<skill>/skill-card.md
```

## Upstream always wins

The **Backfill compliance artifacts** step in the sync workflow copies a card
into the catalog *only when the rsync left no card there*. As soon as a source
repo ships its own `skill-card.md`, that card lands via rsync and the backfill
becomes a no-op for that skill — no flag to flip, no coordination needed.

The sync PR body reports both states:

- **backfilled** — upstream still owes a card; this is the outstanding debt list
- **retirable** — upstream now ships its own card, so the `compliance.d` entry
  here is dead weight and should be deleted in that PR

## What does *not* belong here

**`skill.oms.sig`.** A signature is a cryptographic attestation over specific
bytes. Copying one over content it was not generated from produces an artifact
that fails verification — and `NVIDIA/skills`' sync detects exactly this case
and reverts the skill. Signing stays a per-source-repo task, performed by
commenting `/nvskills-ci` on a PR in the repo that owns the skill.

**Evals.** Eval definitions must be co-located with the skill in its source repo
(`SRC-10`), for the same `--delete` reason.

## Current entries

| Catalog path | Source repo | Upstream card PR |
|---|---|---|
| `open-models-skills/kermt/*` (8) | `NVIDIA-BioNeMo/KERMT` | [KERMT#26](https://github.com/NVIDIA-BioNeMo/KERMT/pull/26) |
| `open-models-skills/proteina-complexa/*` (5) | `NVIDIA-BioNeMo/Proteina-Complexa` | [Proteina-Complexa#60](https://github.com/NVIDIA-BioNeMo/Proteina-Complexa/pull/60) |
| `library-skills/nvMolKit` (1) | `NVIDIA-BioNeMo/nvMolKit` | [nvMolKit#248](https://github.com/NVIDIA-BioNeMo/nvMolKit/pull/248) |

The same card content was opened as a PR against each source repo. When those
merge, the corresponding entries here become retirable.

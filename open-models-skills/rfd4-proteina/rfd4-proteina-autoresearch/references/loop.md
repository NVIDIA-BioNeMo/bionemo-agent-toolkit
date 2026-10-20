# The autoresearch loop (waves, branches, inspectability)

Adapted from muni's autoresearch experiments
([scoring-function-dependent strategies](https://muni.bio/research/scoring-function-dependent-strategies),
[autoresearch + CLI](https://www.muni.bio/research/muni-makeover-cli-autoresearch)),
which build on Karpathy's autoresearch framing. The mechanism transfers to
RFD4-Proteína; the reported results there are Proteina-Complexa on TREM2 and are used
here only as illustrations.

## Vocabulary

- **Wave (round)** — one iteration: run this wave's branches, score, then update.
- **Branch** — one (input, search-config) combination carried across waves; it can
  be promoted (spawns a child) or frozen (retired).
- **Branch health** — the median of that branch's **top-3** design scores. A robust
  summary that resists single lucky outliers.

## The per-wave rules

After scoring a wave:

1. **Freeze** any branch whose health is in the **bottom quartile** among branches
   with >=3 scored designs. Stop funding it.
2. **Promote** any branch that produced a design in the current **global top-k**.
   A promoted branch spawns **one child** that mutates **exactly one** parameter
   (see `sweep-axes.md`) so the effect is attributable.
3. **Allocate** the next wave's job budget roughly **70% exploit** (promoted +
   top-half-by-health branches) and **30% explore** (unexplored parameter
   combinations).

These thresholds (quartile, top-k, 70/30) are starting points — tune them to your
budget and how rugged the landscape looks.

## What good trajectories look like (illustrative)

muni's four reward functions produced four *different* behaviors on the same
target: one climbed steadily by refining a single surface; one anchored on an early
optimum and spent later waves testing (mostly failing) nearby variants; one shifted
to a new surface family; one stayed on the same surface but changed strategy within
it. The lesson for RFD4-Proteína campaigns: **expect the reward to shape the search
path**, and read the losing branches — a branch that never beats the incumbent
still tells you what the reward does and does not value.

## Inspectability — keep the loop on disk

Record enough that any wave is replayable and any decision is auditable. A simple
layout that mirrors the muni loop:

| File | Contents |
| --- | --- |
| `campaign/program.md` | Objective, reward definition, and the freeze/promote/allocate rules |
| `campaign/seed_branches.json`, `campaign/wave{N}.json` | Per-branch payloads (input + search config) for each wave |
| `campaign/decisions.md` | Why each branch was promoted / frozen / spawned (the reasoning, not just the outcome) |
| `campaign/results.tsv` | Per-design / per-branch scores and metadata |

Alongside these sit the underlying artifacts the other skills already produce:
per-branch design CIFs (from generate/search) and metrics CSVs (from evaluate).

Within `rfd4-proteina-campaign`, register each branch and ingest every materialized
design, oracle prediction, and metric into `campaign.sqlite`. The table above
remains a readable experiment log; `results.tsv` is an export rather than the
authoritative provenance record.

**Failed branches are signal.** Capture *why* a path was wrong — that is what makes
the next wave smarter, and what a human reviewer learns from. A final score says
which branch won; the trajectory says how, and why the rest did not.

## Stop conditions

Stop when the running best plateaus across several waves, or the compute budget is
spent. Record whether the search space was actually exhausted — "we stopped at wave
N with budget X" is itself a result, and "exhaust the space to see if strategy
changes recover gains" is the natural continuation.

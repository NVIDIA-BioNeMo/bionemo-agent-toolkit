# Metrics reference (compact)

Distilled from [docs/workflow/metrics.md](upstream-sources.md) and
[docs/workflow/custom-metrics.md](upstream-sources.md) — read
those for the full column lists, per-metric thresholds, and worked examples.

## What ships enabled

**46 metric / pass-criterion / filter entries** are registered in
`configs/metrics/all_metrics.yaml` and run automatically; most are gated behind
one or more `metrics_tags`, so turning one on is just passing a tag.

| Category | Count | Config |
| --- | --- | --- |
| Design metrics (inline, pre-refolding) | 19 | `configs/metrics/inline_metrics/design_metrics.yaml` + `developability_metrics.yaml` |
| Structure-prediction metrics | 1 | `configs/metrics/inline_metrics/structure_prediction_metrics.yaml` |
| Refolding metrics (design vs. refolded) | 7 | `configs/metrics/refolding_metrics/all_refolding_metrics.yaml` |
| Refolding oracles (AF3 variants) | 4 | `configs/metrics/refolding_oracles/af3.yaml` |
| Pass criteria (pass/fail thresholds) | 10 | `configs/metrics/pass_criteria/all_pass_criteria.yaml` |
| Pre-oracle filters (skip the oracle on cheap failures) | 5 | `configs/metrics/pre_oracle_filters/all_pre_oracle_filters.yaml` |

Additional metric classes exist in the codebase but are opt-in
(not wired into any default config) — TMol interface ddG / H-bonds /
electrostatics (`TMolBlockPairMetric`), atom-pair distance constraint
(`AtomPairDistanceMetric`, catalytic geometry), QM ligand interaction energy
(`QMInteractionEnergyIPA`), charge complementarity
(`ChargeComplementarityMetric`), and a few others. Turning one on needs only a
few lines of YAML, no Python.

## Tag semantics

Each metric entry may declare gate fields; they are matched against the
`metrics_tags` list you pass on the CLI (matched by set intersection — free-form
strings, no fixed enum):

- `required_tags_any: [a, b]` — runs if `metrics_tags` contains **at least one**.
- `required_tags_all: [a, b]` — runs only if `metrics_tags` contains **all**.
- `prohibited_tags: [c]` — skipped if `metrics_tags` contains `c`, even when the
  required tags match.
- **No tags at all = always runs.**

**Design tags and refolding tags are separate, unrelated namespaces** — no
implication between them. To run both families pass both:
`metrics_tags='[design, unconditional_refolding]'`.

## Common tags

| Tag | Activates | Needs AF3 container? |
| --- | --- | --- |
| `design` | Raw-structure design metrics (clash, bond length, SSE) | No |
| `developability` | GRAVY / instability index + Rosetta SAP / ExposedHydrophobics (+ pass criterion) | No (PyRosetta SIF for Rosetta metrics) |
| `unconditional_refolding` | AF3 refold + scRMSD/pLDDT for unconditional generation | Yes |
| `ppi_refolding` | AF3 refold + target templating + interface metrics (protein binders) | Yes |
| `motif_scaffold_refolding` | AF3 refold + motif RMSD (motif scaffolding / enzymes) | Yes |
| `sm_binder_refolding` | AF3 refold + binding metrics (small-molecule binders) | Yes |
| `ame_refolding` | AF3 refold for enzyme (MCSA) active-site benchmarks | Yes |
| `disco_refolding` | AF3 refold + ligand-centroid displacement | Yes |
| `hotspot_conditioning` | Hotspot-obedience metric (needs hotspot input) | No |
| `3d_coordinate_conditioning` | Motif coordinate RMSD metrics | No |
| `rasa_conditioning` | RASA buried/exposed adherence metrics | No |
| `interchain_interactions` | Interchain interaction adherence + counts | No |
| `small_molecule_only` | PoseBusters + chirality; suppresses polymer design metrics | No |
| `structure_prediction` | All-atom lDDT vs. ground truth (validation runs) | No |

## Refolding / oracle container requirement

Refolding metrics (`refolded_backbone_rmsd`, `refolded_target_aligned_binder_rmsd`,
`refolded_motif_allatom_rmsd`, `refolded_motif_ca_rmsd`,
`refolded_backbone_aligned_ligand_rmsd`, `max_ligand_centroid_distance`) and the
refolding oracles (`oracle`, `oracle_ppi`, `oracle_dna`) run the AF3 predictor,
which runs **only inside an apptainer/docker container** configured via the
cluster env files. Without the container these metrics silently do not run (no
oracle columns, no error). Plain design metrics need no container. See
[RFD4-Proteína installation guide](upstream-sources.md).

Oracle key outputs (prefixed `<oracle_key>.`): `overall_plddt`, `overall_ptm`,
`overall_iptm`, `plddt_coi`, `ptm_coi`, `pae_coi`, `ipae_coi`, `min_ipae_coi`,
`iptm_coi`, `frac_under_1`/`1.5`/`2`. Pass criteria threshold these into a
`{key}.pass` flag (e.g. `unconditional`: `refolded_backbone_rmsd.rmsd` ≤ 1.5).

## FoldSeek diversity clustering

`aggregate_metrics --cluster_with_foldseek` adds a `foldseek_cluster_id` column
by clustering the **designed chain** (`chain_of_interest`) at TM-score 0.5.
Requires `FOLDSEEK_EXEC` in the active environment. Post-hoc evaluation writes
its designed-chain CIFs; generation-time aggregation requires
`save_chain_of_interest=true`.

## Custom metrics

Add Python classes under `src/rfproteina/metrics/custom_metrics/` and register
them in `configs/metrics/custom_metrics/all_custom_metrics.yaml` (both
git-ignored; `# @package metrics`). Picked up automatically; columns are prefixed
by the config key. Three categories — design (`inline_metrics`), refolding
(`refolding_metrics`), and pass criteria (`pass_criteria`, via the built-in
`PassCriterionMetric`, no Python). Full walkthrough:
[docs/workflow/custom-metrics.md](upstream-sources.md).

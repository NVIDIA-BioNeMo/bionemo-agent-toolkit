#!/usr/bin/env python
"""Write the phase-1 and phase-2 configs for a commitment-curve study from one spec.

A commitment curve needs three configs that have to agree: a phase-1 ``inference_experiment`` that
makes the parents, a phase-2 one that partially re-diffuses them, and a sweep config holding the
restart-step grid. The two experiments must declare the *same* metric set and tags, or parents and
children are scored by different code and the correlation is meaningless. Generating all three from
one spec is what keeps them in step; edit the results freely afterwards for cluster specifics.

Spec (YAML)::

    name: my_commitment
    inputs: /path/to/design_inputs        # directory of design-problem CIFs
    parents_dir: /path/to/parents         # flat directory of phase-1 designs, built in step 4
    out_root: /path/to/runs

    metrics_group: tcr_design             # a configs/metrics/<group>.yaml, or omit for all_metrics
    metrics_tags: [design, tcr_design]    # what actually switches metrics on

    phase1:
      num_replicates: 4                   # replicates belong HERE, not in phase 2
      batch_size: 4
      existing_designs: null              # a directory -> skip generation, score it offline

    phase2:
      step: 5                             # grid every N of nsteps
      nsteps: 60
      batch_size: 4
      gen_njobs: 1

Examples:
  >>> python make_configs.py --spec my_study.yaml

Usage: python make_configs.py --spec study.yaml [--repo_root /path/to/model] [--dry_run]
Arguments: Study YAML, target model checkout, and optional preview mode.
Output: Phase-1, phase-2, and sweep YAML files, or a dry-run preview.
Exit codes: 0 for success, 1 for invalid spec/runtime failure, 2 for invalid CLI arguments.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import fire
import yaml

logger = logging.getLogger(__name__)

# Phase 2 uses one child per parent because Spearman precision follows the parent count.
# Additional children estimate within-parent spread rather than tightening the curve.
PHASE2_NUM_REPLICATES = 1


def _defaults_block(metrics_group: str | None) -> str:
    override = f"\n  - override /metrics: {metrics_group}" if metrics_group else ""
    return f"defaults:\n  - inference_on_user_inputs{override}\n  - _self_\n"


def _tags_block(spec: dict[str, Any]) -> str:
    tags = "\n".join(f"  - {t}" for t in spec.get("metrics_tags", []))
    return tags or "  []"


def phase1_config(spec: dict[str, Any]) -> str:
    """The run that produces the parents."""
    name, p1 = spec["name"], spec.get("phase1", {})
    return f"""# @package _global_
# Phase 1 creates the parent population; replicates increase the independent parent count.

{_defaults_block(spec.get("metrics_group"))}
inputs: {spec["inputs"]}

run_name_: {name}_phase1
out_dir: {spec["out_root"]}/{name}_phase1

num_replicates: {p1.get("num_replicates", 1)}
batch_size: {p1.get("batch_size", 4)}
seed: {p1.get("seed", 0)}

# Must match the phase-2 config exactly, or the correlation measures the difference in scoring too.
metrics_tags:
{_tags_block(spec)}
"""


def phase2_config(spec: dict[str, Any]) -> str:
    """The shared settings for every restart step; the grid lives in the sweep config."""
    name, p2 = spec["name"], spec.get("phase2", {})
    return f"""# @package _global_
# Phase 2 partially diffuses the parents; configs/sweeps/{name}.yaml supplies the restart grid.

{_defaults_block(spec.get("metrics_group"))}
# Parent links omit _generated and retain compression suffixes so `task` joins to phase 1.
inputs: {spec["parents_dir"]}

run_name_: {name}_sweep
batch_size: {p2.get("batch_size", 4)}
seed: {p2.get("seed", 0)}

# One child per parent, deliberately: Spearman precision follows the parent count, so add parents in
# phase 1 rather than children here.
num_replicates: {PHASE2_NUM_REPLICATES}

# Parallelism inside one restart step; with one replicate there is nothing to divide unless
# `gen_njobs` can divide the *examples*. Otherwise parallelism comes from the sweep points.
gen_njobs: {p2.get("gen_njobs", 1)}

# Parent CIFs already carry their conditions; do not add stochastic sampling transforms.

generation:
  args:
    nsteps: {p2.get("nsteps", 60)}

# Partial diffusion activates the fidelity metrics; retain inline design metrics in custom groups.

# Must match the phase-1 config exactly.
metrics_tags:
{_tags_block(spec)}
"""


def sweep_config(spec: dict[str, Any]) -> str:
    """The restart-step grid."""
    name, p2 = spec["name"], spec.get("phase2", {})
    nsteps, step = p2.get("nsteps", 60), p2.get("step", 5)
    fracs = [round(1 - k / nsteps, 4) for k in range(nsteps - step, -1, -step)]
    grid = "\n".join(f"    - {f}" for f in fracs)
    return f"""# {name}: one partial-diffusion run per restart step, followed by sweep-level aggregation.
# Restart step is (1 - fraction) * {nsteps}; this grid advances by {step} steps.

# The smallest fraction is the clean-end control; 1.0 is the between-problem floor.

base_config: inference

base_config_overrides:
  - inference_experiment={name}_sweep

run_name_prefix: {name}

sweep:
  generation.args.partial_trajectory_fraction_steps:
{grid}
"""


def main(spec: str, repo_root: str = ".", dry_run: bool = False) -> None:
    """Write the two experiment configs and the sweep config named by ``spec``.

    Args:
      spec: Path to the YAML spec described in this module's docstring.
      repo_root: Repository root; configs land under ``<repo_root>/configs/``.
      dry_run: Print the paths and the launch commands without writing anything.

    Raises:
      ValueError: If a required key is missing, or neither inputs nor existing designs are given.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    loaded = yaml.safe_load(Path(spec).read_text())
    for required in ("name", "out_root", "parents_dir"):
        if not loaded.get(required):
            raise ValueError(f"spec is missing required key {required!r}")

    existing = loaded.get("phase1", {}).get("existing_designs")
    if not loaded.get("inputs") and not existing:
        raise ValueError("spec needs either `inputs` (generate parents) or `phase1.existing_designs` (score them)")

    name, root = loaded["name"], Path(repo_root)
    targets: dict[Path, str] = {
        root / "configs" / "inference_experiment" / f"{name}_sweep.yaml": phase2_config(loaded),
        root / "configs" / "sweeps" / f"{name}.yaml": sweep_config(loaded),
    }
    if not existing:
        targets[root / "configs" / "inference_experiment" / f"{name}_phase1.yaml"] = phase1_config(loaded)

    for path, text in sorted(targets.items()):
        if dry_run:
            logger.info("would write %s", path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        logger.info("wrote %s", path)

    phase1_dir = f"{loaded['out_root']}/{name}_phase1"
    print("\nNext:")
    if existing:
        tags = ",".join(loaded.get("metrics_tags", []))
        print("  1. score the curated designs offline (they are the parents):")
        print(f"       rfd4-evaluate inputs={existing} \\")
        print(f"           metrics_tags='[{tags}]' out_dir={phase1_dir}")
        print("  2. the curated directory is already the parent directory -- point parents_dir at it")
        print(f"       (spec has parents_dir: {loaded['parents_dir']}, curated designs: {existing})")
    else:
        print(f"  1. ./scripts/launch_generate.sh inference_experiment={name}_phase1 --no-foldseek")
        print(f"  2. link parents from {phase1_dir!r} into {loaded['parents_dir']!r} (SKILL.md Step 5)")
    # Cheap, and it can call the sweep off: a criterion nothing passes is not a commitment question.
    print("  3. how rare is each metric in the parents, before buying the sweep:")
    print("       python .../metric_distributions.py \\")
    print(f"           --metrics_csv {phase1_dir}/per_example_metrics.csv \\")
    print(f"           --out_dir {phase1_dir}/analysis")
    print(f"  4. ./scripts/launch_sweep.sh --sweep-config configs/sweeps/{name}.yaml \\")
    print(f"           --base-out-dir {loaded['out_root']}/{name}_sweep --no-foldseek")
    print("  5. python .../commitment_curve.py --metrics '<Label=column,...>' \\")
    print(f"           --sweep_csv {loaded['out_root']}/{name}_sweep/sweep_per_example_metrics.csv \\")
    print(f"           --parent_csv <the {name}_phase1 per_example_metrics.csv> \\")
    print(f"           --nsteps {loaded.get('phase2', {}).get('nsteps', 60)} \\")
    print(f"           --out_dir {loaded['out_root']}/{name}_sweep/analysis")


if __name__ == "__main__":
    fire.Fire(main)

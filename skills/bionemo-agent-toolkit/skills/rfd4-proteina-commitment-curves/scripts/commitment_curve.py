#!/usr/bin/env python
"""Commitment curves: when along the trajectory does a metric stop being able to change?

Reads the sweep master table plus the phase-1 parent table, and for each metric and each
partial-diffusion restart step computes the Spearman correlation between the children's values and
their own parent's value. Writes a tidy CSV and a line plot, one line per metric.

Alongside it, and with no configuration, writes the *fidelity* curves: how much of the parent each
child literally kept, as sequence identity and CA RMSD to the parent structure. Those two are the
scale on which the correlations should be read -- they must reach 100% and 0 A at the clean end, and
they say whether a low rho means the model re-decided the property or merely rebuilt the protein.

The x axis: ``partial_trajectory_fraction_steps`` is the fraction of the trajectory re-run, so
restart step = ``(1 - frac) * nsteps``. Step 0 re-runs everything from noise; step ``nsteps`` is the
parent itself, where rho is 1.0 by construction. Rho does *not* fall to 0 at step 0 and need not
reach 1 at the clean end -- see references/method.md before reading a curve.

Examples:
  >>> SWEEP=/scratch/me/runs/my_commitment_sweep
  >>> python commitment_curve.py \\
  ...     --sweep_csv $SWEEP/sweep_per_example_metrics.csv \\
  ...     --parent_csv /scratch/me/runs/my_commitment_phase1/per_example_metrics.csv \\
  ...     --out_dir $SWEEP/analysis \\
  ...     --metrics 'Docking Z=tcr_docking_geometry.docking_z,min ipAE=min(oracle.a|oracle.b)'

Usage: python commitment_curve.py --sweep_csv sweep.csv --parent_csv parents.csv --out_dir analysis --metrics Score=score
Arguments: Sweep/parent CSVs, output directory, metric names; optional join keys and bootstrap settings.
Output: Correlation and available fidelity CSVs, plus light/dark PNG plots.
Exit codes: 0 for success, 1 for invalid data/runtime failure, 2 for invalid CLI arguments.
"""

# Preserve mathematical symbols used as chart labels.
# ruff: noqa: RUF001

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

import fire
import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

logger = logging.getLogger(__name__)

FRAC_COLUMN = "generation.args.partial_trajectory_fraction_steps"

# One line per metric. Past three the palette cannot stay CVD-safe when every pair is compared, so a
# fourth metric belongs in a second figure rather than a fourth hue.
MAX_SERIES = 3

# Row-wise reductions a metric expression may name, as ``reducer(colA|colB)``. Same three as
# PassCriterionMetric's min_of / max_of / mean_of, and each is a pandas DataFrame method.
COLUMN_REDUCERS = {"min": pd.DataFrame.min, "max": pd.DataFrame.max, "mean": pd.DataFrame.mean}

PALETTE = {  # validated with the dataviz skill's validate_palette.js, both modes
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a"],
        "surface": "#fcfcfb",
        "primary": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70"],
        "surface": "#1a1a19",
        "primary": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
    },
}


class FidelitySeries(NamedTuple):
    """One "how much of the parent survived" series, and the value it must reach at the clean end.

    These are absolute per-child quantities, not correlations, so they need no join to the parent
    table: phase 2 hands the parent CIF in as the input structure, and both metrics are scored
    against that input.
    """

    column: str
    label: str
    axis_label: str
    scale: float  # applied to the raw column before plotting, e.g. a [0, 1] fraction to a percent
    clean_end: float  # the definitional value at restart step == nsteps, i.e. a parent against itself
    clean_end_text: str  # how that value reads in the subtitle, with its unit
    y_max: float | None  # fixed axis top, or None to take it from the data


# Always computed, never configured. Both are emitted by the inline design metrics whenever the
# `partial_diffusion` tag is on, which generate.py adds automatically for any partial-diffusion run.
FIDELITY_SERIES = (
    FidelitySeries(
        column="sequence_similarity_to_input.sequence_identity_to_input",
        label="Sequence identity to parent",
        axis_label="sequence identity to parent (%)",
        scale=100.0,
        clean_end=100.0,
        clean_end_text="100%",
        y_max=100.0,
    ),
    FidelitySeries(
        column="ca_rmsd_to_input.rmsd",
        label="CA RMSD to parent",
        axis_label="CA RMSD to parent (Å)",
        scale=1.0,
        clean_end=0.0,
        clean_end_text="0 Å",
        y_max=None,
    ),
)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    """Coerce to float and treat non-finite as missing, so one inf cannot poison a correlation."""
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)


def parse_metrics(spec: str | tuple[str, ...]) -> list[tuple[str, str]]:
    """Parse the ``--metrics`` spec into ``(column, label)`` pairs.

    Each entry is ``Label=column``. A ``Label=min(colA|colB)`` entry reduces several columns to
    their row-wise minimum first, the same reduction ``PassCriterionMetric``'s ``min_of`` performs.
    ``max(...)`` and ``mean(...)`` are the other two.

    Examples:
      >>> parse_metrics("Docking Z=tcr_docking_geometry.docking_z")
      [('tcr_docking_geometry.docking_z', 'Docking Z')]
      >>> parse_metrics("min ipAE=min(oracle.ipae_B_C|oracle.ipae_B_D)")
      [('min(oracle.ipae_B_C|oracle.ipae_B_D)', 'min ipAE')]
    """
    entries = spec.split(",") if isinstance(spec, str) else list(spec)
    metrics = []
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"--metrics entry {entry!r} must be 'Label=column'")
        label, column = entry.split("=", 1)
        metrics.append((column.strip(), label.strip()))
    if len(metrics) > MAX_SERIES:
        raise ValueError(
            f"{len(metrics)} metrics requested but the palette is only CVD-safe to {MAX_SERIES}; "
            "split them across two runs of this script"
        )
    return metrics


def resolve_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a metric column, evaluating a ``min(a|b|c)`` reduction if that is what was asked for.

    The three reducers mirror ``PassCriterionMetric``'s ``min_of`` / ``max_of`` / ``mean_of``, so a
    threshold lifted straight out of a pass-criteria config resolves here unchanged.

    Raises:
      KeyError: If a named column is absent from the frame.
    """
    for reducer in COLUMN_REDUCERS:
        if column.startswith(f"{reducer}(") and column.endswith(")"):
            parts = [p.strip() for p in column[len(reducer) + 1 : -1].split("|")]
            missing = [p for p in parts if p not in frame.columns]
            if missing:
                raise KeyError(f"columns absent for {column}: {missing}")
            stacked = pd.concat([_numeric(frame, p) for p in parts], axis=1)
            return COLUMN_REDUCERS[reducer](stacked, axis=1)
    if column not in frame.columns:
        raise KeyError(column)
    return _numeric(frame, column)


def bootstrap_ci(
    statistic: Callable[[np.ndarray], float], groups: np.ndarray, n_boot: int, seed: int
) -> tuple[float, float]:
    """Percentile CI for a statistic of row indices, resampling whole parents rather than rows.

    Children of one parent are correlated, so the unit of resampling has to be the parent; drawing
    rows would understate the interval badly.

    Args:
      statistic: Maps the row indices of one resample to a scalar. May return ``nan`` for a
        degenerate resample, which is then dropped.
      groups: Parent identity per row, as integer codes.
      n_boot: Number of bootstrap resamples.
      seed: Seed for the resampling.

    Returns:
      The 2.5th and 97.5th percentiles of the resampled statistic, or ``(nan, nan)`` if there are too
      few parents to resample.
    """
    unique = np.unique(groups)
    if len(unique) < 3:
        return float("nan"), float("nan")
    by_parent = [np.flatnonzero(groups == g) for g in unique]
    rng = np.random.default_rng(seed)

    draws = []
    for _ in range(n_boot):
        picked = rng.integers(0, len(by_parent), size=len(by_parent))
        value = statistic(np.concatenate([by_parent[p] for p in picked]))
        if np.isfinite(value):
            draws.append(value)
    if not draws:
        return float("nan"), float("nan")
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def bootstrap_rho(
    child: np.ndarray, parent: np.ndarray, groups: np.ndarray, n_boot: int, seed: int
) -> tuple[float, float]:
    """Percentile CI for Spearman rho over parents.

    Args:
      child: Child metric values.
      parent: The matching parent value for each child.
      groups: Parent identity per child, as integer codes.
      n_boot: Number of bootstrap resamples.
      seed: Seed for the resampling.

    Returns:
      The 2.5th and 97.5th percentiles of the resampled rho.
    """

    def rho_of(idx: np.ndarray) -> float:
        a, b = child[idx], parent[idx]
        # A resample can be degenerate (every draw the same parent); nan drops it from the interval.
        if len(np.unique(a)) < 2 or len(np.unique(b)) < 2:
            return float("nan")
        return float(spearmanr(a, b).statistic)

    return bootstrap_ci(rho_of, groups, n_boot=n_boot, seed=seed)


def with_restart_step(sweep: pd.DataFrame, nsteps: int) -> pd.DataFrame:
    """Return a copy of the sweep table carrying the restart step the fraction column implies."""
    sweep = sweep.copy()
    sweep["restart_step"] = ((1 - sweep[FRAC_COLUMN]) * nsteps).round().astype(int)
    return sweep


def compute_curve(
    sweep: pd.DataFrame,
    parents: pd.DataFrame,
    metrics: list[tuple[str, str]],
    child_key: str = "task",
    parent_key: str = "example_id",
    nsteps: int = 60,
    n_boot: int = 500,
    seed: int = 0,
) -> pd.DataFrame:
    """Spearman rho against the parent value, per metric and restart step.

    Args:
      sweep: Phase-2 master table (``sweep_per_example_metrics.csv``).
      parents: Phase-1 table, one row per parent.
      metrics: ``(column, label)`` pairs from :py:func:`parse_metrics`.
      child_key: Sweep column naming a child's parent. ``task`` is the parent CIF's filename stem.
      parent_key: Phase-1 column holding the same value; ``example_id`` for the standard layout.
      nsteps: Trajectory length the fractions refer to.
      n_boot: Bootstrap resamples per point.
      seed: Bootstrap seed.

    Returns:
      Tidy frame: ``metric, label, restart_step, frac, rho, ci_lo, ci_hi, n_pairs, n_parents``.
    """
    sweep = with_restart_step(sweep, nsteps)

    rows = []
    for column, label in metrics:
        try:
            sweep_values = resolve_column(sweep, column)
            parent_series = resolve_column(parents, column)
        except KeyError as missing:
            logger.warning("skipping %s: %s absent from the sweep or parent table", label, missing)
            continue
        parent_values = pd.DataFrame({"_key": parents[parent_key], column: parent_series})
        sweep_slim = pd.DataFrame(
            {"_key": sweep[child_key], column: sweep_values, "restart_step": sweep["restart_step"]}
        )

        for step, group in sweep_slim.groupby("restart_step", sort=True):
            joined = group[["_key", column]].merge(parent_values, on="_key", suffixes=("_child", "_parent")).dropna()
            child = joined[f"{column}_child"].to_numpy()
            parent = joined[f"{column}_parent"].to_numpy()
            groups = pd.factorize(joined["_key"])[0]

            ci_lo, ci_hi = bootstrap_rho(child, parent, groups, n_boot=n_boot, seed=seed)
            rows.append(
                {
                    "metric": column,
                    "label": label,
                    "restart_step": int(step),
                    "frac": round(1 - step / nsteps, 4),
                    "rho": spearmanr(child, parent).statistic if len(child) > 10 else float("nan"),
                    "ci_lo": ci_lo,
                    "ci_hi": ci_hi,
                    "n_pairs": len(child),
                    "n_parents": int(len(np.unique(groups))),
                }
            )
        # The trajectory's own end point: a parent against itself. Definitional, not measured.
        n_parents = int(parent_values[column].notna().sum())
        rows.append(
            {
                "metric": column,
                "label": label,
                "restart_step": nsteps,
                "frac": 0.0,
                "rho": 1.0,
                "ci_lo": np.nan,
                "ci_hi": np.nan,
                "n_pairs": n_parents,
                "n_parents": n_parents,
            }
        )
    return pd.DataFrame(rows)


def compute_fidelity(
    sweep: pd.DataFrame,
    series: Sequence[FidelitySeries] = FIDELITY_SERIES,
    child_key: str = "task",
    nsteps: int = 60,
    n_boot: int = 500,
    seed: int = 0,
) -> pd.DataFrame:
    """Median sequence identity and CA RMSD to the parent, per restart step.

    No parent table is needed: under partial diffusion the parent CIF *is* the input structure, so
    each child's row already carries both quantities measured against its own parent.

    Args:
      sweep: Phase-2 master table (``sweep_per_example_metrics.csv``).
      series: Which fidelity columns to follow. Absent ones are skipped with a warning.
      child_key: Sweep column naming a child's parent, used as the bootstrap resampling unit.
      nsteps: Trajectory length the fractions refer to.
      n_boot: Bootstrap resamples per point.
      seed: Bootstrap seed.

    Returns:
      Tidy frame: ``metric, label, restart_step, frac, value, ci_lo, ci_hi, n_children, n_parents``.
    """
    sweep = with_restart_step(sweep, nsteps)
    n_parents = int(sweep[child_key].nunique())

    rows = []
    for spec in series:
        if spec.column not in sweep.columns:
            logger.warning("skipping %s: %s absent from the sweep table", spec.label, spec.column)
            continue
        slim = pd.DataFrame(
            {
                "_key": sweep[child_key],
                "value": _numeric(sweep, spec.column) * spec.scale,
                "restart_step": sweep["restart_step"],
            }
        ).dropna()

        for step, group in slim.groupby("restart_step", sort=True):
            values = group["value"].to_numpy()
            groups = pd.factorize(group["_key"])[0]
            ci_lo, ci_hi = bootstrap_ci(
                lambda idx, v=values: float(np.median(v[idx])), groups, n_boot=n_boot, seed=seed
            )
            rows.append(
                {
                    "metric": spec.column,
                    "label": spec.label,
                    "restart_step": int(step),
                    "frac": round(1 - step / nsteps, 4),
                    "value": float(np.median(values)),
                    "ci_lo": ci_lo,
                    "ci_hi": ci_hi,
                    "n_children": len(values),
                    "n_parents": int(len(np.unique(groups))),
                }
            )
        # The trajectory's own end point: a parent against itself. Definitional, not measured.
        rows.append(
            {
                "metric": spec.column,
                "label": spec.label,
                "restart_step": nsteps,
                "frac": 0.0,
                "value": spec.clean_end,
                "ci_lo": np.nan,
                "ci_hi": np.nan,
                "n_children": n_parents,
                "n_parents": n_parents,
            }
        )
    return pd.DataFrame(rows)


def draw_series(axes: Axes, series: pd.DataFrame, value_column: str, color: str, colors: dict) -> None:
    """Draw one bootstrap band plus its line and markers against ``restart_step``."""
    axes.fill_between(series.restart_step, series.ci_lo, series.ci_hi, color=color, alpha=0.16, linewidth=0, zorder=2)
    axes.plot(series.restart_step, series[value_column], color=color, linewidth=2, zorder=4)
    axes.plot(
        series.restart_step,
        series[value_column],
        "o",
        markersize=4.5,
        color=color,
        markeredgecolor=colors["surface"],
        markeredgewidth=1.5,
        zorder=5,
    )


def draw_definitional_point(axes: Axes, step: int, value: float, colors: dict) -> None:
    """Mark a parent against itself: hollow and in neutral ink, so it does not read as measured."""
    axes.plot(
        [step],
        [value],
        "o",
        markersize=6,
        markerfacecolor=colors["surface"],
        markeredgecolor=colors["secondary"],
        markeredgewidth=1.6,
        zorder=6,
    )


def style_axes(axes: Axes, colors: dict) -> None:
    """Apply the shared chart furniture: horizontal grid, two spines, muted ticks."""
    axes.grid(axis="y", color=colors["grid"], linewidth=0.8, zorder=0)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(colors["axis"])
    axes.tick_params(colors=colors["muted"], labelsize=8.5)


def plot_curve(curve: pd.DataFrame, out_path: Path, metrics: list[tuple[str, str]], mode: str, nsteps: int) -> None:
    """Render the commitment curve, one line per metric."""
    colors = PALETTE[mode]
    figure, axes = plt.subplots(figsize=(9.0, 5.6), dpi=200)
    figure.patch.set_facecolor(colors["surface"])
    axes.set_facecolor(colors["surface"])

    for slot, (column, _) in enumerate(metrics):
        series = curve[(curve.metric == column) & (curve.restart_step < nsteps)].sort_values("restart_step")
        if series.empty:
            continue
        draw_series(axes, series, "rho", colors["series"][slot], colors)

    draw_definitional_point(axes, nsteps, 1.0, colors)

    axes.axhline(1.0, color=colors["axis"], linewidth=1, linestyle=":", zorder=1)
    axes.set_xlim(-3, nsteps + 4)
    # A between-problem floor can sit slightly below 0; leave room rather than clip the point.
    axes.set_ylim(min(0.0, float(curve.rho.min()) - 0.05), 1.09)
    axes.set_xticks(range(0, nsteps + 1, 10))
    axes.set_yticks(np.arange(0, 1.01, 0.2))
    axes.set_xlabel(
        f"partial-diffusion restart step   (0 = regenerate from noise → {nsteps} = the parent itself)",
        fontsize=9.5,
        color=colors["secondary"],
    )
    axes.set_ylabel("Spearman ρ  (child vs. its own parent)", fontsize=9.5, color=colors["secondary"])
    axes.set_title(
        "When does the model commit? Metric agreement between a re-noised child and its parent",
        fontsize=11.5,
        color=colors["primary"],
        pad=42,
        loc="left",
    )
    measured = curve[curve.restart_step < nsteps]
    children = int(round((measured.n_pairs / measured.n_parents).median()))
    axes.text(
        0,
        1.035,
        f"{int(measured.n_parents.max())} parents × {children} child{'' if children == 1 else 'ren'} "
        "per restart step; band = 95% bootstrap CI over parents\n"
        f"the hollow point at step {nsteps} is ρ = 1 by construction (parent vs. itself)",
        transform=axes.transAxes,
        fontsize=8.5,
        color=colors["muted"],
        va="bottom",
    )

    style_axes(axes, colors)

    handles = [
        plt.Line2D([], [], color=colors["series"][i], linewidth=2, marker="o", markersize=4.5, label=label)
        for i, (_, label) in enumerate(metrics)
    ]
    # Upper left: the curves rise left to right and converge near the top right, so this corner is
    # the region least likely to be crossed.
    legend = axes.legend(
        handles=handles,
        loc="upper left",
        frameon=False,
        fontsize=9,
        labelcolor=colors["secondary"],
        handlelength=1.8,
    )
    legend.set_zorder(7)

    figure.tight_layout()
    figure.savefig(out_path, facecolor=colors["surface"])
    plt.close(figure)
    logger.info("wrote %s", out_path)


def plot_fidelity(
    fidelity: pd.DataFrame, out_path: Path, series: Sequence[FidelitySeries], mode: str, nsteps: int
) -> None:
    """Render the fidelity curves, one stacked panel per series.

    Panels rather than one axis with two scales: percent and angstroms share no zero and no
    direction -- identity climbs to 100 while RMSD falls to 0 -- so a twin axis would invite reading
    a crossing that is an artefact of the scaling.
    """
    colors = PALETTE[mode]
    figure, panels = plt.subplots(
        len(series), 1, figsize=(9.0, 3.4 * len(series) + 1.0), dpi=200, sharex=True, squeeze=False
    )
    figure.patch.set_facecolor(colors["surface"])

    for slot, (spec, axes) in enumerate(zip(series, panels[:, 0], strict=True)):
        axes.set_facecolor(colors["surface"])
        color = colors["series"][slot % len(colors["series"])]
        measured = fidelity[(fidelity.metric == spec.column) & (fidelity.restart_step < nsteps)].sort_values(
            "restart_step"
        )
        draw_series(axes, measured, "value", color, colors)
        draw_definitional_point(axes, nsteps, spec.clean_end, colors)

        axes.axhline(spec.clean_end, color=colors["axis"], linewidth=1, linestyle=":", zorder=1)
        axes.set_xlim(-3, nsteps + 4)
        top = spec.y_max if spec.y_max is not None else float(np.nanmax(measured.ci_hi.fillna(measured.value)))
        # A sweep where the metric is 0 everywhere would otherwise ask for a zero-height axis.
        axes.set_ylim(-0.03 * (top or 1.0), (top or 1.0) * 1.09)
        axes.set_ylabel(spec.axis_label, fontsize=9.5, color=colors["secondary"])
        style_axes(axes, colors)

    bottom_axes = panels[-1, 0]
    bottom_axes.set_xticks(range(0, nsteps + 1, 10))
    bottom_axes.set_xlabel(
        f"partial-diffusion restart step   (0 = regenerate from noise → {nsteps} = the parent itself)",
        fontsize=9.5,
        color=colors["secondary"],
    )

    top_axes = panels[0, 0]
    top_axes.set_title(
        "How much of the parent survives? Sequence and backbone identity of a re-noised child",
        fontsize=11.5,
        color=colors["primary"],
        pad=42,
        loc="left",
    )
    measured = fidelity[fidelity.restart_step < nsteps]
    top_axes.text(
        0,
        1.06,
        f"median over {int(measured.n_parents.max())} parents; band = 95% bootstrap CI over parents\n"
        f"the hollow point at step {nsteps} is the parent against itself, so "
        f"{' and '.join(s.clean_end_text for s in series)} by construction",
        transform=top_axes.transAxes,
        fontsize=8.5,
        color=colors["muted"],
        va="bottom",
    )

    figure.tight_layout()
    figure.savefig(out_path, facecolor=colors["surface"])
    plt.close(figure)
    logger.info("wrote %s", out_path)


def main(
    sweep_csv: str,
    parent_csv: str,
    out_dir: str,
    metrics: str | tuple[str, ...] = "",
    child_key: str = "task",
    parent_key: str = "example_id",
    nsteps: int = 60,
    n_boot: int = 500,
    seed: int = 0,
) -> None:
    """Compute the commitment and fidelity curves and render both in both modes.

    Args:
      sweep_csv: ``sweep_per_example_metrics.csv`` from the sweep-level concat.
      parent_csv: Phase-1 ``per_example_metrics.csv`` (the parents).
      out_dir: Destination for ``commitment_curve.csv``, ``fidelity_curve.csv`` and the PNGs.
      metrics: Comma-separated ``Label=column`` entries, at most three. A column may be
        ``min(colA|colB)`` to reduce several columns to their row-wise minimum. The two fidelity
        series are always added on top of these and need no spec.
      child_key: Sweep column naming a child's parent.
      parent_key: Phase-1 column holding the same value.
      nsteps: Trajectory length the fractions refer to.
      n_boot: Bootstrap resamples per point.
      seed: Bootstrap seed.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parsed = parse_metrics(metrics)
    if not parsed:
        raise ValueError("--metrics is required, e.g. --metrics 'Docking Z=tcr_docking_geometry.docking_z'")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    sweep = pd.read_csv(sweep_csv, low_memory=False)
    curve = compute_curve(
        sweep,
        pd.read_csv(parent_csv, low_memory=False),
        metrics=parsed,
        child_key=child_key,
        parent_key=parent_key,
        nsteps=nsteps,
        n_boot=n_boot,
        seed=seed,
    )
    if curve.empty:
        raise ValueError("no metric resolved against both tables; check --metrics against the CSV headers")
    curve.to_csv(out_path / "commitment_curve.csv", index=False)
    logger.info("wrote %s", out_path / "commitment_curve.csv")

    present = [(c, label) for c, label in parsed if label in set(curve.label)]
    for mode in ("light", "dark"):
        suffix = "" if mode == "light" else "_dark"
        plot_curve(curve, out_path / f"commitment_curve{suffix}.png", present, mode=mode, nsteps=nsteps)

    fidelity = compute_fidelity(sweep, child_key=child_key, nsteps=nsteps, n_boot=n_boot, seed=seed)
    # Only the definitional end point survives if a column is present but entirely non-finite, so
    # ask for the measured rows rather than the column.
    measured_series = set(fidelity[fidelity.restart_step < nsteps].metric) if not fidelity.empty else set()
    present_series = [s for s in FIDELITY_SERIES if s.column in measured_series]
    if not present_series:
        # A sweep predating these metrics, or one whose metric group drops the inline design
        # metrics. The commitment curve above still stands; only the scale to read it on is missing.
        logger.warning(
            "no fidelity column found in %s -- the sweep needs the `partial_diffusion` inline design "
            "metrics; rerun phase 2 with a metric set that includes them",
            sweep_csv,
        )
        return
    fidelity.to_csv(out_path / "fidelity_curve.csv", index=False)
    logger.info("wrote %s", out_path / "fidelity_curve.csv")

    for mode in ("light", "dark"):
        suffix = "" if mode == "light" else "_dark"
        plot_fidelity(fidelity, out_path / f"fidelity_curve{suffix}.png", present_series, mode=mode, nsteps=nsteps)


if __name__ == "__main__":
    fire.Fire(main)

#!/usr/bin/env python
"""How rare is each metric? One histogram per metric, cut by the thresholds in the pass criteria.

Run this on the phase-1 parents before spending anything on phase 2. It answers a question the
commitment curve cannot: *how hard is each property to hit at all?* One panel per metric, the
pass-criteria thresholds drawn as vertical cuts, and for every cut the observed pass rate plus a
model-based estimate of it -- so a criterion no parent passed still gets a number, and "how many
designs must I sample for one passer" has an answer before the sweep is budgeted.

Thresholds come from a pass-criteria config (``configs/metrics/pass_criteria/all_pass_criteria.yaml``
by default), so the cuts on the figure are the same numbers the run scored its ``*.pass`` columns
with. Only criteria whose metric columns are present in the CSV are drawn.

Two estimates sit behind every observed rate, and they disagree on purpose:

* the **fitted density** drawn over the histogram (best of a few families by AIC), whose tail
  probability is a whole-distribution extrapolation, and
* a **generalised-Pareto tail fit** to the exceedances past an intermediate quantile, the
  extreme-value estimator, which is the one to believe when the cut is far out in the tail.

Neither is data. The figure quotes an extrapolation only where too few designs passed for the
observed rate to have any resolution, always names which model produced it, and marks it *poor fit*
where the density visibly fails a KS test -- a bimodal metric is the usual culprit. Read
references/method.md before quoting one.

Examples:
  >>> python metric_distributions.py \\
  ...     --metrics_csv /scratch/me/runs/my_commitment_phase1/per_example_metrics.csv \\
  ...     --out_dir /scratch/me/runs/my_commitment_phase1/analysis
  >>> python metric_distributions.py \\
  ...     --metrics_csv .../per_example_metrics.csv --out_dir .../analysis \\
  ...     --metrics 'Docking Z=tcr_docking_geometry.docking_z:min=1.0' --criteria ppi

Usage: python metric_distributions.py --metrics_csv parents.csv --out_dir analysis
Arguments: Metrics CSV, output directory, and the pass-criteria config actually used by the run.
Output: Metric distributions, threshold summaries, and light/dark PNG plots.
Exit codes: 0 for success, 1 for invalid data/runtime failure, 2 for invalid CLI arguments.
"""

# Preserve mathematical symbols used as chart labels.
# ruff: noqa: RUF001

from __future__ import annotations

import logging
import math
import warnings
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import fire
import matplotlib
import numpy as np
import pandas as pd
import yaml
from commitment_curve import PALETTE, resolve_column, style_axes
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

logger = logging.getLogger(__name__)

DEFAULT_PASS_CRITERIA = "configs/metrics/pass_criteria/all_pass_criteria.yaml"

# PassCriterionMetric's reducers, mapped to the expression syntax resolve_column understands.
REDUCER_EXPRESSIONS = {"min_of": "min", "max_of": "max", "mean_of": "mean"}

# Candidate overlays are intentionally unimodal; the KS result exposes incompatible data.
# The lowest-AIC compatible family supplies the density estimate.
CANDIDATE_DISTRIBUTIONS = {
    "norm": stats.norm,
    "skewnorm": stats.skewnorm,
    "lognorm": stats.lognorm,
    "gamma": stats.gamma,
}

# Below this many finite values a density fit is noise; the histogram is still drawn.
MIN_VALUES_TO_FIT = 20
# A metric taking fewer distinct values than this is a flag or a count, not something to fit.
MIN_UNIQUE_TO_FIT = 5
# KS against a fit whose parameters came from the same sample is anti-conservative, so a p-value
# this low is a strong signal of misfit rather than a borderline one.
POOR_FIT_P = 0.05

# Fit the generalized-Pareto tail past this quantile, while retaining MIN_EXCEEDANCES.
# Small samples use the highest order statistic that preserves that minimum.
GPD_QUANTILE = 0.80
MIN_EXCEEDANCES = 25

# Past this many observed passers the sample speaks for itself and the headline number is the
# observed rate; below it, an extrapolation is the only thing with any resolution.
OBSERVED_IS_ENOUGH = 10

# The central span the x axis shows. A single wild outlier otherwise collapses every real bar into
# one bin, which is how a histogram silently stops being readable.
AXIS_PERCENTILES = (0.5, 99.5)

Z_95 = 1.959964


class Cutoff(NamedTuple):
    """One threshold from a pass criterion, and which criteria asked for it.

    Args:
      kind: ``"min"`` (pass at or above) or ``"max"`` (pass at or below).
      value: The threshold itself, in the metric's own units.
      sources: Pass-criteria entry names that impose it, e.g. ``("ppi", "sm_binder")``.
    """

    kind: str
    value: float
    sources: tuple[str, ...]

    @property
    def symbol(self) -> str:
        return "≥" if self.kind == "min" else "≤"

    def passes(self, values: np.ndarray) -> np.ndarray:
        """Boolean mask of the values on the passing side."""
        return values >= self.value if self.kind == "min" else values <= self.value

    def visible_span(self, lo: float, hi: float) -> tuple[float, float] | None:
        """The passing interval clipped to an axis window, or ``None`` if none of it is visible."""
        start, end = (max(self.value, lo), hi) if self.kind == "min" else (lo, min(self.value, hi))
        return (start, end) if end > start else None


class Panel(NamedTuple):
    """One metric's histogram: the column expression, its title, and every cut drawn on it."""

    column: str
    label: str
    cutoffs: tuple[Cutoff, ...]


class DensityFit(NamedTuple):
    """The best-AIC density family for one metric, and how badly it misses."""

    name: str
    frozen: Any
    aic: float
    ks_p: float  # below POOR_FIT_P the family is wrong, whatever its AIC rank said


class TailFit(NamedTuple):
    """A generalised-Pareto fit to one tail, or an empty one if the tail could not support it."""

    rate: float
    threshold: float
    shape: float
    scale: float
    n_exceedances: int

    @classmethod
    def empty(cls) -> TailFit:
        return cls(math.nan, math.nan, math.nan, math.nan, 0)


def _interpolated_path(node: Any) -> str | None:
    """Return the dotted path of an OmegaConf ``${a.b.c}`` reference, or ``None`` if not one."""
    if isinstance(node, str) and node.startswith("${") and node.endswith("}"):
        return node[2:-1]
    return None


def _resolve_thresholds(spec: Any, document: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a ``metric_thresholds`` value, following a same-file ``${...}`` reference once.

    ``all_pass_criteria.yaml`` defines ``internal_coords`` as a reference to ``motif_scaffold``'s
    thresholds. ``yaml.safe_load`` leaves that as a literal string, so follow it here rather than
    pull Hydra in to read one file.
    """
    path = _interpolated_path(spec)
    if path is None:
        return spec if isinstance(spec, dict) else None
    # Paths are absolute in the composed config; this file is the `metrics.pass_criteria` node.
    node: Any = document
    for part in path.removeprefix("metrics.pass_criteria.").split("."):
        if not isinstance(node, dict) or part not in node:
            logger.warning("cannot resolve threshold reference %s; skipping that criterion", spec)
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def _column_expression(label: str, spec: dict[str, Any]) -> str:
    """Turn one threshold spec into a column expression :py:func:`resolve_column` understands.

    Examples:
      >>> _column_expression("oracle.plddt_coi", {"min": 70.0})
      'oracle.plddt_coi'
      >>> _column_expression(
      ...     "best_ipae", {"min_of": ["oracle.ipae_B", "oracle.ipae_C"], "max": 1.5}
      ... )
      'min(oracle.ipae_B|oracle.ipae_C)'
    """
    for reducer, expression in REDUCER_EXPRESSIONS.items():
        if reducer in spec:
            return f"{expression}({'|'.join(spec[reducer])})"
    return label


def _dedupe_cutoffs(cuts: dict[tuple[str, float], list[str]]) -> tuple[Cutoff, ...]:
    """Collapse a (kind, value) -> sources mapping into cuts ordered by threshold."""
    return tuple(
        Cutoff(kind, value, tuple(dict.fromkeys(sources)))
        for (kind, value), sources in sorted(cuts.items(), key=lambda item: item[0][1])
    )


def read_pass_criteria(paths: Sequence[str], keep: Sequence[str] | None = None) -> list[Panel]:
    """Read every threshold out of one or more pass-criteria configs, one panel per metric.

    A column named by several criteria gets one panel carrying all their cuts, deduplicated by
    (kind, value) -- so ``refolded_backbone_rmsd.rmsd``, thresholded by five criteria at two
    distinct values, draws two lines rather than five.

    Args:
      paths: Pass-criteria YAML files, in the layout of
        ``configs/metrics/pass_criteria/all_pass_criteria.yaml``.
      keep: Criteria entry names to keep, or ``None`` for all of them.

    Returns:
      Panels in the order their columns were first seen, each with its cuts sorted by value.
    """
    collected: dict[str, dict[tuple[str, float], list[str]]] = {}
    labels: dict[str, str] = {}
    for path in paths:
        document = yaml.safe_load(Path(path).read_text()) or {}
        for criterion, entry in document.items():
            if not isinstance(entry, dict) or "metric_thresholds" not in entry:
                continue
            if keep is not None and criterion not in keep:
                continue
            thresholds = _resolve_thresholds(entry["metric_thresholds"], document)
            for label, spec in (thresholds or {}).items():
                column = _column_expression(label, spec)
                # A reduction's outer key is a human label; a plain key is the column itself.
                labels.setdefault(column, label)
                cuts = collected.setdefault(column, {})
                for kind in ("min", "max"):
                    if spec.get(kind) is not None:
                        cuts.setdefault((kind, float(spec[kind])), []).append(criterion)

    return [Panel(column, labels[column], _dedupe_cutoffs(cuts)) for column, cuts in collected.items()]


def parse_metric_panels(spec: str | tuple[str, ...]) -> list[Panel]:
    """Parse the ``--metrics`` spec into panels, with optional inline cuts.

    Each entry is ``Label=column`` with any number of ``:min=V`` / ``:max=V`` suffixes. The column
    may be a ``min(a|b)`` / ``max(a|b)`` / ``mean(a|b)`` reduction.

    Examples:
      >>> panel = parse_metric_panels("Docking Z=tcr_docking_geometry.docking_z:min=1.0")[0]
      >>> panel.column, panel.label, panel.cutoffs[0].value
      ('tcr_docking_geometry.docking_z', 'Docking Z', 1.0)
      >>> parse_metric_panels("ipAE=min(oracle.ipae_B|oracle.ipae_C)")[0].cutoffs
      ()
    """
    entries = [e for e in (spec.split(",") if isinstance(spec, str) else list(spec)) if e.strip()]
    panels = []
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"--metrics entry {entry!r} must be 'Label=column[:min=V][:max=V]'")
        label, remainder = entry.split("=", 1)
        column, *bounds = remainder.split(":")
        cutoffs = []
        for bound in bounds:
            kind, _, value = bound.partition("=")
            if kind.strip() not in ("min", "max") or not value:
                raise ValueError(f"--metrics entry {entry!r} has a bad bound {bound!r}; use ':min=V' or ':max=V'")
            cutoffs.append(Cutoff(kind.strip(), float(value), ("--metrics",)))
        panels.append(Panel(column.strip(), label.strip(), tuple(sorted(cutoffs, key=lambda c: c.value))))
    return panels


def merge_panels(primary: Sequence[Panel], secondary: Sequence[Panel]) -> list[Panel]:
    """Merge two panel lists on the column, keeping ``primary``'s order and label.

    Cuts from both sides are unioned and deduplicated, so a metric the user tracks explicitly still
    picks up whatever threshold the pass criteria impose on it.
    """
    merged: dict[str, Panel] = {}
    for panel in [*primary, *secondary]:
        if panel.column not in merged:
            merged[panel.column] = panel
            continue
        existing = merged[panel.column]
        cuts: dict[tuple[str, float], list[str]] = {}
        for cut in [*existing.cutoffs, *panel.cutoffs]:
            cuts.setdefault((cut.kind, cut.value), []).extend(cut.sources)
        merged[panel.column] = existing._replace(cutoffs=_dedupe_cutoffs(cuts))
    return list(merged.values())


def fit_density(values: np.ndarray) -> DensityFit | None:
    """Fit each candidate family and return the lowest-AIC one, with its KS p-value.

    Returns ``None`` when the sample is too small or too discrete to describe, or when every family
    failed -- the histogram is then drawn bare and no whole-distribution estimate is offered.
    """
    if len(values) < MIN_VALUES_TO_FIT or len(np.unique(values)) < MIN_UNIQUE_TO_FIT:
        return None

    best: DensityFit | None = None
    for name, family in CANDIDATE_DISTRIBUTIONS.items():
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            # A family that cannot describe this support warns its way to a bad fit; drop it quietly.
            warnings.simplefilter("ignore")
            try:
                params = family.fit(values)
            except (RuntimeError, ValueError, stats.FitError):
                continue
            frozen = family(*params)
            loglik = float(np.sum(frozen.logpdf(values)))
            ks_p = float(stats.kstest(values, frozen.cdf).pvalue)
        if not np.isfinite(loglik):
            continue
        aic = 2 * len(params) - 2 * loglik
        if best is None or aic < best.aic:
            best = DensityFit(name, frozen, aic, ks_p)
    return best


def fitted_rate(fit: DensityFit, cutoff: Cutoff) -> float:
    """Tail probability the fitted density assigns to the passing side of a cut."""
    return float(fit.frozen.sf(cutoff.value) if cutoff.kind == "min" else fit.frozen.cdf(cutoff.value))


def gpd_tail(values: np.ndarray, cutoff: Cutoff) -> TailFit:
    """Peaks-over-threshold estimate of the pass rate, for a cut out in the tail.

    Orients both sample and cut so that "passing" always means "large", fits a generalised Pareto to
    the exceedances past an intermediate threshold, and multiplies its survival at the cut by the
    exceedance rate. Extreme-value theory says this is the right shape for a tail whatever the bulk
    looks like, which is why it outranks the whole-distribution fit once the cut is far out.

    Returns:
      The estimate and its fitted parameters, or :py:meth:`TailFit.empty` when the cut is not past
      the intermediate threshold, there are too few exceedances, or the fit fails.
    """
    # A flag or a small-integer count has no tail to extrapolate, only ties.
    if len(np.unique(values)) < MIN_UNIQUE_TO_FIT:
        return TailFit.empty()
    oriented = values if cutoff.kind == "min" else -values
    target = cutoff.value if cutoff.kind == "min" else -cutoff.value

    # Use an order statistic so tied values cannot reduce the tail below the requested size.
    # Select the highest threshold that retains enough strict exceedances.
    wanted = max(MIN_EXCEEDANCES, math.ceil((1 - GPD_QUANTILE) * len(oriented)))
    ordered = np.sort(oriented)
    above = len(ordered) - np.searchsorted(ordered, ordered, side="right")
    eligible = np.flatnonzero(above >= wanted)
    if len(eligible) == 0:
        return TailFit.empty()
    threshold = float(ordered[eligible[-1]])
    exceedances = oriented[oriented > threshold] - threshold
    # Inside the bulk the observed rate already beats any extrapolation.
    if target <= threshold:
        return TailFit.empty()

    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            shape, _, scale = stats.genpareto.fit(exceedances, floc=0)
        except (RuntimeError, ValueError, stats.FitError):
            return TailFit.empty()
        # A negative shape is a bounded tail, and a survival of 0 past its endpoint is a real answer.
        survival = float(stats.genpareto.sf(target - threshold, shape, loc=0, scale=scale))

    rate = len(exceedances) / len(oriented) * survival
    return TailFit(
        rate, threshold if cutoff.kind == "min" else -threshold, float(shape), float(scale), len(exceedances)
    )


def wilson_interval(n_pass: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Wilson rather than the normal approximation because the interesting cases here are rates near
    zero, where the normal interval goes negative and has no coverage at all.
    """
    if n == 0:
        return math.nan, math.nan
    phat = n_pass / n
    denominator = 1 + Z_95**2 / n
    centre = (phat + Z_95**2 / (2 * n)) / denominator
    spread = Z_95 * math.sqrt(phat * (1 - phat) / n + Z_95**2 / (4 * n**2)) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)


def choose_estimate(n_pass: int, observed: float, tail: TailFit, fit: DensityFit | None, fit_rate: float) -> str:
    """Name the estimate to headline: the sample where it has resolution, an extrapolation where not.

    Returns:
      ``"observed"``, ``"GPD tail"``, a density family name, or ``"none"`` if nothing could be fitted.
    """
    if n_pass >= OBSERVED_IS_ENOUGH:
        return "observed"
    if np.isfinite(tail.rate):
        return "GPD tail"
    if fit is not None and np.isfinite(fit_rate):
        return fit.name
    return "none"


def axis_window(values: np.ndarray, cutoffs: Sequence[Cutoff]) -> tuple[float, float]:
    """Robust x range: the central span of the data, plus any cut sitting near it.

    A cut far outside the data is deliberately *not* included. Stretching the axis to reach a
    threshold nothing comes close to would flatten every bar into one bin, and the caption reports
    that cut's rate whether or not its line is on screen.
    """
    lo, hi = (float(v) for v in np.percentile(values, AXIS_PERCENTILES))
    if hi <= lo:
        lo, hi = float(np.min(values)), float(np.max(values))
    if hi <= lo:  # a metric that is constant across every design
        lo, hi = lo - 0.5, hi + 0.5
    span = hi - lo

    for cutoff in cutoffs:
        if lo - span <= cutoff.value <= hi + span:
            lo, hi = min(lo, cutoff.value), max(hi, cutoff.value)
    margin = 0.04 * (hi - lo)
    return lo - margin, hi + margin


class Drawable(NamedTuple):
    """A metric that resolved against the table: what to plot, and the work already done for it."""

    panel: Panel
    values: np.ndarray
    fit: DensityFit | None
    window: tuple[float, float]


def summarise(frame: pd.DataFrame, panels: Sequence[Panel]) -> tuple[pd.DataFrame, list[Drawable]]:
    """Per metric and cut: the observed pass rate, the fitted rate, and the tail estimate.

    Args:
      frame: A metrics table, one row per design (``per_example_metrics.csv``).
      panels: Metrics to summarise, from :py:func:`read_pass_criteria` / :py:func:`parse_metric_panels`.

    Returns:
      A tidy frame -- one row per (metric, cut), or one cut-less row for a metric with no threshold
      -- and the metrics that resolved, carrying the values, fit and axis window the figure reuses.
    """
    rows: list[dict[str, Any]] = []
    drawable: list[Drawable] = []

    for panel in panels:
        try:
            series = resolve_column(frame, panel.column)
        except KeyError as missing:
            logger.info("skipping %s: %s absent from the table", panel.label, missing)
            continue
        values = series.dropna().to_numpy(dtype=float)
        if len(values) < 3:
            logger.info("skipping %s: only %d finite values", panel.label, len(values))
            continue

        fit = fit_density(values)
        drawable.append(Drawable(panel, values, fit, axis_window(values, panel.cutoffs)))
        summary = {
            "metric": panel.column,
            "label": panel.label,
            "n": len(values),
            "n_missing": int(len(frame) - len(values)),
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "p05": float(np.percentile(values, 5)),
            "p95": float(np.percentile(values, 95)),
            "fit_name": fit.name if fit else "",
            "fit_aic": fit.aic if fit else math.nan,
            "fit_ks_p": fit.ks_p if fit else math.nan,
        }
        if not panel.cutoffs:
            rows.append(summary)
            continue

        for cutoff in panel.cutoffs:
            n_pass = int(np.count_nonzero(cutoff.passes(values)))
            observed = n_pass / len(values)
            ci_lo, ci_hi = wilson_interval(n_pass, len(values))
            fit_rate = fitted_rate(fit, cutoff) if fit else math.nan
            tail = gpd_tail(values, cutoff)
            source = choose_estimate(n_pass, observed, tail, fit, fit_rate)
            estimate = {"observed": observed, "GPD tail": tail.rate, "none": math.nan}.get(source, fit_rate)
            rows.append(
                summary
                | {
                    "cutoff_kind": cutoff.kind,
                    "cutoff": cutoff.value,
                    "cutoff_sources": " ".join(cutoff.sources),
                    "n_pass": n_pass,
                    "rate_observed": observed,
                    "rate_ci_lo": ci_lo,
                    "rate_ci_hi": ci_hi,
                    "rate_fit": fit_rate,
                    "rate_gpd": tail.rate,
                    "gpd_threshold": tail.threshold,
                    "gpd_shape": tail.shape,
                    "gpd_scale": tail.scale,
                    "gpd_n_exceedances": tail.n_exceedances,
                    "estimate_source": source,
                    "rate_estimate": estimate,
                    "designs_per_pass": 1 / estimate if estimate > 0 else math.inf,
                }
            )
    return pd.DataFrame(rows), drawable


def _format_count(rate: float) -> str:
    """``1 in N`` designs for one passer, at a precision the estimate can support."""
    if not np.isfinite(rate) or rate <= 0:
        return "—"
    expected = 1 / rate
    return f"1 in {expected:,.0f}" if expected < 10_000 else f"1 in {expected:.0e}".replace("e+0", "e")


def _format_rate(rate: float) -> str:
    if not np.isfinite(rate):
        return "—"
    return f"{rate * 100:.2g}%" if 0 < rate < 0.001 else f"{rate * 100:.1f}%"


def _cutoff_caption(cutoff: Cutoff, summary: pd.DataFrame, window: tuple[float, float]) -> str:
    """The one-line verdict drawn above a panel for one cut."""
    sources = cutoff.sources[0] + (f" +{len(cutoff.sources) - 1}" if len(cutoff.sources) > 1 else "")
    head = f"{cutoff.symbol}{cutoff.value:g} {sources}"
    if not (window[0] <= cutoff.value <= window[1]):
        head += " (off axis)"

    row = summary[(summary.cutoff_kind == cutoff.kind) & (summary.cutoff == cutoff.value)]
    if row.empty:
        return head
    row = row.iloc[0]
    caption = f"{head} · {int(row.n_pass)}/{int(row.n)} = {_format_rate(row.rate_observed)}"
    if row.estimate_source == "observed":
        # The observed rate is its own estimate here; naming it twice is noise.
        return f"{caption} ({_format_count(row.rate_observed)})"
    if not np.isfinite(row.rate_estimate) or row.rate_estimate <= 0:
        # A bounded fit that ends before the cut. Not "never", but rarer than this sample can resolve.
        return f"{caption} · {row.estimate_source} ends before the cut"
    caption += f" · {row.estimate_source} {_format_rate(row.rate_estimate)} ({_format_count(row.rate_estimate)})"
    if row.estimate_source == row.fit_name and row.fit_ks_p < POOR_FIT_P:
        return caption + " — poor fit"
    # Two extrapolations that agree are worth trusting and worth only one number; two that disagree
    # by an order of magnitude mean the tail is not identified, and hiding the second would be a lie.
    other = row.rate_fit if row.estimate_source == "GPD tail" else row.rate_gpd
    other_name = row.fit_name if row.estimate_source == "GPD tail" else "GPD tail"
    if np.isfinite(other) and other > 0 and max(other / row.rate_estimate, row.rate_estimate / other) > 10:
        caption += f"; {other_name} says {_format_count(other)}"
    return caption


def draw_panel(axes: Axes, drawable: Drawable, summary: pd.DataFrame, colors: dict, bins: int) -> None:
    """Draw one metric: histogram, fitted density, and a vertical cut per threshold."""
    panel, values, lo, hi = drawable.panel, drawable.values, *drawable.window
    axes.set_facecolor(colors["surface"])
    counts, edges, _ = axes.hist(
        values, bins=bins, range=(lo, hi), color=colors["muted"], edgecolor=colors["surface"], linewidth=0.5, zorder=3
    )

    if drawable.fit is not None:
        # Counts, not density, on the y axis -- "how many designs" is the question -- so the pdf is
        # scaled by the sample size and bin width to live on the same axis.
        grid = np.linspace(lo, hi, 400)
        axes.plot(
            grid,
            drawable.fit.frozen.pdf(grid) * len(values) * (edges[1] - edges[0]),
            color=colors["series"][0],
            linewidth=1.8,
            zorder=5,
        )

    for slot, cutoff in enumerate(panel.cutoffs):
        color = colors["series"][1 + slot % (len(colors["series"]) - 1)]
        if lo <= cutoff.value <= hi:
            axes.axvline(cutoff.value, color=color, linewidth=1.6, linestyle="--", zorder=6)
        if span := cutoff.visible_span(lo, hi):
            axes.axvspan(*span, color=color, alpha=0.09, linewidth=0, zorder=1)

    top = float(np.max(counts)) if len(counts) else 0.0
    axes.set_xlim(lo, hi)
    axes.set_ylim(0, top * 1.12 if top else 1.0)
    beyond = int(np.count_nonzero((values < lo) | (values > hi)))
    axes.set_xlabel(
        panel.label + (f"   ({beyond} beyond the axis)" if beyond else ""), fontsize=8.5, color=colors["secondary"]
    )
    style_axes(axes, colors)

    captions = [_cutoff_caption(cutoff, summary, drawable.window) for cutoff in panel.cutoffs]
    if not captions:
        captions = [f"n = {len(values)}; no pass criterion thresholds this metric"]
        caption_colors = [colors["muted"]]
    else:
        caption_colors = [colors["series"][1 + i % (len(colors["series"]) - 1)] for i in range(len(captions))]
    # Bottom-up, so the first cut's line sits nearest the plot it belongs to.
    for slot, (caption, color) in enumerate(zip(reversed(captions), reversed(caption_colors), strict=True)):
        axes.text(0, 1.02 + slot * 0.08, caption, transform=axes.transAxes, fontsize=7.2, color=color, va="bottom")


def plot_distributions(
    drawable: Sequence[Drawable], summary: pd.DataFrame, out_path: Path, mode: str, bins: int, ncols: int
) -> None:
    """Render every metric as one grid of histograms."""
    colors = PALETTE[mode]
    ncols = min(ncols, len(drawable))
    nrows = math.ceil(len(drawable) / ncols)
    # Every cut writes a caption line above its panel and tight_layout cannot see free text, so both
    # the top margin and the gap between rows have to be bought explicitly.
    caption_rows = max(max((len(d.panel.cutoffs) for d in drawable), default=1), 1)
    header = 0.62 + 0.20 * caption_rows

    figure, grid = plt.subplots(nrows, ncols, figsize=(5.0 * ncols, 3.1 * nrows + header), dpi=200, squeeze=False)
    figure.patch.set_facecolor(colors["surface"])

    for axes, item in zip(grid.flat, drawable, strict=False):
        draw_panel(axes, item, summary[summary.metric == item.panel.column], colors, bins)
    for axes in list(grid.flat)[len(drawable) :]:
        axes.set_visible(False)
    for row in range(nrows):
        grid[row, 0].set_ylabel("designs", fontsize=8.5, color=colors["secondary"])

    # figure.text rather than suptitle for the title too: tight_layout reserves its own space for a
    # suptitle, which would double-count against the `rect` already sized for the header.
    height = figure.get_figheight()
    figure.text(
        0.008,
        1 - 0.16 / height,
        "How rare is each metric? Distribution over the designs, cut by the pass criteria",
        fontsize=12,
        color=colors["primary"],
        va="top",
        ha="left",
    )
    figure.text(
        0.008,
        1 - 0.42 / height,
        f"{int(summary.n.max())} designs; dashed lines are pass-criteria thresholds and the shaded side passes; the "
        "curve is the best-AIC density fit.\nEach cut's rate is the observed one, unless fewer than "
        f"{OBSERVED_IS_ENOUGH} designs passed, when the named extrapolation is quoted instead.",
        fontsize=8.5,
        color=colors["muted"],
        va="top",
        ha="left",
    )

    figure.tight_layout(rect=(0, 0, 1, 1 - header / height))
    figure.subplots_adjust(hspace=0.30 + 0.13 * caption_rows, wspace=0.22)
    figure.savefig(out_path, facecolor=colors["surface"])
    plt.close(figure)
    logger.info("wrote %s", out_path)


def _as_list(value: str | Iterable[str]) -> list[str]:
    return [value] if isinstance(value, str) else [str(v) for v in value]


def main(
    metrics_csv: str,
    out_dir: str,
    pass_criteria: str | tuple[str, ...] = DEFAULT_PASS_CRITERIA,
    criteria: str | tuple[str, ...] | None = None,
    metrics: str | tuple[str, ...] = "",
    bins: int = 30,
    ncols: int = 3,
) -> None:
    """Summarise how rare each metric is, and render the histograms in both modes.

    Args:
      metrics_csv: A ``per_example_metrics.csv`` -- normally phase 1's, but any run's works.
      out_dir: Destination for ``metric_distributions.csv`` and the PNGs.
      pass_criteria: Pass-criteria config(s) supplying the thresholds. Pass ``""`` for no cuts
        beyond those given inline in ``--metrics``.
      criteria: Comma-separated criteria entry names to keep, or omit for every entry whose columns
        are present in the CSV.
      metrics: Comma-separated ``Label=column[:min=V][:max=V]`` entries, drawn first and merged with
        whatever the pass criteria say about the same column. A column may be a ``min(a|b)``,
        ``max(a|b)`` or ``mean(a|b)`` reduction.
      bins: Histogram bins per panel.
      ncols: Panels per row.

    Raises:
      ValueError: If nothing was asked for, or if no metric resolved against the CSV.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(metrics_csv, low_memory=False)
    keep = None if criteria is None else [name.strip() for entry in _as_list(criteria) for name in entry.split(",")]
    from_config = read_pass_criteria([p for p in _as_list(pass_criteria) if p], keep=keep)
    panels = merge_panels(parse_metric_panels(metrics), from_config)
    if not panels:
        raise ValueError("nothing to plot; give --metrics or point --pass_criteria at a config with thresholds")

    summary, drawable = summarise(frame, panels)
    if not drawable:
        raise ValueError(f"none of the {len(panels)} requested metrics resolved against {metrics_csv}")
    logger.info("%d of %d requested metrics are present in the table", len(drawable), len(panels))

    summary.to_csv(out_path / "metric_distributions.csv", index=False)
    logger.info("wrote %s", out_path / "metric_distributions.csv")

    for mode in ("light", "dark"):
        suffix = "" if mode == "light" else "_dark"
        plot_distributions(
            drawable, summary, out_path / f"metric_distributions{suffix}.png", mode=mode, bins=bins, ncols=ncols
        )


if __name__ == "__main__":
    fire.Fire(main)

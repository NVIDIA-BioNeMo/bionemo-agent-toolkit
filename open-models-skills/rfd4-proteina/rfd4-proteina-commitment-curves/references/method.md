# The method, and the statistics that decide whether the curve means anything

## What is being measured

For each parent design and each restart step `s`, re-noise the parent to the time the
schedule holds at `s`, denoise forward, and score the child with the same metric set that
scored the parent. Then, per (metric, step), take the Spearman correlation between the
children's values and their own parents' values across all parents.

ρ answers: *if I had stopped the trajectory at step `s` and screened on this metric, how
well would that ranking predict the final one?* Rank correlation because it is scale-free
— three metrics in different units land on one axis.

## The x axis

`partial_trajectory_fraction_steps = frac` re-runs that fraction of the trajectory, so
`restart step = (1 - frac) * nsteps`. With `nsteps: 60`, a grid every 5 steps is
`frac ∈ {0.0833, 0.1667, …, 1.00}`. Step 0 is a full regeneration; step 60 is the parent.

**Use the fraction knob, not `partial_t_backbone`.** The modalities run different
schedule curves (`bb_ca` log, `local_latents` power), so handing both the same numeric
`t` puts them at different points of their own trajectories. Fraction mode reads every
modality's schedule at one shared step index, and removes the need for `couple_partial_t`.

## Parents are the sample size

Children of one parent are correlated, so the effective n is the number of **parents**:

- Budget **40+ parents**. A ρ from 4 has a confidence interval of roughly ±0.9 — enough
  to draw a smooth-looking curve that means nothing.
- Phase 2 therefore uses **one child per parent**. A second child only estimates
  within-parent spread. Budget for 2x the designs is better spent on 2x the parents.
- The bootstrap in `commitment_curve.py` resamples parents, not rows, for the same
  reason; resampling rows would understate the interval badly.

Replicates still make sense in **phase 1**: there each replicate of a design problem
becomes its own parent.

## The fidelity curves, and why they are not optional

Two more curves are always computed, from columns phase 2 produces on its own because the
parent CIF is the *input* structure of a partial-diffusion run:

- `sequence_similarity_to_input.sequence_identity_to_input` — fraction of positions whose
  amino acid type is unchanged, plotted as a percent.
- `ca_rmsd_to_input.rmsd` — CA RMSD to the parent after superposition, in angstroms.

Both are absolute per-child quantities, so they need no join and no parent table; they are
summarised as the **median across parents** with the same parent-resampled bootstrap. The
median rather than the mean because a handful of children that rebuild completely would
otherwise drag the whole curve.

They do two jobs. First they are a far sharper clean-end control than ρ: identity must be
100% and RMSD 0 Å at the smallest fraction, with no reproducibility ceiling to excuse a
shortfall. Second they disambiguate a falling ρ, which otherwise has two causes that look
identical:

| identity / RMSD | ρ | reading |
| --- | --- | --- |
| still at plateau | high | the property is fixed and so is the structure — nothing has happened yet |
| still at plateau | falling | the metric is **sensitive**: the same fold, re-scored, ranks differently |
| already departed | high | the **conditioning** fixes the metric, not the trajectory |
| already departed | falling | genuine re-decision — the model is building a different protein |

The step where the fidelity curves leave their plateau is the step the model stops
rebuilding and starts refining, and it is the natural reference point for every ρ crossing
you quote.

## How rare is each metric, and what the two extrapolations assume

`metric_distributions.py` answers a different question from the curve: not *when* a
property is decided but *how often* it lands where you need it. Per metric it draws the
histogram of the parents, the pass-criteria thresholds as vertical cuts, and per cut three
numbers — one measured, two modelled.

**The measured one.** The observed pass rate, with a 95% Wilson interval in the CSV.
Wilson rather than the normal approximation because every interesting case here sits near
zero, where a normal interval goes negative and has no coverage at all. With `k` passers
out of `n` this is all you need — *until `k` is small*, and at `k = 0` it says only "below
roughly `3/n`", which is why the other two exist.

**The density fit.** Each of `norm`, `skewnorm`, `lognorm`, `gamma` is fitted by maximum
likelihood and the lowest AIC wins; that is the curve drawn over the histogram, and its
tail probability at the cut is one estimate. It uses the whole sample, so it is efficient
*if the family is right* — and badly wrong if it is not, because the bulk it fits well
dictates a tail nothing constrains. A KS p-value goes in the CSV as `fit_ks_p`, and the
figure marks any estimate it headlines from a fit with p < 0.05 as **poor fit**. KS with
parameters estimated from the same sample is anti-conservative, so a small p is a strong
signal of misfit, not a borderline one.

**The generalised-Pareto tail fit.** Peaks-over-threshold: orient the values so passing
means large, take the exceedances past an intermediate threshold (the top 20%, or the top
25 points where the sample is small — an order statistic rather than a quantile, because
an oracle reporting four decimal places still ties often enough for `> quantile(0.8)` to
return half the intended tail), fit a GPD to them and multiply its survival at the cut by
the exceedance rate. The Pickands–Balkema–de Haan result says the tail has this shape
whatever the bulk looks like, which is why it is the one the figure headlines when both
are available.

**Which number the figure shows.** The observed rate once at least 10 designs passed;
otherwise the GPD estimate; otherwise the density fit; and the source is always named on
the chart. When the two extrapolations disagree by more than 10x the second is printed
too — that disagreement is the finding, and it means the tail is not identified.

Three limits worth stating out loud when you quote one of these:

- **A negative GPD shape is a bounded tail.** Past its endpoint the survival is zero and
  the caption reads *ends before the cut*. That is "rarer than this sample can resolve",
  never "impossible".
- **Bimodality breaks both.** A metric with two clusters (a docked and an undocked mode,
  say) gets a unimodal curve drawn over it that fits neither, and a GPD fitted to the
  upper edge of the *nearer* cluster which knows nothing of a further one. Both estimates
  are then worthless; the KS flag is what catches it.
- **They extrapolate, so they inherit the sample's biases.** A rate estimated from 40
  parents of one design problem is that problem's rate, not the model's.

Sanity-check against the run's own `*.pass` columns on the same set of designs with all
required metrics present. The joint pass rate is at most the **smallest individual pass
rate**. Multiplying individual rates gives the joint probability only if the filters are
independent; it is not a general bound. Two identical filters that each pass 50% also pass
50% together, not 25%. Use the measured combined `*.pass` mean for sampling budgets,
report its complete-case denominator, and report missing-metric designs separately.

## The two controls

**The clean end (highest restart step).** The smallest fraction must reproduce the
parents, ρ ≈ 1. This is a plumbing check on partial diffusion, not a data point. If it
fails, nothing else in the sweep is interpretable.

**The floor (step 0).** A full regeneration under identical conditioning. If the parents
are different design problems this is **not 0** — it is the between-problem floor, i.e.
how much of the metric the input fixes regardless of what the trajectory does. Quote it
explicitly; a curve that "only" falls to 0.7 may have fallen all the way.

## Each metric has its own ceiling

At the highest restart step the child is structurally the parent. If ρ there is below 1,
the gap is the metric's own reproducibility limit, not a property of the model — a
stochastic relax (FastRelax) re-minimises differently each call, a sampled oracle (AF3)
returns a different number per diffusion seed.

So read a curve **relative to its own ceiling**. A metric that plateaus at 0.78 and
reaches 0.55 by step 50 has recovered 71% of its attainable correlation there; reporting
"0.55, so it has not committed" would be wrong. If a ceiling is low, either pin the
stochastic inputs (fix the oracle seed) or accept that it cannot resolve a commitment
point finely.

## Validate the scorer before you trust the curve

1. **Check the parents have spread.** A metric that collapses to one value across parents
   has nothing for the sweep to detect.
2. **Check the metric ranks known-good structures correctly.** If a solved native scores
   in the worst quartile of your designs, the metric is measuring something else.
3. **Check non-finite values.** `commitment_curve.py` drops non-finites per metric; count
   how many you lost.

## Interpreting

State the crossing point in steps: *above step X the property is preserved; by step Y a
child is indistinguishable from an independent design.*

Then look at the children's **absolute** metric values per step, not only ρ. The two
answer different questions and can diverge — below some restart step children may both
forget their parent *and* land on worse structures than a fresh run, which means partial
diffusion is actively harmful there. Correlation alone hides that.

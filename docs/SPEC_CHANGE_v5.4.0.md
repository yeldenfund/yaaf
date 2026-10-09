# Spec change v5.4.0 — equal weights

Declared 2026-10-09. Replaces the calibrated weight vector with 1/N over the
live components. Scope: the weights, and nothing else. The drawdown penalty,
the CVaR penalty and the formula's shape are untouched here; the drawdown is
diagnosed in `D7_FINDINGS.md` and not yet declared.

## The change

    W = {k: 1/8 for k in W}          W_SUM = 1.0

replacing

    sharpe_dsr 0.14   avg_r 0.16   pf_pct 0.12   pf 0.10
    stability  0.09   winrate 0.08  sortino 0.07  vol 0.05     W_SUM = 0.81

`S_RAW = clamp(Σ sᵢwᵢ / W_SUM − cvar_pen − dd_pen, 0, 100)` is unchanged, and
the division by `W_SUM` keeps the scale, so the ceiling stays exactly 100.

1/N is taken over the keys present in `W`. A component the amendment removed
is not in `W` and therefore receives no weight: equal weighting cannot
resurrect `smoothness` or `mc`. The simulation prints the component list it
weighted, so that is checkable rather than asserted.

## Why

**The grounds are in the record already.** Dawes (1979) on improper linear
models: unit weights on standardized predictors match or beat regression
weights out of sample, because estimated weights carry estimation error that
usually exceeds the precision they buy. DeMiguel, Garlappi and Uppal (2009):
1/N beats optimized portfolios out of sample for the same reason. Both are
cited in the whitepaper.

**And the calibration this replaces was done against a broken instrument.**
Measured today, in this order: `CF` was pinned at 1.0 for most of the
population by an accumulation defect (v5.2.0); the PSR feeding `sharpe_dsr`
used a `T` of days against a per-trade Sharpe (v5.3.0); `s_mc` was the
constant 50 and `smoothness` nearly constant, both removed by Amendment
v5.0.2. Weights fitted while four of eleven components were degenerate or
wrong describe the defects, not the phenomenon. There is no version of the
calibration worth preserving.

## What it costs, measured

`sim_weights_dd.py` on the 500 sealed GMX payloads, 302 of them above the
30-trade floor, scored from a fresh state:

| | ρ vs calibrated, excluding floored | top-20 kept | floored at 0 | mean S_RAW |
|---|---|---|---|---|
| calibrated (base) | 1.0000 | 20/20 | 11/302 | 26.13 |
| **1/N** | **0.9944** | **18/20** | 9/302 | 31.51 |

Spearman is computed with average ranks, over the agents that neither variant
floored — comparing with the floored included measures the number of ties, not
the agreement. Both figures are in the simulation's output so the choice of
which to report cannot decide the conclusion; including the floored, ρ is
0.9950.

The criterion was declared before the run: ρ above ~0.98 and little movement in
the top 20 means the weights are not buying ordering. Met.

**The two agents that leave the top 20 are the only non-cosmetic effect.** If
allocation reads the top 20, that is a real difference — small, and now
measured instead of assumed.

Mean S_RAW rises from 26.13 to 31.51 because the components that were
down-weighted (`vol` at 0.05) score higher on this population than those that
were up-weighted. That is a level shift, not a reordering, and it moves band
assignment: on this fresh-state run, PROMISING goes from 35 to 40 of 302.

## What this does not claim

That 1/N predicts better. The simulation measures rank agreement on one
population, and that population is outcome-selected — the 500 addresses are
the largest dollar winners and losers of a window. If two rules order the same
here, the choice between them is simplicity and honesty, not performance.
Which rule predicts better is Phase 2's question and needs the forward window.

The band rows of the simulation are **not** evidence about band migration in
production: every agent is scored from a fresh state, so `SISTEMA ≤ ~385` by
construction and VERIFIED is unreachable in every variant. Band effects are
the re-score's to measure.

## Consequence to publish at the same moment

Every level-based number changes: band, `isEligible`, the fee. The counts
produced by the calibrated weights become historical, and every published
count must name the version that produced it.

**Measured effect:** (pending the deliberate re-score)

# Spec change v5.3.0 — D5 and D6, with the API

Declared 2026-10-09. Applies the two items of Amendment v5.0.2 that were left
behind when D1–D3 and D10 landed. Changes published score values.

## D6 — the PSR's T was the number of days

The scorer called `compute_dsr(sharpe, n_obs=n_daily, …)`, and `n_daily` is the
count of distinct trading days (`out["n_daily"] = max(len(set(dates)), 2)` in
`enrich_metrics_from_trades`). But the `sharpe` passed in is `sharpe_r`, the
Sharpe of per-trade R-multiples. The `T` in

    sigma_sr0 = sqrt( (1 − skew·SR + ((kurt−1)/4)·SR²) / (T − 1) )

is the number of observations in the series that produced that Sharpe. Days are
not that series. Amendment v5.0.2 records the ratio between the two as 5.83×.

`n_obs` is now `n_trades`. The line computing `n_daily` is removed, because
nothing else in the scorer used it; `enrich_metrics_from_trades` still produces
`metrics["n_daily"]` as collector metadata.

**Direction of the effect, and it is upward.** A smaller `T` makes `sigma_sr0`
larger, the z-score smaller, and the PSR closer to 0.5. For an agent with
positive Sharpe the PSR was *understated*, so correcting it raises `psr`, raises
`s_sharpe_dsr`, and raises `S_RAW`. Measured on the acceptance test's synthetic
agent at Sharpe 0.08: 0.5756 before, 0.7685 after, with T going from 7 to 90.

That runs opposite to the other two changes of the day: D11 and the EMA reset at
the version boundary both push scores down. The net per agent is not predictable
from the signs and is the re-score's to measure.

## D5 — the field named `dsr` held a PSR

`compute_dsr` applies the multiple-testing haircut only when `n_trials > 1`
(`z = z − sqrt(2·ln(n_trials))`), `n_trials` defaults to 1, and nothing in the
pipeline passes it. So the served value was always a Probabilistic Sharpe Ratio
under a name claiming a Deflated one — a correction asserted and not made.

The result field is now `psr`, beside `psr_n_obs` and `psr_n_trials`. Those two
exist because the wrong denominator was invisible: a reader could not tell, from
the output, what `T` had been used. Now they can.

The weight key stays `W["sharpe_dsr"]` and the component stays `s_sharpe`.
Renaming those changes published field names that `facts.py` and the API both
carry, which is naming debt worth paying separately rather than inside this
change.

## The API, in the same patch

`scores_api.py` hid the field from `detail` with
`{k: v for k, v in p.items() if k != "dsr"}`, precisely because the value was
wrong. With the value corrected and the name honest, the reason to hide it is
gone: the filter is removed and `detail` carries the whole payload.

Renaming in the scorer alone would have re-exposed the field by accident,
because the filter matches the old literal. That is why the two files move
together, and why the patch writes both or neither.

## Acceptance test

`test_d5_d6_psr.py`, nine checks. D6 is tested twice on purpose:

- **by invariance** — `psr` must not change when `metrics["n_daily"]` goes from
  3 to 300. This does not depend on having read the formula correctly.
- **by recomputation** — `psr` must equal the published formula recomputed with
  `T = n_trades`, at 30, 90 and 400 trades. Stronger, but worth exactly what the
  reading of the formula is worth, which is why it does not stand alone.

The recomputation uses the *enriched* metrics, not the declared ones, because
`enrich_metrics_from_trades` overwrites `skew` and `kurt` from the trades; using
the declared values would have produced a false failure. A ninth check requires
the three `T` cases to differ by more than 0.05, so a saturated PSR cannot let
the recomputation pass trivially — the failure mode that `test_saturation.py`
case B already declares about itself.

Measured before the patch: 8 of 9 failing, with the multiple-testing guard
passing. After: 9 of 9.

## `test_saturation.py` will change

It must. The composite multiplies by this number, and `sharpe_dsr` carries
weight 0.14. A saturation run that produced identical output before and after
would mean D6 had not been applied.

## What this does not claim

That `sharpe_r` is the right Sharpe for the composite, or that `CAP_SHARPE` is
calibrated against it. Only that `T` must match the series that produced the
Sharpe.

`T` is taken as `metrics["trades"]`, the collector's count. If a collector ever
computes `sharpe_r` over a filtered subset of trades while still reporting the
unfiltered count, `T` and the series diverge again — in the same way, for the
same reason, and invisibly. `psr_n_obs` is in the output so that divergence is
at least auditable.

**Measured effect:** (pending the deliberate re-score)

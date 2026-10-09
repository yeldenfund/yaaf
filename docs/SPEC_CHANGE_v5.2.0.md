# Spec change v5.2.0 — D11: the scorer stops accumulating `total_trades`

Declared 2026-10-09. Supersedes nothing; adds to Amendment v5.0.2 and spec
change v5.1.0.

## What was measured

Before the change, in production:

| | |
|---|---|
| `yaaf_state` rows | 397 |
| `SUM(total_trades)` | 3,671,818 |
| `MAX(total_trades)` | 72,545 |
| `AVG(total_trades)` | 9,249 |
| payload files read | 500 |
| trades declared in those payloads | 43,984 |
| **ratio** | **83.5×** |

`CF = min(√(trades / CF_N_STAR), 1)` with `CF_N_STAR = 250` saturates at 250
trades. At a mean of 9,249, **CF was 1.0 for essentially the whole
population.** One of the three factors of `SISTEMA = EMA × CF × SF` has never
discounted anyone. The public page's claim of "full confidence at 250 trades"
described a factor that was 1 in every case.

## Why it happened

Two decisions, each defensible alone:

1. The scorer accumulated: `cum_trades = int(state.get("total_trades", 0)) + n_trades`.
2. The pipeline re-scored every payload on every round — `run_observatory.sh`
   step 4, *"scoring completo (sempre)"*, with 667 scoring timestamps on
   record.

Accumulation is correct when each call delivers *new* trades. These payloads
are snapshots: `feed_yaaf_hl_fast.py` collects only the addresses that have no
payload yet, and each file holds that address's whole history. So every round
added the same history again. 83.5× is approximately the number of rounds that
passed over unchanged files.

## The change

```python
# before
cum_trades = int(state.get("total_trades", 0)) + n_trades
# after
cum_trades = n_trades
```

The scorer receives an *observation*, not a delta, and it has no way to tell
which it was given. Summing inside the scorer silently assumed deltas.
Accumulating, where that is the right semantics, belongs to whoever reads the
files and knows whether they are snapshots or deltas.

`total_trades` stays in `yaaf_state`: it remains the record of what was
observed in the last scoring of that address. It is no longer a running sum.

## Acceptance test, written before the patch

`test_d11_idempotence.py`. It must fail on the pre-D11 code and pass after.
Measured on the pre-D11 source: `total_trades` 65 → 130 on the second call of
the same observation, `cf` 0.509902 → 0.721110. After: both constant.

The test states what it does not cover. The EMA and `round_history` still
advance on every call, and that is correct for D11: the EMA is the smoother,
and not re-scoring an unchanged observation is the pipeline's job, not the
scorer's. A test demanding EMA idempotence here would be charging D11 with
something D11 does not deliver.

## Declared and not fixed here: P1

`round_history` receives a copy of the same `s_raw` on every re-scoring of an
unchanged payload. Measured 2026-10-09: of 397 rows, 391 hold two or more
entries, and **379 of those 391 hold the same value repeated** — mean window
length 6.13. With every entry identical, `σ_s = 0`, so the dispersion term
`(1 − σ_s/25)⁺` is 1.0 and `SF` reduces to its level term.

So before this change **two of the three factors of SISTEMA were inert for
roughly 95% of the population**, by the same root cause: a snapshot scored
repeatedly. D11 fixes the trade count. The window needs the pipeline to stop
re-scoring unchanged payloads, which requires the payload's hash in the state
— a schema column and a change to the emit. That is P1, and it must land
before the cron runs again, or the window refills with duplicates.

Until P1 lands, `SF`'s dispersion term should be read as unmeasured rather than
as evidence of consistency.

## Consequence to publish at the same moment, not later

CF starts discounting again, so every agent under 250 observed trades loses
score it was never entitled to. This stacks with the EMA reset at the version
boundary (`EMA_INITIAL = 300`, `round_history` cleared), which the re-score
also carries because the S_RAW scale changed between 5.0.0 (9 components,
W_SUM 0.96, attainable ceiling 88.0208) and 5.1.0 (8 components, W_SUM 0.81,
ceiling 100): smoothing across that boundary averages incommensurable numbers.

Both effects push down. Every published count must name the version that
produced it, and the counts produced by 5.0.0 become historical rather than
wrong — they were the output of the specification in force at the time.

**Measured effect:** (pending the deliberate re-score)

## Open, and not to be resolved by assumption

The payload set declares 43,984 trades; `MEASUREMENT_INPUTS.md` records 39,945
for the same 500 payloads. The difference is 4,039. Candidates: `metrics.trades`
(the collector's count) against `len(trades)` (what the test counted), or a
re-collection after the IC run. 39,945 is a published figure, so this is
resolved by checking, not by choosing.

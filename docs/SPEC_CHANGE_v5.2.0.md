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

> **Read the correction at the end of this file before using any figure above.**
> The effect sizes in the sections above were overstated and are retracted
> there.

## Open, and not to be resolved by assumption

The payload set declares 43,984 trades; `MEASUREMENT_INPUTS.md` records 39,945
for the same 500 payloads. The difference is 4,039. Candidates: `metrics.trades`
(the collector's count) against `len(trades)` (what the test counted), or a
re-collection after the IC run. 39,945 is a published figure, so this is
resolved by checking, not by choosing.

---

## Correction, 2026-10-09, after the first version of this document

The first version of this file, committed in `8e818f4`, overstated the effect
of the defect it describes. Four of its claims do not survive measurement. They
are retracted here rather than edited away, because the history of the
corrections is part of the evidence.

### What was actually measured

**GMX**, `yaaf_state.total_trades` against the payload's own `metrics.trades`,
58 addresses paired:

| | |
|---|---|
| median ratio | 1.13 |
| min | 0.42 |
| max | 2.00 |

One accumulation, two at most — consistent with 2.0 score rows per GMX address.

**Hyperliquid**, `total_trades` against `COUNT(*)` of that address's rows in
`fills`, 309 addresses paired. Trades are formed by grouping fills, so
`trades <= fills` always, and any ratio above 1 is accumulation with no
interpretation needed. No code path deletes from `fills` (checked), so the
bound holds.

| | |
|---|---|
| addresses with ratio > 1 | **259 of 309** |
| median ratio | 4.56 |
| p90 | 11.07 |
| max | 19.36 |

**The effect on CF**, 337 addresses paired with their fill counts:

| | |
|---|---|
| `total_trades >= 250`, so CF = 1.0 today | 298 |
| of those, holding fewer than 250 fills — CF = 1.0 **only** because of the accumulation | **12** |
| holding 250 or more fills | 322 |

### Retracted

1. **"ratio 83.5x".** Invalid. It divided the trades declared in the 500 GMX
   payloads (43,984) by `SUM(total_trades)` over *both* populations
   (3,671,818). The HL payloads carry no `metrics.trades` at all — `score_yaaf`
   computes metrics from `fills` in the database — so the two sides of that
   ratio are different populations. The figure also appears in the commit
   message of `216bcb2`, which cannot be edited; this paragraph is its
   retraction.

2. **"CF was 1.0 for essentially the whole population"** and **"one of the
   three factors of SISTEMA has never discounted anyone".** Wrong. CF is 1.0
   for 298 of 337, and 286 of those agents are above the saturation point on
   their own fill count. The accumulation inflated numbers that were already
   saturated. Saturated is saturated. The measured damage to CF is 12
   addresses of 337, about 3.6%.

3. **"two of the three factors of SISTEMA were inert for roughly 95% of the
   population".** Unsupported. The 379-of-391 identical `round_history`
   windows are consistent with a population whose metrics did not change
   between refreshes: `refresh_all.sh` re-collects every address daily
   (`feed_yaaf_hl_fast.py wallets_full.txt`, "reprocessa TODOS os enderecos"),
   so an unchanged `s_raw` can be a correct observation of an agent that did
   not trade. In that case `sigma_s = 0` and the dispersion term being 1.0 is
   the formula working, not failing.

4. **"the pipeline never refreshes payload"**, stated in the discussion that
   produced this document though not in the document itself. Wrong in the
   other direction: `refresh_all.sh` reprocesses all addresses daily, and the
   spread of payload mtimes (325 on 10-06, 131 on 10-07, 124 on 10-08, 143 on
   10-09) reflects partial completion per run, not one-time collection.

### What survives

D11 is correct, and by code-level proof rather than production statistics: the
acceptance test shows `total_trades` 65 -> 130 and `cf` 0.509902 -> 0.721110 on
a second call with the same observation. A scorer should not maintain a sum it
cannot validate, whatever the magnitude of the error that sum accumulated.

The defect is one of data integrity in `yaaf_state`, not of the published
score. Zeroing `total_trades` in the re-score is still right, because the
stored value is wrong — but the expected effect on published scores is small,
not severe. The EMA reset at the version boundary remains the large effect of
the re-score; the CF correction is marginal.

### P1, downgraded from fix to open question

The earlier framing — that the pipeline fakes observations by re-scoring
unchanged payloads — rests on a question this project has not decided and
which is not a bug: **does an unchanged observation count as an
observation?** For an EMA meant to express maturity over time, an agent that
stays good for months arguably should mature. For a scorer whose input is
trades, no new trades is no new information. Both readings are defensible,
both move SISTEMA for the whole population, and the choice belongs in the
specification, declared, with its consequence computed first.

What is a defect, narrowly: `emit_yaaf_final.py` scores every payload on every
run, including addresses that the collection step did not reach that day. For
that subset, and only for it, the scoring adds an observation that is not new.
Sizing that subset is a prerequisite to deciding P1, not a consequence of it.

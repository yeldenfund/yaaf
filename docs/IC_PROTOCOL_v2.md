# IC Measurement Protocol v2

**Status:** frozen before the measurement
**Date:** 2026-10-08
**Supersedes:** `IC_PROTOCOL.md` (v1) for the corrected universe
**Scope:** YAAF on GMX V2

---

## Why there is a v2

v1 was frozen correctly and executed correctly. Its result —
ρ = 0.6577, 95% CI [0.3955, 0.8207], n = 31 — stands as a measurement of the 31
agents it covered, and every validity check it recorded still holds.

What v1 could not know is that its universe was an accident. The collector
lowercased each address before querying an index that stores them EIP-55
checksummed, so 404 of 500 discovered addresses returned zero trades, silently
(`AMENDMENT_v5.0.2.md`, D9). The 100 agents v1 measured were not selected by any
criterion; they were the subset whose source file happened to carry checksummed
case.

Fixing that did not only widen the universe. **It recovered three months of
history that v1 never saw:**

| | v1 | corrected |
|---|---|---|
| Collection window | ~31 days | **89 days** (2026-07-10 → 2026-10-08) |
| T1 | 17 days | **61 days** |
| T2 | 12 days | **28 days** |
| Distinct months in T1, median per agent | 1 | **3** |
| Payloads with trades | 100 | **504** |
| Agents passing both filters | 31 | **124** |

v1's conclusion that the agents were simply young was wrong, and wrong for the
same reason as everything else the defect touched.

---

## What carries over from v1, unchanged

These were not contaminated by D9 and are restated here rather than revised:

- **Primary horizon: the sum of `r_multiple` over T2.** Secondary is the mean,
  tertiary the sum of `pnl`. All three are computed and reported on every run.
- **Filters: ≥30 closed trades in T1, ≥10 in T2.** The T1 floor follows from
  Formal Specification §2.2 and is not a measurement parameter.
- **Statistic:** Spearman with average ranks for ties; p and the 95% interval
  both from the Fisher transform, so they agree at the boundary.
- **Metric construction:** the script imports `compute_yaf_metrics` from the
  collector and the scorer itself. It does not rebuild metrics.
- **Reproduction guard:** each S_RAW is recomputed and compared against the
  stored run; a mismatch aborts rather than reporting.

---

## The universe, declared

| | |
|---|---|
| Discovery | `discover_gmx_v2.py` |
| Wallet file | `wallets_gmx.txt`, 500 addresses, all EIP-55 checksummed |
| Pre-filter | `trades >= 5` in the discovery metadata — **this existed in v1 and was undocumented** |
| Collector | `feed_yaaf_gmx.py` with the D9 patch (`to_checksum_address` on read) |
| Window requested | 90 days |
| Payloads | `yaaf_payloads_gmx/*.json`, files prefixed `_` excluded |

Naming all four stages is the point. v1 documented only the payloads and the
30-trade floor, which is how a defect in stage one went unrecorded.

### Required before the measurement: uniform re-collection

The 100 original payloads were collected one day before the 404 new ones, so T2
is longer for the newer agents. The split rule exists to give every agent a
common forward period, and an uneven collection end defeats it.

Move `yaaf_payloads_gmx/` aside, re-run the collector over the whole wallet file
in one pass, verify the count, and only then discard the copy. **No measurement
runs on a mixed-vintage payload set.**

---

## Split

The global median of `exit_time` over all trades of all agents, recomputed on
this universe. T1 is everything before that instant, T2 everything from it on.

**v1's cut date is deliberately not carried forward.** An earlier draft of this
protocol proposed fixing it at v1's 2026-09-25T03:00:16Z to isolate the change in
universe. That was withdrawn: v1's cut was the median of the biased sample, so
reusing it would import the bias, and against the corrected data it splits 77/13
days rather than 61/28. Comparability between v1 and v2 is lost either way,
because the universe changed fourfold. A clean measurement is worth more than a
contaminated one that looks comparable.

---

## Survivorship

The tenth percentile of last-trade dates is 2026-09-22: about one agent in ten
stopped trading before the window closed. Agents that stop are **kept** if they
satisfy both trade floors. Excluding them would measure only the survivors and
inflate the correlation, which is the classic survivorship bias in exactly the
setting it was named for.

Agents that stop and therefore fail the ≥10 floor in T2 drop out by the ordinary
filter, and that count is reported alongside the others.

---

## Scorer version

The measurement runs on the scorer **as published**, `5.0.0-FORMAL` at the commit
recorded at run time, before Amendment v5.0.2 is applied.

The reason is that this measures what an allocator actually receives today. The
amendment's repairs change the score for every agent, so a post-amendment
measurement is a different object and gets its own protocol version. Measuring
both on the same data and publishing the better one is the trial-shopping this
document exists to prevent.

---

## Pre-registered test: Component 8 (Stability², w = 0.09)

v1 measured its IC at −0.0218, p_BHY = 1.0000, and left it untouched under a
decision rule fixed before that measurement: act only on a component that is
*significantly negative* after correction, because at n = 31 "not significant"
means no power. That rule stands.

v1 also recorded that the Formal Specification's alternative,
`(1/(1+σ_mSharpe))²`, was **not computable**: it needs monthly Sharpe dispersion
and no agent had two months. On the corrected universe **117 of 124 agents
(94.4%) have two months or more and 87 (70.2%) have three**, so that obstacle is
gone.

It is the only obstacle that is gone. Both formulas remain blind to sign — each
measures consistency, neither measures quality, and an agent that loses reliably
scores well on either. Computability does not make a formula correct.

**Declared now, before the run:** both forms are computed and both ICs reported.
A change to component 8 is justified only if the specification's form shows a
significantly better IC after BHY correction. Equal or worse, it stays as built
and the divergence is recorded as a permanent known limitation. The 7 agents with
a single month take `σ_mSharpe` as undefined and are reported separately; no
fallback value is invented for them.

---

## Reporting

ρ, p, 95% CI and n for all three horizons; the count dropped by each filter; the
reproduction guard's maximum deviation; leave-one-out and winsorisation
sensitivity; the component-level IC table with BH and BHY; effective
dimensionality. Written to `docs/evidence/ic_test_gmx_v2_result.json` and
committed with the scripts.

---

## Non-negotiables

The protocol is frozen before the measurement. No filter is adjusted after seeing
a result. No horizon is selected after seeing a result. The cut date is not
revisited. **This run is the canonical figure for the corrected universe, declared
canonical before it is executed**, and v1's ρ = 0.6577 remains on record as the
measurement of its own, accidental, universe.

If the result comes out weaker than v1, it is published weaker. A larger, honestly
constructed sample that disagrees with a smaller accidental one is information,
not a setback.

---

## Result — 2026-10-08, canonical

Run under this protocol, on the uniformly re-collected universe, declared canonical
before execution.

| | |
|---|---|
| Addresses declared | 500 (`wallets_gmx.txt`) |
| Payloads in universe | 500 · 39,945 trades |
| Window | 2026-07-10 → 2026-10-08 |
| Cut (global median) | 2026-09-04T12:57:22Z · T1 56.3 d · T2 33.7 d |
| Dropped: <30 trades in T1 | 340 |
| Dropped: <10 trades in T2 | 8 |
| **Agents measured** | **152** |

| Horizon | ρ | p | 95% CI |
|---|---|---|---|
| **Primary — sum of R over T2** | **+0.2540** | 0.0015 | **[0.0988, 0.3971]** |
| Secondary — mean R over T2 | +0.2629 | 0.0010 | [0.1083, 0.4052] |
| Tertiary — sum of PnL over T2 | +0.0092 | 0.911 | [−0.1503, 0.1681] |

**Sensitivity:** leave-one-out moves ρ by at most 0.0217; winsorising at p05/p95
moves it 0.0003. At n = 152 the estimate is stable.

**Against v1.** v1 reported 0.6577 [0.3955, 0.8207] on 31 agents. The intervals
barely touch — v1's estimate sits at the extreme edge of what the corrected data
supports. v1 was executed correctly; its universe was not. **The canonical figure
for YAAF on GMX V2 is 0.2540.**

### The uniform-collection precondition earned its place

A first run was executed on payloads of two vintages, two days apart, and
discarded under this protocol's own rule. It returned ρ = 0.2004 on 124 agents —
and Stability² at **−0.2027**, close enough to the threshold to invite action.
The uniform run puts that same component at **−0.0606**, p_BHY = 1.0000.

A two-day difference in collection moved one component's IC by 0.14. Had the
first run been accepted, the record would now contain a near-significant negative
finding on a component that sits at zero. The precondition was written before any
result existed, for exactly this reason, and it turned out to matter empirically
rather than only in principle.

### Component 8 — the pre-registered test resolved

| | ρ | p | n |
|---|---|---|---|
| As implemented (fraction of R within ±2σ) | −0.0956 | 0.25 | 146 |
| Formal Specification ((1/(1+σ_mSharpe))²) | −0.0159 | 0.85 | 146 |
| Correlation between the two forms | +0.0366 | | |

Neither is significant and the specification's form is not better, so under the
rule fixed before the run **the component stays as built** and the divergence
becomes a permanent declared limitation. Six agents lack two usable months and
were excluded from this comparison rather than given an invented value.

The two forms correlate at +0.04. They were never substitutes for one another.

### Components

Eight of eleven survive BHY (c(13) = 3.1801) as positive, one more than v1
produced, because n = 152 carries more power: win rate +0.4066, PF percentile
+0.3774, Sharpe×PSR +0.2940, PSR alone +0.2650, average R and expectancy +0.2501,
inverse volatility +0.2482, profit factor +0.2277, Sortino +0.2157. The
max-drawdown penalty reads −0.3931, which is the penalty working.

Stability² (−0.0606), Smoothness² (+0.1085) and the CVaR penalty (−0.0952) are
inconclusive. Market context remains a constant 50.

Effective dimensionality: ten components carry variance, five factors reach 90%,
the first explains 56.6%. Average R and expectancy still correlate +1.0000.

### Still open after this run

The clone check and the `r_multiple` integrity check were run on v1's universe and
have not been repeated on this one. Neither bears on the headline — both were
clean, and the sensitivity figures here are far tighter than v1's — but they are
not yet evidence about these 152 agents.

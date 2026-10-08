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
---

## Addendum — 2026-10-08, after the result

**Status:** correction to a declaration in this document, written after the
measurement it concerns. It does not alter any text above; the text above is the
record of what was declared, including what was declared wrongly.

### The declared universe was wrong

The section "The universe, declared" records the pre-filter as
`trades >= 5` in the discovery metadata. That is the default of
`discover_gmx_v2.py`, which did not produce the list. The generator was
`discover_gmx.py`, and its rule is not a trade floor:

> aggregate every GMX trade action over a rolling window ending at the run
> instant; keep accounts with `n_trades >= min_trades` (default 10 — the minimum
> among the 500 is exactly 10); rank by **aggregate dollar PnL**; take the top
> `max_addrs/2` and the bottom `max_addrs/2`.

The 500 are the extremes of dollar PnL: 250 largest winners and 250 largest
losers over a window ending 2026-10-06. The `--days` actually passed was not
recorded. `--max-addrs 500` must have been, since the default is 200.

Line order in `wallets_gmx.txt` preserves the construction and the halves do not
overlap: the lowest PnL in the top half is +10.08, the highest in the bottom half
is −291.63.

### The overlap with the forward window is not conditional

The discovery window ends at the run instant, 2026-10-06. T2 runs
2026-09-04T12:57:22Z → 2026-10-08. Any window longer than two days ends inside
T2; under the 30-day default the discovery window lies entirely inside T2. The
unrecorded `--days` changes how much of the selection signal comes from T1, not
whether the universe was selected using information from the period the primary
horizon measures.

This document's claim that the universe was "declared" is therefore true of the
file and false of the rule. Stage one of the four-stage provenance chain was
named but mis-stated, which is the same class of failure as D9 one stage further
in.

### What was measured in response

Three checks, `selection_check.py` and `selection_check2.py`, both guarded: the
pooled ρ is recomputed and must reproduce the published figure before anything
else is reported.

**The figure reproduces exactly.** Primary +0.2540 and secondary +0.2629, both to
four places, difference 0.0000 against this document's table; 152 of 152 measured
agents join to the declared wallet file.

**Three candidate explanations were tested and all three failed.**

| Hypothesis | Prediction | Measured | Verdict |
|---|---|---|---|
| Extreme-groups inflation (selection truncates the outcome, raising ρ) | selection variable related to the predictor | ρ(discovery PnL, S_RAW) = **+0.1146**, p = 0.16 | fails — selection is ~orthogonal to the predictor, which deflates rather than inflates |
| Range restriction in the predictor among winners | less S_RAW spread in the top half | IQR **31.14** top vs **21.95** bottom; sd 20.65 vs 15.88 | fails, and reversed |
| Size collider (conditioning on dollar PnL couples size to R) | ρ collapses when size is controlled | partial **+0.4644** vs +0.4607 raw in the bottom half; size terciles +0.4127 / +0.4052 / +0.6032 | fails — survives the control and every tercile |

### What the figure actually is

ρ = 0.2540 is a mixture of two populations that behave differently:

| | n | ρ(S_RAW, Σ R over T2) | p |
|---|---|---|---|
| pooled | 152 | **+0.2540** | 0.0016 |
| top half — selected for winning | 59 | **+0.0254** | 0.85 |
| bottom half — selected for losing | 93 | **+0.4607** | <0.0001 |

The pooled figure is carried by the losing half, where it is stronger than
published. In the winning half the score carries no detectable forward
information. Controlling size moves neither (+0.1582 and +0.4644).

**The composition has a visible mechanism.** Among the 93 in the bottom half, 61
have `s_sharpe`, `s_sortino`, `s_avg_r` and `s_expectancy` all at zero and 67 have
`s_pf` at zero. `s_winrate` and `s_stability` are at zero for none. For two
thirds of that group S_RAW is therefore a function of consistency components
only, the return-magnitude components being at the floor — and that is the group
where the signal is.

Two defects of Amendment v5.0.2 are confirmed on this population rather than on a
worked example: `s_smoothness` is zero for **151 of 152** agents (D1), and the
zero counts of `s_avg_r` and `s_expectancy` are identical in both halves —
26/59 and 61/93 — which is the ρ = +1.0000 duplication of D2 visible in a count.

### The label changes

This document declares ρ = 0.2540 "the canonical figure for YAAF on GMX V2".
That phrasing asserts a population. It is withdrawn and replaced:

> **ρ = 0.2540 is the pooled rank correlation on a universe constructed from the
> extremes of dollar PnL over a window that ends inside the forward period. It is
> +0.0254 among agents selected for winning and +0.4607 among agents selected for
> losing. It is not an estimate for the population of GMX agents, and no estimate
> for that population has been produced.**

The figure is not retired the way 0.4362 and 0.6577 were. It reproduces exactly,
its sensitivity is unchanged, and the three mechanisms by which selection could
have manufactured it were each tested and each failed. What was wrong was the
claim attached to it.

### Also downgraded

The near-zero tertiary result — ρ = 0.0092 on dollar PnL — is recorded above as a
finding, *that dollar PnL is not predicted*. In a sample built from the extremes
of dollar PnL, where the selection variable correlates +0.8430 with that same
horizon, near-zero is partly what the construction produces. The claim becomes
inconclusive pending an outcome-blind universe.

### Consequence for the gate measurement

The 500 cannot be used to measure the gate. Half were selected for being the
largest dollar losers in a window inside the forward period, and the gate's
outcome is ruin; a gate test on this universe would measure its own construction.
A gate measurement requires a universe whose selection rule uses only information
available before T1 ends, with a fixed `until_ts` at the T1 boundary and no PnL
ordering of any kind. `discover_gmx.py` cannot be used as written.

### Pre-registration status of this document

The protocol text was first committed 2026-10-08T14:06:57Z, about nine hours
after the 05:00:08Z run; host file mtimes are copy times. This document's claim
to have been frozen before the measurement is **not verifiable by a third party**
and is not asserted as such. One narrower claim survives and is the only one
made: the decision rules that could have been chosen after seeing a result — the
trade floors, the `stability_spec` convention, the Yekutieli constant, the
universe filter — were present in `ic_test_gmx_v2.py`, whose working-tree copy
carries mtime 04:02Z, before the run. That is consistent with pre-registration
and is not proof of it, because mtimes are forgeable.

### Open

Whether the +0.4607 in the losing half is the composite or is win rate wearing
its name. The published component table puts win rate at +0.4066 against the
composite's +0.2540; if S_RAW in that group is approximately win rate, the
composite adds nothing there. Measured by `selection_check3.py`, which also tests
whether the winning half reverts and whether the bottom-half signal survives as a
classification of Σ R > 0 — the form the gate measurement takes.

### Addendum, continued — the open item closed

Measured by `selection_check3.py` on the same table, same join (152 of 152).

#### Component ICs are not comparable across the pooled sample

| Component | top half (n=59) | bottom half (n=93) |
|---|---|---|
| **S_RAW (composite)** | **+0.0254** | **+0.4607** |
| `s_vol` (inverse volatility, w = 0.05) | −0.0854 | **+0.5624** |
| `s_sharpe` | +0.0174 | +0.2997 |
| `s_sortino` | −0.0778 | +0.2741 |
| `s_winrate` | **+0.2666** | +0.2577 |
| `s_avg_r` = `s_expectancy` | +0.0474 | +0.2532 |
| `s_pf_pct` | +0.1652 | +0.2461 |
| `s_pf` | +0.0710 | +0.1940 |
| `s_stability` | +0.0813 | −0.1532 |
| `s_smoothness`, `s_mc` | constant | constant |

**This withdraws a claim made earlier in this work.** The pooled component table
reports win rate at +0.4066 against the composite's +0.2540, and that was read as
the composite being out-predicted by one of its own parts. Within groups it is
not: win rate is +0.2666 and +0.2577 — stable across both halves — while the
composite moves from +0.03 to +0.46. Pooling adds between-group variance to
every quantity that differs systematically between the halves, and win rate does
differ; the composite is the one quantity that does not, because
ρ(discovery PnL, S_RAW) = +0.1146. **The pooled comparison therefore compares a
component that the selection inflates against a composite that it does not.** It
is not evidence about aggregation either way, and must not be cited as such.

What survives is narrower and still unflattering: in the half where the model
carries signal, **inverse volatility alone reaches +0.5624 against the
composite's +0.4607** — and it carries a weight of 0.05, the second smallest in
the model. The composite also barely tracks it: within that half,
ρ(S_RAW, `s_vol`) = +0.2503, against +0.8129 for `s_pf_pct` and +0.7896 for
`s_sharpe`. **The model under-weights its best predictor in the regime where it
works.** That is a calibration finding with arithmetic behind it and belongs with
the threshold re-derivation, not with Amendment v5.0.2.

`s_stability` returns −0.1532 (p = 0.14) in the half where every other component
is positive. It is the second negative point estimate for that component. The
pre-registered rule — act only on a component significantly negative after BHY
correction — is unchanged and it still is not met. Recorded, not acted on.

`s_smoothness` and `s_mc` are constant within both halves, so no IC is defined
for either. D1 and D3 of Amendment v5.0.2 are confirmed on the population.

An earlier reading in this work, that for two thirds of the bottom half S_RAW
reduces to the consistency components because the magnitude components sit at the
floor, is wrong. The floor creates ties, not absence: ρ(S_RAW, `s_sharpe`) is
+0.7896 in that half, driven by the 32 agents whose Sharpe is live. The ranking
is dominated by whether an agent has a live magnitude component at all.

#### The selection variable relates to the outcome between groups, not within

| | ρ(discovery PnL, Σ R over T2) |
|---|---|
| pooled | **+0.5830** |
| within the top half | +0.0441 (p = 0.74) |
| within the bottom half | +0.2066 (p = 0.047) |

The pooled +0.58 is almost entirely the group split. Past dollar performance
carries no information about forward R among the winners and very little among
the losers.

#### The accountability form of the question gives the strongest result in this work

The same data, asked as a classification — does S_RAW separate agents whose Σ R
over T2 is positive — rather than as a correlation:

| | n | Σ R > 0 | S_RAW median, positive | S_RAW median, negative | AUC | p |
|---|---|---|---|---|---|---|
| top half | 59 | 44 | 20.95 | 17.97 | 0.552 | 0.56 |
| **bottom half** | **93** | **12** | **44.08** | **14.24** | **0.827** | **0.0003** |
| pooled | 152 | 56 | 23.81 | 14.31 | 0.632 | 0.0068 |

Rate of Σ R > 0 above and below a threshold on S_RAW:

| Threshold | bottom half | pooled |
|---|---|---|
| 20 | 25.0% vs 5.3% — **+19.7 pp** | 47.7% vs 28.7% — +19.0 pp |
| 30 | 28.6% vs 6.2% — **+22.4 pp** | 48.0% vs 31.4% — +16.6 pp |
| 40 | 44.4% vs 5.3% — **+39.1 pp** | 60.6% vs 30.3% — +30.4 pp |

Four things must be said with it, or the number is misreported.

1. **The universe is outcome-selected.** None of this is a population estimate,
   and the bottom half's AUC is computed on agents chosen for extreme dollar loss
   in a window overlapping the forward period.
2. **The three thresholds were not pre-registered.** They were written as round
   numbers before this output existed, which is not the same as being declared in
   a protocol. The monotone rise is reassuring and the AUC — which uses no
   threshold — is the statistic to cite. The cut table is descriptive.
3. **The cells are small.** 44.4% above 40 in the bottom half is 8 of 18 agents.
4. **These are cuts on S_RAW, not on the gate.** The gate is defined on SISTEMA,
   which is `EMA × CF × SF`; S_RAW 40 corresponds to SISTEMA 400 only in the
   limit of a converged EMA with CF and SF at 1. The correspondence is
   approximate and the gate measurement must use SISTEMA.

With those four stated, the result stands as the first accountability-shaped
measurement in this work: asked as a classification rather than as a correlation,
the score separates — AUC 0.827 where it has signal, 0.632 pooled — and it does so
on the question the protocol is actually about. The form of the Phase 2
measurement is validated. Its universe is not, and must be rebuilt
outcome-blind before any figure from it is published.

# IC Measurement Protocol v1

**Status:** frozen before the first measurement
**Date:** 2026-10-07
**Scope:** YAAF v5.0 on GMX V2

---

## Purpose

Measure the information coefficient between the YAAF score computed on a
historical window (T1) and the agent's realised performance in the subsequent
window (T2).

This is the first IC measurement of YAAF with recorded provenance. The figure
ρ=0.4362 that appeared in Whitepaper v16 has no surviving script, dataset or
log; the scorer version it used is unknown, and it is not reproducible from any
file in this repository. It is retired and must not be cited.

## Scorer

| | |
|---|---|
| File | `/root/yaaf/scorer/yaaf_score_v5_formal.py` |
| Version string | `5.0.0-FORMAL` |
| Commit | `b579e56a23f266dc18fa917c14c8e1278f863b54` |
| Weights | normalised by their sum of 0.96 (Amendment v5.0.1) |

The copy under `/root/aiagentregistry-observatory/` is a symlink to the file
above. Any change to the scorer invalidates this measurement and requires a new
protocol version.

## Metric construction

The script does **not** build metrics of its own. It imports
`compute_yaf_metrics` from `feed_yaaf_gmx.py` — the same function the collector
uses to build the payloads — and `enrich_metrics_from_trades` from the scorer.
`initial_balance` is 11000.0, identical to `emit_yaaf_gmx.py`.

The measurement therefore reflects the code path that produces published
scores, by construction rather than by coincidence.

## Data

- Source: `yaaf_payloads_gmx/*.json`, collected October 2026
- Each trade carries `exit_time`, `pnl`, `r_multiple`, `collateral`, `fees`,
  `is_liquidation`

## Universe filter

- At least 30 trades in T1
- At least 10 trades in T2

**The T1 threshold is not a measurement parameter.** It follows from Formal
Specification §2.2 — *"n ≥ 30 closed trades required. Otherwise S_RAW := 0"* —
and from `MIN_TRADES_SRAW = 30` in the scorer. Measuring IC over agents with
fewer than 30 trades would measure agents the scorer refuses to score in
production. It must not be relaxed to raise n.

## Split

All trades of all agents are pooled and the **global** median of `exit_time` is
taken. T1 is everything before that instant, T2 everything from it onward.

The median is global, not per agent. A per-agent median would give each agent
its own cut date, so one agent's "future" could precede another's "past", and
there would be no common forward period. A single cut date reproduces the
situation of an allocator deciding on one day.

Sample sizes per agent are therefore unequal. That is accepted: it is what
production would face.

## Horizons

All three are computed and reported on every run, regardless of outcome:

| | Target |
|---|---|
| **Primary** | sum of `r_multiple` over T2 |
| Secondary | mean `r_multiple` over T2 |
| Tertiary | sum of `pnl` over T2 |

The primary is scale-free because S_RAW is scale-free by construction (Formal
Spec §1: *"all performance metrics are R-multiples or dimensionless ratios"*).
Correlating a scale-free score against absolute PnL would partly measure
account size: agents trading larger balances produce larger PnL at equal skill.
Spearman does not remove this — rank correlation is invariant to monotone
transformations of a whole variable, not to heterogeneous normalisation across
units. On synthetic agents of identical skill and balances spanning three
orders of magnitude, IC against summed R was 0.90 while IC against absolute PnL
was 0.60, and PnL alone correlated 0.42 with balance.

PnL is retained as a tertiary so the comparison is on record rather than
discarded.

## Statistic

Spearman rank correlation with average ranks for ties. The p-value and the 95%
interval both come from the Fisher transform, so they are mutually consistent
at the boundary.

Reported: ρ, p, 95% CI, n, and the count of agents dropped by each filter.

## Known limitations

**Component 11 (Mc, weight 0.07) is inert.** It requires β, the correlation
between the agent's daily aggregated R and the daily returns of the underlying
market. `compute_yaf_metrics` does not produce `s_mc`, so the scorer falls back
to its neutral default of 50 for every agent. This is equally true in
production — the component is inert there as well, not only in this
measurement.

*Corrected 2026-10-07:* this paragraph originally put effective coverage at 0.89
of the 0.96 weight, counting only Mc. Component 9 (Smoothness², weight 0.08) is
also identically zero for all 31 agents, so live weight is **0.81 of 0.96 —
15.6% of the score does not respond to the agent**, and S_RAW has a ceiling of
88.02 rather than 100. See `AMENDMENT_v5.0.2.md`, D1 and D4.

**Three components as built diverge from the Formal Specification.** The
measurement is faithful to production; production is not faithful to the spec:

| Component | Formal Spec | `compute_yaf_metrics` |
|---|---|---|
| 7 — Inv. Volatility | `max(1 − σ_d/2, 0)` with σ_d daily | per-trade R standard deviation |
| 8 — Stability² | `(1/(1+σ_mSharpe))²`, dispersion of monthly Sharpe | fraction of R within ±2σ |
| 9 — Smoothness² | `min(Calmar/4, 1)²` | `1 − std(diff(pnl))/mean(\|pnl\|)`; no Calmar |
| DD penalty | `MDD% × 0.20` | drawdown of the cumulative-R curve, in R units, not per cent |

These are not defects of this protocol and do not invalidate the measurement,
which reports what production computes. They are a separate code-to-
specification gap and should be resolved on their own terms, under their own
amendment.

## Reporting

Each run writes `docs/evidence/ic_test_gmx_result.json` containing the three
correlations, the cut date, the filter counts and the per-agent observations,
and is committed together with the script.

## Non-negotiables

The protocol is frozen before the first measurement. No filter is adjusted
after seeing a result. No horizon is selected after seeing a result. If the
primary comes out weak, it is published weak: a small, auditable number is an
asset, and an impressive one without provenance is a liability.

---

## First measurement — 2026-10-07

Run under this protocol, commit `b579e56` of `/root/yaaf`.

| | |
|---|---|
| Payloads collected | 100 |
| Cut date (global median `exit_time`) | 2026-09-25T03:00:16Z |
| Dropped: fewer than 30 trades in T1 | 69 |
| Dropped: fewer than 10 trades in T2 | 0 |
| **Agents measured** | **31** |

| Horizon | ρ | p | 95% CI |
|---|---|---|---|
| **Primary — sum of R over T2** | **+0.6577** | <0.0001 | **[0.3955, 0.8207]** |
| Secondary — mean R over T2 | +0.6532 | <0.0001 | [0.3889, 0.8182] |
| Tertiary — sum of PnL over T2 | +0.2173 | 0.2425 | [−0.1484, 0.5308] |

**The statement of the result, in full:**

> The YAAF score computed over ~18 days of trading ranks the following ~12 days
> at ρ = 0.6577, 95% CI [0.3955, 0.8207], n = 31.

The horizon belongs in the sentence, not in a footnote. T1 spans a median of
17.1 days (maximum 18.6); T2 runs from the cut to collection, about 12 days.
This is a realistic window for an allocator who rebalances weekly. It licenses
nothing about months or quarters, which is the horizon an institutional
allocator cares about, and it must never be quoted as "the score predicts future
performance" unqualified.

The reportable figure is the interval, not the point estimate: at n=31 the
score's rank correlation with forward risk-adjusted performance is somewhere
between 0.40 and 0.82.

**The tertiary confirms the pre-registered reasoning.** Against absolute PnL
the correlation is 0.22 and the interval contains zero. The scale
contamination the protocol predicted before the measurement is present and
large: the same score that ranks forward R-multiples at 0.66 ranks forward
dollars at 0.22, indistinguishable from chance. YAAF ranks skill, not
profitability. An allocator using it to predict returns in currency is using
it for something it does not do.

**Primary and secondary agree to within 0.005.** Summed R grows with trade
count; mean R does not. Had the correlation been driven by active agents
mechanically accumulating larger sums, the secondary would have collapsed
relative to the primary. It did not, which argues the signal is in per-trade
quality rather than volume. `ic_diagnostics.py` tests that path directly.

**Coverage.** 69 of 100 collected agents fail the 30-trade floor in T1. The
figure describes agents the scorer would actually score in production, which
is the intended population, but it is 31% of the collected universe and must
not be presented as a property of GMX agents generally.

### Validity diagnostics — `docs/evidence/ic_diagnostics.py`

All three checks pass. The run stands.

**S_RAW is not degenerate.** 31 distinct values among 31 agents — no ties at
all — spanning 0.0000 to 63.5911, with quartiles 14.01 / 21.96 / 28.19. The
ranks are ordering real separation, not rounding noise.

**The volume path does not exist.** It was severed at both ends:

| | ρ | p |
|---|---|---|
| S_RAW(T1) ~ trades in T1 | −0.0967 | 0.61 |
| S_RAW(T1) ~ trades in T2 | −0.0159 | 0.93 |
| trades in T2 ~ sum of R in T2 | +0.0137 | 0.94 |
| trades in T1 ~ trades in T2 | +0.5869 | 0.0004 |

The score is uncorrelated with activity, and activity is uncorrelated with
summed R. Only the last row is strong — activity persists across the cut —
and it connects to neither endpoint, so it cannot carry signal into the
primary. The 0.005 agreement between the primary and the secondary is now
explained rather than merely observed.

**No clones.** No pair of the 31 addresses exceeds Jaccard 0.30 on their T1
`exit_time` sets, and no `agent_id` appears in more than one payload file.
Effective n equals reported n equals 31.

### Threats this measurement does not address

**One cut date is one fold.** The result is a single out-of-sample
observation: the ranking held across this particular boundary. It is not a
cross-validated estimate and the interval does not account for regime
dependence. Repeating the measurement over a rolling set of cut dates is the
obvious strengthening — and each additional date is an additional test, which
is precisely the trial inflation a Harvey & Liu haircut is meant to penalise.
Those dates must therefore be declared in a protocol v2 **before** measuring,
not chosen after seeing which ones look best. Running them ad hoc now would
destroy the provenance this document exists to establish.

**The measured object is production, not the specification.** The 0.66 is the
IC of the scorer as built, including the inert component 11 and the three
components that diverge from the Formal Specification. That is the correct
object for a user-facing claim — it is what an allocator would receive — but
the IC of a spec-faithful implementation is unmeasured and must not be assumed
equal to it.

**Model design history is not auditable.** The eleven components and their
weights were specified by judgment before this data was scored, not fitted to
it, which makes this a genuine out-of-sample test. But the components were
chosen by someone with prior experience of these agents. That informal
in-sample information cannot be quantified by any haircut, and the honest
statement is that the explicit multiplicity here is small — three horizons,
one of them pre-registered as primary — while the implicit multiplicity is
unknown.

**One agent scored exactly 0.0000** with at least 30 trades in T1. No
exception was raised (`sraw_nulo` = 0), so this is a computed zero, presumably
a hard gate. Which gate fired should be confirmed; it does not affect the
Spearman, which only uses its rank.

---

## Component-level IC — `docs/evidence/component_ic.py`

Exploratory and diagnostic. The weights are **not** reweighted from this output:
they were fixed before this data was scored, which is the only reason ρ = 0.6577
is an out-of-sample figure at all. Reweighting here would convert it into
in-sample fitting.

Eleven components are eleven tests, and they are strongly dependent — Sharpe,
Sortino, mean R and expectancy all derive from one R series — so the correction
is Benjamini–Hochberg–Yekutieli, which tolerates arbitrary dependence, with
c(12) = 3.1032. BH is reported alongside; BHY governs.

| Component | w | ρ | p_BHY | |
|---|---|---|---|---|
| 10 PF percentile | 0.12 | +0.5960 | 0.0104 | positive |
| 3 Win rate | 0.08 | +0.5636 | 0.0137 | positive |
| 1 Sharpe/PSR | 0.14 | +0.5069 | 0.0221 | positive |
| 2 Sortino | 0.07 | +0.4929 | 0.0221 | positive |
| 5 Avg R | 0.07 | +0.4881 | 0.0221 | positive |
| 6 Expectancy | 0.09 | +0.4881 | 0.0221 | positive |
| 4 Profit factor | 0.10 | +0.3914 | 0.1069 | inconclusive |
| 7 Inv. volatility | 0.05 | +0.3581 | 0.1605 | inconclusive |
| 8 Stability² | 0.09 | −0.0218 | 1.0000 | inconclusive |
| 9 Smoothness² | 0.08 | — | — | constant 0.0 |
| 11 Market context | 0.07 | — | — | constant 50.0 |
| PSR (standalone) | — | +0.4972 | 0.0221 | positive |

**Seven components survive BHY as positive.** At n = 31 under a correction this
conservative, that is difficult to obtain by chance, and it is the substantive
validation of the framework's core.

**The two largest weights sit on the two strongest signals** — Sharpe/PSR at
0.14 with ρ = +0.51, PF percentile at 0.12 with ρ = +0.60. The weights were set
a priori, without seeing this data, and landed roughly aligned with the measured
ICs. That is evidence for the judgment behind the table, and it is citable
precisely because nothing was tuned.

**Raw profit factor is inconclusive at +0.39 while its percentile is significant
at +0.60.** The same underlying quantity, ranked against peers, carries more
forward signal than the absolute ratio — an empirical argument for
percentile normalisation.

### Correction: the penalty rows were mislabelled

The script applies the component decision rule to the two penalties, and that
rule has the wrong sign convention for them. Penalties are **subtracted**, so a
negative IC means an agent with a larger penalty did worse afterwards — the
penalty is hitting its target.

| | ρ | p_BHY | correct reading |
|---|---|---|---|
| MaxDD penalty | −0.5024 | 0.0221 | working; among the strongest signals in the system |
| CVaR penalty | −0.4194 | 0.0746 | sign correct, significance inconclusive |

The MaxDD penalty is as informative as the best components. The script's
`negativo_significativo` label on that row should be read as a pass, not a
finding.

### Effective dimensionality

Nine components carry variance. Rank-correlation eigenvalues explain
62.1 / 20.7 / 6.6 / 5.0 / 3.5 / 1.9 / 0.2 / 0.1 / 0.0 per cent of variance:
**four factors reach 90%, and the first alone is 62.1%.**

Pairs above |ρ| = 0.90:

| | | ρ |
|---|---|---|
| Avg R | Expectancy | **+1.0000** |
| Sharpe | Sortino | +0.9916 |
| Sortino | Expectancy / Avg R | +0.9897 |
| Sharpe | Expectancy / Avg R | +0.9862 |

Components 1, 2, 5 and 6 are one factor carrying **0.37 of the 0.96 weight —
38.5% of the score on a single dimension** — and 5 and 6 are the same variable
outright (`compute_yaf_metrics` returns `avg_r == expectancy_r`).

**"Eleven components" describes the formula, not the information.** The score has
four dimensions: a risk-adjusted-return factor, win rate, profit factor (better
as a percentile), and inverse volatility. This belongs in the whitepaper, because
a competent reviewer finds it in twenty minutes; present, it demonstrates rigour,
absent, it costs the credibility of everything else.

It also constrains any future reweighting: moving the Sharpe weight moves
Sortino, mean R and expectancy with it, because they are one quantity measured
four times.

---

## Rank versus level

> **Rank-based claims survived every defect found. Level-based claims survived
> none of them.**

ρ = 0.6577 is a Spearman correlation. It passes unchanged through the
miscalibrated PSR, the dead Smoothness², the constant Mc and the duplicated mean
R, because each of those defects is approximately monotone in what remains.
Leave-one-out moves it 0.0820; winsorising moves it 0.0043; the reproduction
guard confirms it to 0.000e+00. It is publishable.

Stage assignment, `isEligible()`, the monthly fee and the published `dsr` field
are **levels**, computed from an S_RAW with a ceiling of 88.02, 15.6% inert
weight, and a PSR whose denominator carries a 5.83× error. **The figure of 4
eligible agents out of 294 is preliminary** and carries that label or is not
published.

The eight defects behind this, each with its arithmetic, are in
`AMENDMENT_v5.0.2.md`. Their resolution changes the scorer and therefore
invalidates this measurement; the canonical figure after the amendment is
measured on **fresh data**, not by re-scoring these 31 agents over this same
31-day window, and is declared canonical before that run.

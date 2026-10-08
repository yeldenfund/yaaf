# Amendment v5.0.2 — Defects found by measurement

**Status:** normative
**Date:** 2026-10-07
**Scope:** `yaaf_score_v5_formal.py` (`5.0.0-FORMAL`, `/root/yaaf` @ `b579e56`),
and Amendment v5.0.1
**Evidence:** `docs/evidence/{ic_test_gmx,ic_sanity_r,component_ic}_result.json`

---

## Provenance

Every defect below was found on 2026-10-07 by running the scorer against the
31-agent GMX sample while establishing `docs/IC_PROTOCOL.md`. None was found by
reading the specification. Two of them had been in production for the whole life
of the scorer, affecting every published YAAF score. Agent counts quoted in this
document are snapshots taken on the dates given; the live API moves with each
scoring run and will not match them.

This is the point of measuring: the specification reads correctly, and the code
matches it closely enough that review did not catch these. Only arithmetic
against real data did.

---

## Correction to Amendment v5.0.1

Amendment v5.0.1 stated that normalising the weight table by its sum of 0.96
makes SISTEMA reach 1000, LEGENDARY fully reachable, and the monthly fee reach
zero. **All three are false as the code stands.** With component 9 identically
zero and component 11 pinned at its neutral default:

```
ceiling = (100 × 0.81 + 50 × 0.07) / 0.96 = 88.0208
```

S_RAW cannot exceed 88.02, so SISTEMA cannot exceed 880.2 and the fee has a
floor of 1.198 USDC. LEGENDARY (≥800) remains reachable but requires CF = SF = 1
with all nine live components simultaneously at 100.

The claims were not wrong in intent. They are wrong because two of the eleven
components do not work. See the resolution below: fixing exactly those two makes
all three claims true.

---

## The defects

### D1 — Component 9 (Smoothness², w = 0.08) is pinned at zero

`s_smoothness = 0.0` for **31 of 31** agents. The implementation, verbatim:

```python
def _smoothness(pnl):
    if len(pnl) < 2: return 0.5
    inc = np.diff(pnl)
    return float(max(0.0, 1.0 - inc.std() / (abs(pnl).mean() + 1e-12)))
```

For an i.i.d. PnL series, `std(diff(pnl)) ≈ √2·σ` while `mean(|pnl|) ≈ 0.8·σ`,
so the ratio is ≈ 1.77 and the expression clamps to zero. It rises above zero
only when the PnL series is nearly deterministic — tested on synthetic agents, a
low-noise winner reaches 0.06–0.21 and everything noise-dominated returns 0.

*Stated precisely, because the first draft of this amendment overstated it:* the
formula is not identically zero by construction. It is zero for every noise-
dominated series, which is every real trading series, and it was zero for all 31
measured agents. It is informative only in a regime trading does not occupy.

8.3% of the normalised score is, in practice, a constant zero.

### D2 — Components 5 and 6 are the same variable (ρ = +1.0000)

`compute_yaf_metrics` returns `avg_r == expectancy_r` — identical values
(−0.671612 for both, in the worked example). Mathematically, expectancy per
trade *is* mean R, so this is not a coding error: the specification defines two
weighted components over one quantity.

Combined weight 0.16 = **16.7% of the score** on a single variable, and the
double count is asymmetric: `CAP_AVG_R = 1.5` but `CAP_EXPECT = 0.6`. For any
agent with mean R ≥ 0.6, `s_expectancy` is pinned at 100 while `s_avg_r` still
moves — a kinked double count rather than a smooth one.

### D3 — Component 11 (Mc, w = 0.07) is a constant

`s_mc = 50.0` for every agent. The component requires β, the correlation between
the agent's daily aggregated R and the daily return of the underlying market;
`compute_yaf_metrics` does not produce it, so the scorer falls back to its
neutral default. It contributes a fixed +3.6458 to every S_RAW and zero variance.

### D4 — S_RAW ceiling is 88.02, not 100

A consequence of D1 and D3. Live weight is 0.81 of 0.96: **15.6% of the score
does not respond to the agent.** This is the defect that invalidates Amendment
v5.0.1 and it is corrected there, above.

### D5 — The `dsr` field is a PSR, not a DSR

`compute_dsr(..., n_trials=1)` is the default; `yelden_score` passes it through
unchanged and production never overrides it. The deflation term
`√(2 ln N)` is therefore never applied. The denominator
`σ_SR₀ = √((1 − γ₃·SR + (γ₄−1)/4·SR²)/(T−1))` is Bailey & López de Prado
faithfully, but without deflation the quantity is the **Probabilistic Sharpe
Ratio**.

N in the DSR is the number of configurations the *strategy's developer* searched.
For a third-party on-chain agent that number is unknowable, so it must not be
guessed: a guessed N manufactures a haircut rather than computing one.

### D6 — The PSR's degrees of freedom are wrong

`compute_dsr(sharpe, n_obs=n_daily, ...)` passes the number of distinct **days**,
while `sharpe_r` is estimated over **trades**. Worked example, 35 trades across
2 days, SR = −5.9976, γ₃ = −1.9891, γ₄ = 7.9918:

| T | σ_SR₀ | z | reported |
|---|---|---|---|
| `n_daily` = 2 | 7.2074 | −0.83 | **0.2027** |
| `n_trades` = 35 | 1.2361 | −4.85 | 6.1 × 10⁻⁷ |

The standard error is inflated **5.83×**, and an agent with Sharpe −6 is
reported as having a 20% chance of a positive true Sharpe when the correct
figure is six in ten million. The 0.2027 reproduces the production value to
fifteen decimals, confirming the diagnosis.

**Impact on the score is small.** For negative Sharpe the `max(sharpe, 0)` clamp
zeroes the component either way; for positive Sharpe the PSR saturates near 1.0
either way. The worst case across the parameter range is +3.4 points on a
0–100 component, i.e. +0.50 S_RAW. The defect destroys the field as a reported
probability; it does not move rankings.

### D7 — The drawdown penalty is in R units, weighted as per cent

`dd_pen = max_dd × 0.20`, where `max_dd` comes from `metrics["max_dd_pct"]`.
Despite the name, `compute_yaf_metrics` derives that value from the cumulative
sum of R-multiples, so it is **in R units, not per cent** (24.94 R in the worked
example, not 24.94%). Two consequences: the 0.20 scale is calibrated for a
quantity it is not receiving, and R-drawdown grows with trade count, so a
longer-running agent accumulates a larger penalty mechanically.

Checked and excluded: this does not explain the penalty's measured IC of −0.5024,
because the trade-count path is severed at both ends (see `IC_PROTOCOL.md`).

### D8 — SF duplicates the level of the score, and the stage thresholds were set as if it did not

Measured on all 316 production YAAF agents from stored payloads, which carry the
real CF, SF and `round_history` (`docs/evidence/{calibration_d8,sf_gate}_result.json`).
This defect was first stated as "the calibration constants assume a history the
population does not have." Measurement narrowed it to something specific, and
dismissed most of the original worry.

**CF is not binding.** Saturated at 1.0 for 246 of 316 agents (77.8%); median 1.0.
`CF_N_STAR = 250` is not what holds the population down.

**SF's dispersion term is inert.** On the 114 agents with a non-zero score and
more than one round of history, `ρ(s̄, SF) = +0.9976`. SF is, in practice, just
`min(s̄/45, 1)`: `σ_s` never approaches `SF_DISP_REF = 25`, so `(1 − σ_s/25)⁺` is
≈ 1 for everyone. **The "Stability Factor" does not measure consistency. It
measures level — redundantly with the EMA.**

```
SISTEMA = EMA × CF × SF  ≈  EMA × CF × min(s̄/45, 1)
```

The score multiplied by a monotone function of itself. This is rank-preserving in
the score — the ranking is not corrupted — but it compresses the scale against
stage thresholds fixed at 200 / 400 / 600 / 800. `ρ(EMA, SISTEMA) = +0.9457` and
`ρ(SF, SISTEMA) = +0.9471` sit side by side because both derive from the same
S_RAW series.

**Consequences, measured:**

- **ELITE and LEGENDARY are empty, 0 real and 0 counterfactual.** Reaching 600
  requires sustained S_RAW ≥ 60 with SF saturated, against a ceiling of 88.02
  (D4) and a population median of 21.96. In this band the agents are genuinely
  weak, and the calibration is not what excludes them.
- **78 of 277 EXPERIMENTAL agents (28.2%) would be PROMISING at CF = SF = 1.**
  They carry s̄ < 45, SF docks them, and they fall below 200. The stage
  distribution therefore mixes performance with calibration and **cannot be
  quoted without that caveat** — but it is a 28% effect, not the whole
  distribution.

**Three hypotheses tested and rejected:**

1. *State is not persisting between rounds.* Refuted: `round_history` has median
   8 and maximum 8, equal to `SF_WINDOW`, with zero empty histories.
2. *The 202 agents at SISTEMA = 0 are unmeasured and should be null, not zero.*
   Refuted: all 202 have `s̄ = 0` with a full history — they scored S_RAW = 0 in
   every recorded round. SISTEMA = 0 is the correct verdict, not missing data. The
   EMA spread among them (8.4 to 255.0) is decay time from the `EMA_INITIAL = 300`
   seed, not skill: 255.0 is exactly 300 × 0.85, one zero round from the seed.
3. *Trading more lowers SISTEMA — a perverse incentive.* Refuted: `ρ(CF, σ_s) =
   +0.6896` confirms more trades means more round-to-round dispersion, but
   `ρ(CF, SF) = −0.0935` (p = 0.32) breaks the chain at the second link, because
   SF does not respond to dispersion at all.

**Resolution, not applied here.** Either remove SF's level term, which duplicates
the EMA, or re-derive the stage thresholds for the compressed scale. Both are
auditable and neither is urgent. D8 is now a precise question rather than an open
worry.

### D9 — The collector silently reached only a fifth of the discovered universe

`main()` in `feed_yaaf_gmx.py` lowercased every address before querying:

```python
a = addr_part.lower()
```

The subsquid index stores addresses EIP-55 checksummed and `account_eq` is an
exact match, so every lowercased query returned an empty result — with no error,
no warning, and in a fraction of the time a real fetch takes.

Demonstrated on one address known to hold 57 trades:

| window | address case | trade actions returned |
|---|---|---|
| 90 days | checksummed | **200** (first page) |
| 90 days | lowercased | **0** |
| 365 days | checksummed | **200** |
| 365 days | lowercased | **0** |

All 100 existing payload filenames carry uppercase hex; they were collected from
a source that happened to preserve case. A later run over 404 further addresses
returned `SKIP (0 trades)` **404 times out of 404**, in 1m57s — about 0.29s per
address, which is the cost of an empty response, not of a paginated fetch.

**It hid depth as well as breadth.** The recovered addresses carry history back
to 2026-07-10, so the collection window is 89 days rather than the ~31 days v1
saw, and the median agent has three distinct months in T1 instead of one. The
conclusion that these agents were simply young was an artifact of this defect.

**This is a defect of the universe, not of the score.** ρ = 0.6577 measures its
31 agents correctly. What the measurement lacked was a defensible account of how
those agents came to be candidates: the universe was capped at 100 of 500
discovered addresses by nothing but which source file happened to carry
checksummed case.

**Fixed** by canonicalising with `eth_utils.to_checksum_address` on read and
using the lowercase form only as a dictionary key, so a future file in either
case is normalised rather than silently failing.

---

---

## Resolution — the minimal change set

| Scenario | W_SUM | live weight | S_RAW ceiling | SISTEMA max | fee floor |
|---|---|---|---|---|---|
| current | 0.96 | 0.81 (84.4%) | 88.0208 | 880.2 | 1.198 |
| remove Mc only | 0.89 | 0.81 (91.0%) | 91.0112 | 910.1 | 0.899 |
| merge 5+6 only | 0.96 | 0.81 (84.4%) | 88.0208 | 880.2 | 1.198 |
| fix Smoothness only | 0.96 | 0.89 (92.7%) | 96.3542 | 963.5 | 0.365 |
| *remove Stability* | 0.87 | 0.72 (82.8%) | 86.7816 | 867.8 | 1.322 |
| D1 fixed + D2 + D3 | 0.89 | 0.89 (100%) | 100.0000 | 1000.0 | 0.000 |
| **D1 removed + D2 + D3** | **0.81** | **0.81 (100%)** | **100.0000** | **1000.0** | **0.000** |

Resolving D1, D2 and D3 — and nothing else — yields a ceiling of exactly
100.0000, SISTEMA reaching 1000 and the fee reaching zero. Both routes through
D1, repair and removal, give the identical ceiling: the arithmetic requires only
that the inert components stop being inert, and does not choose between them.
Decision 2 below chooses, on separate grounds. The three claims of Amendment
v5.0.1 become true precisely when the two inert components are repaired and the
duplicate is merged. **The change set is selected by the arithmetic, not chosen.**

Merging components 5 and 6 at the combined weight of 0.16 does not move the
ceiling, because the total weight on mean R is unchanged. It removes the double
count and the asymmetric kink without recalibrating anything, which makes it the
conservative variant.

### Decisions that remain discretionary and must be declared before re-measuring

1. **The merged component's cap.** `CAP_AVG_R = 1.5` and `CAP_EXPECT = 0.6`
   cannot both survive a merge, and the choice is a calibration decision, not an
   arithmetic consequence. Recommended: **1.5**, because 0.6 saturates at a mean
   R that competent agents routinely exceed, making the component blind exactly
   at the top of the range — the same ceiling defect this amendment removes
   elsewhere.
2. **Component 9: remove it.** *This replaces an earlier recommendation in this
   document to recompute smoothness over the cumulative equity curve. That
   recommendation was made without testing and is withdrawn — on synthetic
   agents the equity-curve form grows with trade count, returns 0.89–0.97 for
   pure noise and 0.97–0.99 for a consistent loser. It is the worst of the
   candidates.*

   Four candidate formulas, tested on synthetic agents at n = 40, 200 and 1000:

   | | noise | smooth winner | volatile winner | consistent loser | n-stable |
   |---|---|---|---|---|---|
   | current, `diff(pnl)` | 0.00 | 0.06–0.21 | 0.00 | 0.10–0.19 | yes |
   | cumulative equity *(withdrawn)* | 0.89–0.97 | 0.97–0.99 | 0.81–0.98 | 0.97–0.99 | **no** |
   | efficiency, `\|Σ\|/Σ\|·\|` | 0.07–0.58 | 0.98 | 0.13–0.23 | **0.98** | yes |
   | signed efficiency, `Σ/Σ\|·\|` | 0.00 | 0.98 | 0.13–0.23 | 0.00 | yes |

   The specification's `min(Calmar/4,1)²` is also unavailable: it requires
   annualising an 18-day return, a 20× extrapolation, and the `/4` divisor
   embeds that annualisation.

   Signed efficiency behaves correctly on every profile — and correlates
   **ρ = +0.8887** with mean R. It adds no dimension; it thickens the collinear
   factor that already carries 38.5% of the score, while inflating apparent
   dimensionality from four components to five under a name that no longer
   describes what it measures.

   No available formula is simultaneously scale-free, sign-aware, n-stable and
   independent of the return factor at this horizon. Removal yields the same
   S_RAW ceiling of exactly 100.0000 (see the table above), and
   **"the framework has no working smoothness measure at this horizon" is a true
   and checkable statement.** Keeping a component that reproduces 89% of mean R
   under the name "smoothness" is the worse outcome.
3. **Penalty rescaling.** Penalties are subtracted after normalisation and do not
   pass through `W_SUM`, so shrinking the divisor makes the same penalty weigh
   relatively less. Measured effect: 12.9% → 12.8% of core. Real in principle,
   negligible in magnitude; recorded rather than corrected.

---

## What is not amended: Component 8 (Stability², w = 0.09)

Measured IC **−0.0218**, p_BHY = 1.0000, against seven sibling components
returning +0.49 to +0.60. It carries 9.4% of the score with no detectable
forward signal.

**It is not changed.** The decision rule was pre-registered before the
measurement: act on a component only if it is *significantly negative* after BHY
correction; at n = 31 with 12 tests the test has low power, so "not significant"
is inconclusive, not evidence of uselessness. A point estimate landing on zero is
not a licence to amend — acting on it would be the trial-shopping the protocol
exists to prevent, and the fact that the result matches a prior suspicion makes
that temptation stronger, not weaker.

Two separate facts are recorded instead:

- The **specification's** formula `(1/(1+σ_mSharpe))²` was not computable on the
  population as measured: it requires monthly Sharpe dispersion and 0 of 31
  agents had two months.

  *Superseded 2026-10-08.* That was a property of the biased universe, not of the
  venue. With D9 fixed, 117 of 124 eligible agents (94.4%) have two months or
  more and 87 (70.2%) have three. **The computability obstacle is gone — and it
  was only one of two.** Both formulas remain blind to sign, so this does not
  justify adopting the specification's form. A test of both is pre-registered in
  `IC_PROTOCOL_v2.md`.
- The implementation has a degenerate case that is rewarded maximally:

  ```python
  m, s = r.mean(), r.std()
  if s < 1e-12: return 1.0
  ```

  An agent whose every trade returns an identical R scores 1.0 → `s_stability`
  = 100, whatever that R is. Including a constant loss.

- Both the implemented and the specified formulas are **blind to sign**. Each
  measures consistency; neither measures quality. A reliably terrible agent
  scores high on either. Whether that is a defect is undecided: the other
  components measure quality, and in the worked example every one of them
  returned 0 and S_RAW clamped to 0 — the system reached the right verdict.

A test of component 8 is pre-registered for the next measurement, on fresh data.

---

## Effect on claims: rank versus level

The organising result of this work, and the reason it is worth publishing:

> **Rank-based claims survived every defect above. Level-based claims survived
> none of them.**

ρ = 0.6577 is a Spearman correlation. It passes through the miscalibrated PSR,
the dead smoothness, the constant Mc and the duplicated mean-R unchanged, because
each of those defects is approximately monotone in what remains. Leave-one-out
moves it 0.0820; winsorising moves it 0.0043. It is publishable.

Stage assignment, `isEligible()`, the monthly fee and the published `dsr` field
are **levels**. Each is computed from an S_RAW whose ceiling is 88.02 rather than
100, with 15.6% of its weight inert and a PSR carrying a 5.83× error in its
denominator. The figure of 4 eligible agents out of 294 is therefore
**preliminary, pending this amendment**, and must be published with that label or
not at all.

### Immediate action, independent of everything else

`scores.yelden.fund` serves the `dsr` field in every YAAF payload. It is a wrong
number presented as a probability on a public endpoint. Remove it until D5 and D6
are resolved and the field is renamed `psr`.

---

## Sequence

1. Remove `dsr` from the public API. One line, no dependencies.
2. Apply D1 + D2 + D3 with the three declared decisions above.
3. Fix D6 (`n_obs=n_trades`) and D5 (rename to `psr`).
4. Fix D7 (drawdown unit).
5. Re-score; confirm the ceiling is 100.0000 in the live code.
6. Freeze the patched scorer and issue `IC_PROTOCOL.md` v2.
7. Measure on **fresh data**, with the canonical figure declared before the run.

Step 7 is not a re-run on the present sample. Re-scoring the same 31 agents over
the same 31-day window would produce a second number from the same data and no
new information, while creating the opportunity to publish whichever of the two
looks better. The canonical measurement waits for history to accumulate.

D8 is not in this sequence. It is now specific (SF's level term
duplicates the EMA) and the two routes to resolving it are named, but
neither is urgent and both change the stage boundaries, so they belong with
a threshold re-derivation rather than with this amendment.

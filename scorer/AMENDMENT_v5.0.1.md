# Amendment v5.0.1 to the YAAF Formal Specification

**Amends:** YAAF · S_RAW v5.0 + SISTEMA v2.0 · Formal Specification (Version 5.0-SPEC, September 2026)
**Status:** Normative. Issued under §9: *"Any deviation requires a versioned amendment to this specification."*
**Scope:** §1 (Design Principles), §4 (Component Table). No component is added, removed or re-weighted.

---

## 1. The defect

The Specification asserts, twice, that the positive component weights sum to exactly 1.00:

> §1 — *"Weight discipline — positive component weights sum exactly to 1.00; DD and CVaR are pure subtractions."*
> §4 — *"Positive weights sum to 1.00."*

The table in §4 sums to **0.96**.

| # | Component | w |
|---|---|---|
| 1 | Sharpe × DSR | 0.14 |
| 2 | Sortino × Conf | 0.07 |
| 3 | Win Rate | 0.08 |
| 4 | Profit Factor | 0.10 |
| 5 | Avg R | 0.07 |
| 6 | Expectancy E(R) | 0.09 |
| 7 | Inv. Volatility | 0.05 |
| 8 | Stability² | 0.09 |
| 9 | Smoothness² | 0.08 |
| 10 | Pf Percentile | 0.12 |
| 11 | Mc (Independence) | 0.07 |
| | **Σ** | **0.96** |

## 2. Provenance

The shortfall is an arithmetic slip introduced when the e-book v1.3 engine was reweighted to make
room for two new components. It is not a dropped component: every component of both documents is
accounted for below.

| Component | e-book v1.3 | Spec v5.0 | Δ |
|---|---|---|---|
| Sharpe × DSR | 0.18 | 0.14 | −0.04 |
| Sortino × Conf | 0.08 | 0.07 | −0.01 |
| Win Rate | 0.12 | 0.08 | −0.04 |
| Profit Factor | 0.15 | 0.10 | −0.05 |
| Avg R | 0.08 | 0.07 | −0.01 |
| Expectancy | 0.10 | 0.09 | −0.01 |
| Volatility | 0.07 | 0.05 | −0.02 |
| Stability² | 0.12 | 0.09 | −0.03 |
| Smoothness² | 0.12 | 0.08 | −0.04 |
| Pf Percentile | — | 0.12 | new |
| Mc (Independence) | — | 0.07 | new |
| **Σ** | **1.02** | **0.96** | |

0.25 was freed from the nine original components to fund two new ones costing 0.19. The remaining
0.06 was never reallocated, and the starting sum was itself 0.02 above unity.

## 3. Resolution

The calibrated weights are retained unchanged. The weighted sum is divided by Σw before the
penalties are applied:

```
S_RAW = clip( ( Σ_{i=1..11} w_i · s_i ) / Σw  −  CVaR_pen  −  DD_pen , 0 , 100 )
```

with Σw = 0.96.

This preserves the relative importance of every component exactly, and restores the declared
[0, 100] range of S_RAW. Rescaling the weights individually was rejected: it would require
redistributing 0.04 across components whose values were calibrated against published standards,
with no principled basis for choosing the recipients.

§1 and §4 are amended to read: *"positive component weights are normalised to sum to 1.00 before
being applied."*

## 4. Effects

Under the defect, S_RAW saturated at 96 and SISTEMA at 960. Consequences now resolved:

- SISTEMA reaches the full declared range of 1000.
- The LEGENDARY band (800–1000) was only 80% reachable; it is now reachable in full.
- §5.1 of Whitepaper v16 states *"SISTEMA 1000 → 0 USDC (excellence is free)."* The minimum
  attainable fee was 0.40 USDC/month. It is now 0.00, and the published fee model is correct.

Every score rises by a uniform factor of 1/0.96 before penalties — approximately 4%. Rankings are
unaffected, as the transformation is monotonic and identical for all agents.

## 5. Implementation

`yaaf_score_v5_formal.py` — `W_SUM = sum(W.values())`, applied as a single division in the core
sum. The published weight table in the source remains the §4 table, so the normalisation is one
visible step rather than pre-divided constants.

Scores produced before this amendment carry `score_version` values preceding `5.0.1`. They are
comparable among themselves but not directly against later scores; the version field distinguishes
them.

---

*YAAF Formal Specification · Amendment v5.0.1 · October 2026 · yelden.fund*

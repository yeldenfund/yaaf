# D7 — the drawdown: diagnosed, not yet declared

2026-10-09. This file records what was established about the drawdown term and
what is still owed before it can become a spec change. It is deliberately not
a declaration: one of the two changes it proposes has not been measured.

## The unit is R, and it is settled by arithmetic

`metrics/r_multiples.py`:

```python
def _max_dd(r):
    eq = np.cumsum(r)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    return float(dd.max()) if len(dd) else 0.0
```

That is the maximum drawdown of the cumulative-**R** curve, in R units. It is
stored under the key `max_dd_pct`.

`collectors/gmx.py` computes no drawdown at all — zero occurrences of
`max_dd`, `drawdown`, `peak` or `cum` — so the GMX payloads' value comes from
this function.

Checked against a real payload rather than inferred. One GMX agent, 65 trades,
`max_dd_pct` recorded as `7.497937820969819`. Recomputing `_max_dd` over that
agent's 65 `r_multiple` values gives `7.497937820969819` — **difference
0.000e+00, to the last digit.**

The same agent's drawdown as a percentage of its peak is **127.11%**. The two
readings of that field differ by a factor of 17 for this agent. They are not
variants of one quantity; they are two quantities that have been sharing a key.

## The live defect: one population, two units

`emit_yaaf_final.py`, in `score_yaaf`:

```python
perf = payload.get("performance") or {}
if perf.get("max_drawdown_pct") is not None:
    metrics["max_dd_pct"] = perf["max_drawdown_pct"]
```

`performance.max_drawdown_pct` is the genuine percentage produced by
`metrics/hl_perf.py` (`max_dd_pct = dd / peak * 100`). So an HL agent whose
payload carries that field is penalized in per cent, and one whose payload does
not is penalized in R. Which unit an agent is scored in depends on whether the
collector filled a field.

With `dd_pen = max_dd × DD_PEN_WEIGHT` and `DD_PEN_WEIGHT = 0.20`, for the
agent above: **1.50 points in R against 25.42 points in per cent**, on a
composite whose mean on this population is 26.13. The second is near
annihilation.

This substitution has to go regardless of which form the term takes.

## The subtractive form is tail-dominated

`max_dd` over the 302 GMX agents above the 30-trade floor, now known to be in R:

| | |
|---|---|
| min / max | 0.0148 / 281.24 |
| median | 5.75 |
| p25 / p75 | 1.79 / 11.96 |
| p90 / p95 / p99 | 23.69 / 31.39 / 136.11 |
| above 10 R | 85 of 302 |
| above 100 R | 4 of 302 |

Translated through `dd_pen = max_dd × 0.20`: the median costs 1.15 points, p90
costs 4.74, p99 costs 27.2, and the maximum costs 56.2. Against a mean S_RAW of
26.13, the top of the distribution is subtracted straight through the `clamp`
floor to zero.

`sim_weights_dd.py` measures what that does. Scaling the penalty by ten keeps
19 of the top 20 and ρ = 0.9610, while flooring **106 of 302** — a third of the
population tied at zero. Removing it entirely moves ρ by 0.0085.

So the term, in this form, does not discriminate — it deletes. At its current
scale it barely moves the ordering; at any scale where it would move the
ordering, it destroys the bottom third's. Tying agents at zero is not the rule
discriminating better; it is the rule losing the ability to discriminate, which
is the reading error made earlier this week on 165 zeros.

## Proposed, and what each part owes

**1. Rename the field to `max_dd_r`, and have the scorer refuse the old key.**
Owes nothing but the edit. The name has been wrong everywhere it appears, and a
scorer that silently accepts either key is how the two units got mixed.
`hl_perf.py` and `stats.py` keep computing their percentage under a key of
their own; it is a reported field and never a substitute.

**2. Remove the substitution in `score_yaaf`.** Owes nothing but the edit, and
it is a live defect, not a refinement.

**3. Replace the subtractive penalty with a bounded component**, scored to
[0,100] like the other seven and entering through the weighted mean:

    s_dd = clamp(1 − max_dd_r / CAP_DD, 0, 1) × 100

A bounded component compresses the tail by construction instead of letting it
pass through to the floor. **This has not been measured.** The ρ = 0.9944 in
`SPEC_CHANGE_v5.4.0.md` is 1/N over the eight current components with the
drawdown still subtractive; 1/N over nine components with the drawdown inside
is a different rule and has its own ordering. Declaring it on the strength of
the other measurement would be asserting an effect that was not tested.

**`CAP_DD = 20 R`, from convention and not from this sample.** Twenty R means
twenty full-risk units lost from peak, which risk-management practice treats as
catastrophic for a system risking 1R per trade. The percentile that happens to
sit nearby (p90 = 23.69 R) is a sanity check, not the justification: setting a
cap from a percentile of this population would calibrate the specification
against an outcome-selected universe, which is the error that 1/N is being
adopted to avoid.

## What must be measured before item 3 is declared

One more run of `sim_weights_dd.py` with two variants added:

- `1/N 9comp` — nine components at 1/9 each, `s_dd` as above with
  `CAP_DD = 20`, and `dd_pen` removed from the subtraction
- `1/N 9comp CAP=40` — the same with a looser cap, to show whether the cap
  choice moves the ordering or only the level

Reported the same way: ρ against the current base excluding the floored, top-20
overlap, and the count at the floor. The question the run answers is whether
moving the drawdown inside the mean changes who leads, or only how many survive
the floor. If ρ stays above 0.98 and the floor count drops, item 3 is a
strict improvement and can be declared. If ρ falls, the reordering has to be
understood before anything is declared.

## Open, with the same form and the same measurement owed

`cvar_pen` is also subtractive with a clamp, and the saturation test records a
difference of +0.0000 between `cvar_95 = 0` and `cvar_95 = −4`, which suggests
it may be inert at current values. **Not measured.** It deserves exactly the
analysis above, and it is not folded into this one.

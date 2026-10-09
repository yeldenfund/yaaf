# Spec change v5.5.0 — the drawdown: a cap, a name, and a removed substitution

Declared 2026-10-09. Three items that go together. Supersedes the proposal in
`D7_FINDINGS.md`; that file's diagnosis stands, its proposal does not — see
*What was proposed and not declared* below.

## 1. The penalty gets a cap

    dd_pen = min(max_dd, CAP_DD) × DD_PEN_WEIGHT        CAP_DD = 20.0 (R)

**Why.** Without a cap the term is dominated by its tail. Over the 302 sealed
GMX agents above the 30-trade floor, `max_dd` in R:

| | |
|---|---|
| median / p75 | 5.75 / 11.96 |
| p90 / p95 / p99 | 23.69 / 31.39 / 136.11 |
| max | 281.24 |
| above 20 R | 37 of 302 (12.3%) |

At `DD_PEN_WEIGHT = 0.20` the median costs 1.15 points and p99 costs 27.2,
against a mean `S_RAW` of 26.13. The tail is subtracted straight through the
`clamp(…, 0, 100)` floor. Shown on one synthetic agent in the acceptance test:
`S_RAW` **0.0000** at 281 R before, **48.88** after, against 52.88 with no
drawdown at all. The uncapped tail annihilates; the capped tail costs 4 points.

**Measured, by `sim_dd_cap.py` on the same 302:**

| | floored | tied above cap | ρ vs base | top-20 |
|---|---|---|---|---|
| base (calibrated W, no cap) | 11/302 | — | 1.0000 | 20/20 |
| 1/N, no cap | 9/302 | — | 0.9944 | 18/20 |
| 1/N, cap 10 R | 4/302 | 85 | 0.9900 | 18/20 |
| **1/N, cap 20 R** | **6/302** | **37** | **0.9927** | **18/20** |
| 1/N, cap 40 R | 6/302 | 8 | 0.9944 | 18/20 |
| 1/N, no drawdown | 2/302 | — | 0.9885 | 18/20 |

Spearman with average ranks, over the agents neither variant floored.

**The cap does not move the ordering.** ρ ranges 0.9900 to 0.9944 across the
three caps — a spread of 0.0044, all above the 0.98 criterion declared before
the run. What it moves is the floor: 11 down to 6. Less information destroyed,
same order.

**And the top-20 is 18/20 in every 1/N variant, including the one with no
drawdown at all.** So the two agents that leave the top 20 leave because of the
weight change in v5.4.0, not because of anything done to the drawdown here.
This change costs no top-20 movement.

**Why 20 R and not a percentile.** Twenty R is twenty full-risk units lost from
peak, which risk-management practice treats as catastrophic for a system
risking 1 R per trade. p90 sits at 23.69 R, which is a sanity check and not the
justification: taking the cap from a percentile of this population would
calibrate the specification against an outcome-selected universe — the error
that 1/N is being adopted to avoid.

**What the cap costs, named rather than hidden.** The 37 agents above 20 R
receive an identical penalty and therefore tie *on this term*. They continue to
differ on the other eight components, so no two agents tie in `S_RAW` because
of it. That is a far smaller loss than tying at `S_RAW = 0`, which is what the
uncapped form produces, and the distinction between the two was misread earlier
this week on 165 zeros.

**Why the term stays at all, and this part is judgement, not measurement.**
Removing it entirely gives ρ 0.9885 and the same 18/20 — it contributes almost
nothing to ordering on this population, probably because drawdown on a
cumulative-R curve is mechanically correlated with `avg_r` and `stability`
(hypothesis, not measured). But a protocol that claims risk-adjusted
accountability and carries no drawdown term is making a weaker claim. The four
agents above 100 R lose 4 points of 31.8 — 12%, and visible. Removing the term
to gain 0.004 of ρ would buy nothing and say less.

## 2. The key is `max_dd_r`, and `max_dd_pct` is still read

The value is the maximum drawdown of the cumulative-**R** curve:
`_max_dd(r) = max(peak − cumsum(r))` in `metrics/r_multiples.py`.
`collectors/gmx.py` computes no drawdown at all, so the GMX payloads' value
comes from that function.

Verified by arithmetic, not inference: one GMX agent, 65 trades, recorded
`7.497937820969819`; recomputing `_max_dd` over that agent's 65 `r_multiple`
values gives `7.497937820969819` — **difference 0.000e+00**. The same agent's
drawdown as a percentage of peak is 127.11%. The two readings differ by a
factor of 17.

So the field name has been wrong wherever it appears. New collection writes
`max_dd_r`.

**The old key keeps being read, as legacy in R.** The 500 sealed payloads carry
`max_dd_pct`, and rewriting them to rename a key would break the hash manifest
— the one thing that cannot happen. A scorer that refused the old key would
make the sealed inputs unscoreable. So: `max_dd_r` when present, `max_dd_pct`
otherwise, read as R.

**Which key was read goes into the result**, as `max_dd_source`, with
`max_dd_r` and `cap_dd` beside it. Precedence that is not recorded is
precedence that will be misread later, which is how the two units got mixed in
the first place.

## 3. The substitution in `score_yaaf` goes

```python
perf = payload.get("performance") or {}
if perf.get("max_drawdown_pct") is not None:
    metrics["max_dd_pct"] = perf["max_drawdown_pct"]
```

`performance.max_drawdown_pct` is the genuine percentage from
`metrics/hl_perf.py` (`dd / peak * 100`). This injected it under the key
holding a drawdown in R. Within one population, an agent whose payload carried
that field was penalized in per cent and one whose payload did not was
penalized in R, and what decided was whether the collector had filled a field.
For the agent above: **1.50 points in R against 25.42 in per cent**, on a
composite whose mean is 26.

This was the only path by which the legacy key carried a percentage. With it
gone, `max_dd_pct` is unambiguous, which is what makes item 2 safe.

The percentage stays reported in `payload["performance"]`, where the name means
what it says, and never substitutes the R value.

## Why the three are one change

The cap without the removal would clamp a percentage at 20, which means
nothing. The removal without the cap leaves the R tail passing through to the
floor. The rename without the removal leaves two units under two names with no
rule about which wins. The patch writes all three or none.

## Acceptance test

`test_v550_dd_cap.py`, 15 checks: the cap at 0 / 5 / 19.999 / 20 / 50 / 281.24
R; monotone below the cap and flat above; `S_RAW` equal at 50 R and 200 R; both
keys giving the same penalty; `max_dd_source` naming the key actually read;
`max_dd_r` winning when both are present; and `S_RAW` at 281 R no longer zero.

The cap cases use the **legacy** key deliberately. Written against the new key
they passed before the patch — because the old scorer ignores an unknown key,
the penalty was simply absent, and the cases passed for having no drawdown
rather than for having a cap. A test with false passes is worse than no test.

Measured: 8 of 15 failing before, 15 of 15 after.

`test_saturation.py` must **not** change: it uses `max_dd_pct = 8.0`, below the
cap, where this patch is a no-op by construction.

## What was proposed and not declared

`D7_FINDINGS.md` proposed making the drawdown a ninth scored component in
[0,100]. That is not declared here, and the reason is the measurement: the cap
achieves the floor improvement (11 → 6) without adding a component, without
changing the weight vector that v5.4.0 just fixed, and without a `CAP_DD`
scaling to calibrate. The component form was never measured, and ρ = 0.9944 in
v5.4.0 covers 1/N over eight components with the drawdown subtractive — not
nine components with it inside. Declaring the component form on that
measurement would have asserted an effect that was not tested.

The diagnosis in that file — the unit proven by arithmetic, the live
substitution defect, the tail domination — is what this change rests on and
stands as written.

## Open, unchanged

`cvar_pen` has the same subtractive-with-clamp form, and the saturation test
records a difference of +0.0000 between `cvar_95 = 0` and `cvar_95 = −4`, which
suggests it may be inert at current values. **Not measured.** It deserves
exactly this analysis and is not folded into it.

**Measured effect:** measured before the patch, for the same reason as
v5.4.0. Over the 302 GMX agents the cap's benefit is the floor rather than the
ranking: agents pinned at `S_RAW = 0` by the drawdown tail fell from 11 to 6,
while the drawdown's contribution to Spearman rho is at most 0.006 under any
treatment tested. Method in `docs/evidence/sim_dd_cap.py`.

The ranking being nearly untouched is the point, not a disappointment: the cap
was adopted to stop a tail from flooring an otherwise assessable agent, not to
reorder anyone.

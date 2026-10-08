# Gate Measurement Protocol v3

**Status:** ready to freeze — precondition 1 verified; 2 and 3 gate execution, not this text
**Date:** 2026-10-08
**Measures:** the gate, on GMX V2
**Does not supersede** `IC_PROTOCOL_v2.md`, which measured a different question on a
different universe. It supersedes nothing; it is the first protocol in this work
that measures the thesis.

---

## Why v3 exists

v1 and v2 measured prediction: whether the score ranks forward returns. The
protocol's thesis is accountability: whether a gate on the score keeps capital
away from agents that destroy it. That has never been measured.

v2's addendum established that it cannot be measured on v2's universe. The 500
addresses are the 250 largest dollar winners and 250 largest dollar losers over a
window ending inside the forward period. Half of them were selected for the
outcome a gate test counts, so a gate test there would measure its own
construction.

Three corrections are therefore built into this protocol, and each one answers a
defect found by measurement rather than by argument.

| Defect found | Correction here |
|---|---|
| The universe was ranked by dollar PnL over a window overlapping T2 | No ranking by any performance quantity, at any stage. Any cap is random with a recorded seed. |
| The split was the median of the universe, so selection and split were circular | **The cut date is declared a priori**, before discovery runs. |
| The ≥10-trades-in-T2 floor silently removed agents that stopped | **No forward floor of any kind.** Zero trades in T2 is an observed outcome, not missing data. |

The third is the one that would have invalidated this measurement on its own.
In a ruin test the outcome *is* cessation, so a filter requiring forward activity
removes exactly the cases being counted. v2 dropped 8 agents that way and
recorded it as an ordinary filter. Backward floors stay legitimate — the ≥30
trades in T1 is the predictor window and history is needed to score. Forward
floors are abolished.

---

## The cut, declared before discovery

**T1 ends and T2 begins at 2026-08-20T00:00:00Z.**

Declared now, before any address is discovered and before any payload is
collected. It is not the median of anything and will not be revisited.

T2 therefore runs from 2026-08-20 to the collection instant — about 50 days at the
time of writing. The longer forward window is the point: ruin is the rarer event
and the forward window is what was short.

**Collection window requested: 180 days**, giving T1 about 131 days. Lengthening
T1 admits more agents past the trade floor and cannot bias a forward test, so it
is requested as long as the index will serve. Whatever the index actually returns
is recorded; the cut does not move to accommodate it.

---

## The universe, declared

Selection may use **only** information timestamped strictly before
2026-08-20T00:00:00Z, and may not rank, sort, filter or stratify on profit,
loss, drawdown, liquidations, volume or any other performance quantity, at any
stage.

**Primary population: every address registered in AIAgentRegistry v2**
(`0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E`) **with `registeredAt` strictly
before the cut**, taken whole.

The registration cutoff is not a performance filter and does not compromise
outcome-blindness. It is required for the question to be well posed: an agent
registered after 2026-08-20 had no gate decision to make at the cut, so there is
nothing about it for a gate test to evaluate. `registeredAt` comes from the
`AgentRegistered` event, which carries a timestamp.

This is the population the gate actually governs — registered agents are who
stake and who would be slashed. It is outcome-blind by construction, because
registration is not a performance measure.

It also corrects a mis-description that has stood through three protocols:
`discover_gmx.py` makes no registry call. It aggregates GMX trade actions by
account. **Every measurement in this work so far is about GMX traders, not about
registered agents** — about the venue population rather than the population the
protocol's own mechanism applies to.

**Supplementary population, with the trigger and the size declared now, before
the count is known:** if **fewer than 100** registry addresses pass the T1 floor,
a supplement is drawn from GMX accounts having at least 30 trade actions
**within the 180 days immediately before the cut** — the same length requested
for T1, so the activity criterion and the predictor window cover the same period
— **sampled at random with `seed = 20260820`**, to bring the measured total to
**400**.

*The activity window was added 2026-10-08, after the first freeze
(`f097adec`, blob `6e38d4ef`) and before any discovery ran. The frozen text said
"strictly before the cut" with no window, which is unbounded; a script choosing
the bound would have made the protocol's decision in code, which is the defect
that `trades >= 5` and D9 both were. Amended before execution and re-frozen;
nothing has been measured under either version.*

Both numbers and the seed are fixed here because "widen it until there is enough"
applied after seeing the count is a post-hoc decision dressed as a precaution.
Random is the only outcome-blind way to cap a population; ranking of any kind is
forbidden, and "top N by activity" is a ranking.

The two populations are reported **separately as well as pooled**. They are
different populations and a pooled figure that hides a divergence between them
would repeat exactly the mixture error that v2's addendum had to undo.

### Discovery, operationally

`discover_gmx.py` cannot be used as written. Two changes, both load-bearing:

- `until_ts` is the cut instant, **not** `time.time()`. The discovery pass must be
  unable to see T2.
- the `sorted(..., key=lambda kv: -kv[1]["pnl"])` ranking and the top-half /
  bottom-half split are removed entirely.

---

## Filters

| | |
|---|---|
| T1 | **≥30 closed trades** before the cut (Formal Specification §2.2; `MIN_TRADES_SRAW`) |
| T2 | **none** |

Every agent passing the T1 floor is measured, including agents with zero trades
after the cut. Their outcome is observed, and for several candidate definitions
below it is the worst available outcome.

---

## The outcome

### Primary: Σ R over T2 ≤ −10

Ten units of risk lost in the forward window.

Declared as a round number, from no distribution, so there is nothing to shop. It
is scale-free, in the same unit the score is built from, needs no liquidation
marker in the payload, and is unaffected by cessation: an agent that stops after a
large loss keeps that loss in its sum.

### Secondaries, pre-registered

1. **Cessation** — no closed trade in the final 14 days of T2.
2. **Σ R over T2 ≤ 0** — the degenerate case of the primary. Retained because the
   classification result in v2's addendum (AUC 0.827 in the losing half, 0.632
   pooled) was measured on exactly this, which makes it the one definition with a
   prior.
3. **Liquidation count in T2 ≥ 5.**

### Why not "any liquidation"

An earlier recommendation in this work named `n_liquidations > 0` as the primary,
on the grounds that it is an event in the data rather than a chosen threshold.
That is withdrawn. The discovery metadata already on disk puts the median
liquidation count per agent at **2.0** in one half of v2's universe and **1.0** in
the other, over a window of roughly a month. Liquidation on GMX V2 is routine, so
a binary "any liquidation" would be true of the majority and would discriminate
nothing. The counter-evidence was in the output of `selection_check2.py` when the
recommendation was made.

### Base rate, reported not revised

The base rate of every definition is reported on the new universe. **If the
primary's base rate falls below 5% or above 95% the test is uninformative, and
that is the result.** The definition is not swapped for a secondary that
separates better. Swapping after seeing the rates is the trial-shopping this
document exists to prevent, and it is more tempting here than anywhere else
because four definitions are on the table and they will not agree.

---

## The gate

**Threshold: SISTEMA ≥ 500**, read from the deployed contract and not from the
documentation.

*Corrected 2026-10-08, before any discovery ran.* An earlier version of this
document declared 400, the VERIFIED band boundary from the published band table.
`contracts/AIAgentRegistry.sol` declares
`uint256 public constant SCORE_THRESHOLD_ACTIVE = 500`. **The contract's gate is
500 and no band boundary corresponds to it** — the bands are <200, <400, <600,
<800, ≥800, so 500 sits in the middle of VERIFIED. The published table therefore
implies the gate falls on a band edge and it does not. The gate that exists is
the one in the contract, so that is the one measured; 400 and 600 are reported as
secondary thresholds because the documentation uses them.

Which predicate encodes the gate — `isEligible(address)` or `isActive(address)`,
both present in the contract — is read from the source and named here before the
run, not chosen after.

On SISTEMA, not on S_RAW. The two are not interchangeable: `SISTEMA = EMA × CF × SF`,
and S_RAW 50 maps to SISTEMA 500 only in the limit of a converged EMA with CF and
SF at 1. The cut tables in v2's addendum were on S_RAW and are descriptive only.
The contract's `INITIAL_SCORE = 300` matches the framework's `EMA_INITIAL`, and
its `MAX_SCORE = 1000` matches SISTEMA's range, so the two scales do correspond;
only the threshold was mis-stated.

**Scorer: patched.** This measurement runs on the scorer after Amendment v5.0.2
D1 + D2 + D3, and only after the acceptance test returns S_RAW = 100.0000 exactly
on a saturating synthetic agent. Unlike v2, which deliberately measured the
scorer as published, a gate measurement must use the scorer that would actually
gate — and the published one has a ceiling of 88.02 with 15.6% of its weight
inert, which moves every band boundary.

---

## Statistic

Not Spearman. The question is classification.

- The 2×2 table: admitted × ruined, with both marginals and the base rate.
- **The difference in ruin rate between admitted and excluded, with a 95%
  interval** (Newcombe, for a difference of proportions). This is the headline.
- Fisher exact p.
- Sensitivity, specificity, and the positive and negative likelihood ratios.
- **AUC of SISTEMA against the ruin indicator**, which uses no threshold and is
  therefore the figure to cite if the band boundary is later re-derived.
- The same five, computed separately on the registry population and on the
  supplementary sample.

**Pre-registered sensitivity, with its control named now.** The admitted-versus-
excluded difference is recomputed stratified by agent size, size being the
**mean `collateral` per trade over T1** — a field the payload already carries,
measured entirely before the cut. It is declared here so that no proxy is chosen
after a result exists. The size control used in the v2 addendum's collider test
was `volume_usd` from the discovery window, which lies inside T2 and is therefore
contaminated for any purpose other than the control it served there; this one is
not.

Reported for the primary definition and for all three secondaries, in one table,
with the primary named as primary.

---

## Power, computed before the run

The minimum detectable difference in ruin rate is computed from the realised n
and base rate **before the contingency table is looked at**, and recorded in this
document.

If the test is underpowered the finding is "underpowered" and the response is to
widen the universe — the registry is not the only source of agent addresses and
the supplementary sample can grow. The response is not to report an underpowered
result as a finding, nor to move the band threshold until something separates.
Component 8 at n = 31 stands as the example of why.

---

## Preconditions, to verify before this document is frozen

1. **Does the payload carry a liquidation marker per trade?**
   **Verified 2026-10-08: yes, no collector patch needed.** Each trade in
   `yaaf_payloads_gmx/*.json` carries `is_liquidation`, set at
   `feed_yaaf_gmx.py:84` from `dir == "LIQUIDATION"`, which
   `collectors/gmx.py:182` maps from GMX order type 7; `metrics.n_liquidations`
   is the count, at `feed_yaaf_gmx.py:127`. Each trade also carries
   `r_multiple`, so the **primary outcome is computable from the payload as the
   collector already writes it**. The field was absent from the v2 result table,
   not from the payload.
2. **Is the scorer patched and has the acceptance test passed?** Phase 1 of
   `PLAN.md`. The gate cannot be measured with a ceiling of 88.02.
3. **Is the retention rule in force?** The input manifest of this run must be
   committed in the same commit as its result. A gate measurement whose inputs are
   not retained is worth as much as one that was never run.

---

## Pre-registration, made checkable

v2 claimed to be frozen before its measurement and that claim is not verifiable:
its first commit is about nine hours after the run and host mtimes are copy
times.

The fix costs one line. **This document is committed before discovery runs, and
the discovery and measurement scripts record that commit hash in their output**,
the way `git_hash()` already records the scorer's. Pre-registration then stops
being an assertion and becomes something a stranger checks with `git log`.

---

## Non-negotiables

The cut date is declared and does not move. No forward filter is introduced. The
outcome definition is not swapped after the base rates are seen. The band
threshold is not moved after the table is seen. No ranking by any performance
quantity enters the selection at any stage.

If the gate does not separate ruin, it is published that it does not. That is the
falsification this whole body of work has been building toward, and a protocol
that could not return it would not be worth running.

---

## What this protocol does not measure

**The slash.** It is implemented — `slashAgent`, `SlashLevel`, and an
`AgentSlashed` event carrying `burned`, `remainingStake` and `reason`, with
`WARNING_SLASH_PCT = 10` and `SUSPENSION_SLASH_PCT = 50`. Whether it has ever
fired is therefore a question about the chain, not an assumption: a scan of
`AgentSlashed` logs answers it. **That scan is a precondition of calling the
slash unmeasurable**, and this document asserted it unmeasurable without running
it. If the event fired even a handful of times there is outcome data, and a
separate protocol is owed. Until the scan runs, the slash is out of scope for
lack of a measurement, not for lack of events.

If the scan finds no events, what remains measurable is counterfactual — how
often the condition would have triggered across this universe, and whether those
agents went on to lose — and that is a statement about the rule's calibration,
not about its effect. Either way it needs its own protocol, which must say which
of the two it is measuring in its first sentence.

---

## Addendum — 2026-10-08, after enumerating the registry, before any measurement

### The deployed gate cannot be measured

`registry_v3.py` enumerated AIAgentRegistry v2 at
`0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E` (11,826 bytes of bytecode, Polygon
mainnet, block 95,195,183):

| | |
|---|---|
| `totalAgents` | **2** |
| `totalRegistered` | 2 |
| `totalActive` | 2 |
| status | ACTIVE, both |
| registered | 2026-04-05, both, 58 minutes apart |
| on-chain score ≥ 500 | **0** |
| `isEligible` now | **0** |
| `minStake` | 50 YLD |
| `monthlyFee` | 1 YLD |

The decoding was checked rather than trusted: for each agent the script computed
`status == ACTIVE and score >= 500` from the decoded struct and compared it with
the contract's own `isEligible`. Two agents, zero divergences.

**n = 2.** The gate as deployed governs two addresses, and at the moment neither
passes it. No statistic recovers a gate test from that, and no widening of the
universe fixes it, because an address that never registered was never subject to
the gate.

### What this changes about the measurement

This protocol's supplementary population was written as a power top-up — a way
to add agents if the registry yielded too few. With n = 2 it is not a top-up; it
is the entire study, and the study is therefore a different object than the one
this document set out to measure. That substitution has to be stated rather than
quietly inherited, because the two questions differ in what they can conclude.

**The measurement that remains possible, and is worth running:**

> Applied counterfactually to GMX accounts selected without looking at outcomes,
> would a threshold of 500 on SISTEMA have separated agents that went on to lose
> heavily from those that did not?

That is a question about **the rule**, on the venue population. It is answerable,
the data path is built, and the classification form already showed signal
(AUC 0.827 and 0.632 on an outcome-selected universe; this would be the first run
on an outcome-blind one).

**It is not a question about the gate.** The result may not be reported as
evidence that the gate works, that registered agents behave in any particular
way, or that capital was protected. There is no capital behind the gate to
protect: both registered agents sit below the threshold, so `isEligible` admits
nobody today.

Accordingly, for this measurement:

- **Primary population:** GMX accounts with at least 30 trade actions in the 180
  days before the cut, sampled at random with `seed = 20260820`, to **400**.
- **The two registered agents are reported separately and never pooled.** Two
  observations are a footnote, not a stratum.
- Every published figure from this run carries the word **counterfactual** and
  names the population as venue traders.

### The adoption finding is the finding about the deployed system

It is published alongside, not instead: the protocol has a live contract on
Polygon mainnet with two registered agents, both below the eligibility
threshold, scores last pushed 2026-10-07 and 2026-09-08. That is a statement
about adoption rather than about the score, and it is more informative about the
system's current state than any correlation in this body of work.

### The slash question, closed without a log scan

The log scan failed — the node caps `eth_getLogs` at 10,000 blocks and the
fallback chunked at 500,000 — but it is no longer needed. `totalAgents` equals
`totalRegistered` equals 2, so only two addresses have ever been registered, and
each carries its own slash history in-struct: `warningCount`, `slashPending`, and
a `status` that a SUSPENSION would have moved to PENDING and a BAN to BANNED.
Both are ACTIVE. The contract's `totalSlashed` and `totalBurned` counters settle
it globally in two calls.

This document asserted the slash unmeasurable without checking. It is now
checkable from the enumeration, and the assertion should stand or fall on those
two counters rather than on an assumption.

### Published figures that the contract contradicts

Found while reading the source, and owed a correction on the public surfaces:

| Published | In the contract |
|---|---|
| Gate at the VERIFIED band boundary | `SCORE_THRESHOLD_ACTIVE = 500`, mid-band |
| Stake floors 50 / 200 / 500 / 1000 / 2000 USDC by band | a single `minStake`, 50 **YLD** — no tiering appears in the constants or in `minStake`; confirm by reading `registerAgent` before correcting the text |
| `monthly_fee = 10 × (1000 − SISTEMA)/1000` USDC | `monthlyFee × (MAX_SCORE − score) / MAX_SCORE` with `monthlyFee = 1` **YLD** — same form, different unit and magnitude |

The band-dependent stake floor is the one to check first. If the contract has no
tiering, the whitepaper describes a mechanism that the deployed system does not
implement, and that is a stronger claim to correct than a wrong constant.

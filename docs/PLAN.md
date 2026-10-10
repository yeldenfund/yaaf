# Plan — from the prototype to the final object

**Status:** proposal, not frozen
**Date:** 2026-10-08
**Companion to:** `IC_PROTOCOL.md`, `IC_PROTOCOL_v2.md`, `AMENDMENT_v5.0.2.md`, `STATE.md`
**Scope:** what has to be repaired, in what order, and what "done" means

---

## The framing, accepted

GMX V2 is the prototype. Hyperliquid is the final object. That is correct, and
the reason is not volume — it is falsifiability. GMX has an on-chain
`AIAgentRegistry` that declares which addresses are agents, a subsquid index that
returns closed trades with a usable risk denominator, and 89 days of history
already collected. It is the cheapest place in the world to find out whether
YAAF's thesis is wrong.

Hyperliquid is where the thesis would matter if it is right: roughly 39% of perp
DEX volume, a majority of open interest, and a large share of flow already
automated. It also has no agent registry, no clean attribution of trades to an
automated signer, and no risk-at-entry field from which to build an R-multiple.
Every one of those is a reason to do GMX first, not a reason to hurry past it.

So the order of this plan is: **retain the evidence, close the score, test the
thesis, make the history checkable, correct the claims, then port.**

---

## The failures, sorted

Three kinds, and only one of them is about the score.

**1. Failures of the score.** Nine defects, enumerated with arithmetic in
`AMENDMENT_v5.0.2.md`, change set selected by the arithmetic rather than chosen.
None applied yet. This is the best-understood category and the least important
one, because rank-based claims survived every defect and the measurement already
passed through them unchanged.

**2. Failures of evidence.** YAAF has measured prediction — ρ = 0.2540 on the
corrected universe, honestly obtained. It has never measured accountability. The
gate and the slash, which are the thesis, have no evidence of any kind behind
them. The system has been audited against a claim it does not make.

**3. Failures of durability.** This is the newest and the worst. Below.

**4. Failures of collection.** Found on 2026-10-09 while verifying the re-score.
None of them was looked for, and together they are larger than the score defects
of category 1.

- `wallets_full.txt` holds **143** addresses; `yaaf_payloads/` holds **722**
  files. Neither the six-hourly round nor `refresh_all.sh` collects anything
  outside the wallet list, so **579 payloads belong to addresses that are never
  re-collected** — while being re-scored four times a day until P1 landed. The
  served population is largely built on payloads nobody maintains.
- The six-hourly writer is `run_observatory.sh`, which appears in no crontab, no
  systemd timer and no PM2 app; it was found by the two strings it writes to
  `logs/cron.log`. It collected only addresses with no payload yet — 26 of 139,
  30 of 141, 25 of 143, 29 of 143 across the logged rounds — and then scored
  everything: about 462 rows per round, four rounds a day. Roughly **1,850 scores
  a day standing on roughly 110 collection events**, which is what filled
  `round_history` with a single repeated value in 379 of 391 windows.
- The profile classifier is **not stable for the same address between runs**. Two
  addresses were labelled `directional` in one collector run while their payload
  on disk read `unknown`. The probable cause is in the same output: `HTTP Error
  429` on 9 of 57 addresses, so an incomplete collection yields a partial history
  and a different label. The chain ends in a superseded score published as
  current, which is D12.
- `profile: unknown` is **not** "no data". 261 of 722 payloads carry it,
  including addresses with Sharpe 7.04 and 10% drawdown. A third of the collected
  population never enters scoring, because the emit filters on a label that
  fails. This was previously recorded as wasted API budget; it is larger than
  that.

This category has no phase of its own and needs one. It sits upstream of
everything Phase 2 will measure: a gate measured on a population assembled this
way inherits the assembly's defects, and no statistic computed downstream can
recover from it.

---

## Phase 0 — Retain the evidence

### What happened today

The working tree that produced the canonical measurement is no longer present on
the machine this session runs on. `feed_yaaf_gmx.py`, `yaaf_score_v5_formal.py`,
`yaaf_payloads_gmx/` (500 payloads, 39,945 trades) and
`docs/evidence/ic_test_gmx_v2_result.json` return nothing from a filesystem-wide
search. What survived is what had been copied elsewhere: the protocol documents,
the measurement scripts, the site, the theme.

The production deployment on the VPS may still hold all of it. The point is that
**from here it cannot be determined**, and that is the defect. A figure was
published whose inputs live in exactly one place, unhashed, with no manifest and
no copy, on a 25 GB disk that has already needed a reclaim once.

For a protocol whose thesis is that an agent can terminate and restart and have
its history erased, having its own canonical measurement in that position is the
sharpest contradiction in the system. It is also the one that costs the least to
fix.

### Corrected 2026-10-09

Most of this phase was already done, on the night of the run, and this plan said
otherwise without checking. The record:

- `docs/evidence/gmx_v2/payloads_manifest.sha256`, 500 lines, and
  `ic_test_gmx_v2_result.aggregate.json` were committed **in the same commit**,
  `f22270c`, 2026-10-09T02:02:44Z. The precondition was met at the time.
- `MEASUREMENT_INPUTS.md` in that commit carries the published/withheld split
  with a SHA-256 per item, the scorer-commit correction recorded *as a
  correction* rather than amended away, and the outcome-selected-universe
  caveat.
- Re-checked 2026-10-09: all 500 manifest entries present on disk; nothing in
  the seal missing. The directory holds one extra file, `_summary.json`, which
  the manifest does not cover.

What is actually open in this phase is the second half of the precondition, the
half the plan had been missing: **the producers are not under version control.**
`observatory_commit` is `None` in the result because the collector was not in a
repository when the run happened, and `/root/aiagentregistry-observatory` is
still not a git repository. Until it is, the declared precondition cannot be
satisfied by any future run, GMX or Hyperliquid. The privacy constraint does not
conflict with this: the collector is code, the payloads are data. The code can be
versioned publicly; the payloads stay out, as they already do.

A second exposure remains, and the seal does not address it: the 500 payloads
exist on one disk with no history. The manifest proves they have not changed; it
does not stop them disappearing. If they go, the public label becomes *"measured
2026-10-08; inputs not retained"* even with the manifest committed, because a
manifest without the bodies detects tampering but does not reproduce anything.

### Steps

1. ~~**Inventory the VPS.**~~ Done; see above. 500 payloads, 39,945 trades,
   152 scored after the trade floors.

2. **If they exist, hash them in place.** SHA-256 per payload, one manifest file,
   a root hash over the sorted manifest. Commit the manifest, the result JSON's
   aggregate sections, the scripts and the wallet file in a single commit. The
   manifest discloses nothing and makes the run checkable by a stranger.

3. **If they do not exist, say so on the public page.** The label is
   *"measured 2026-10-08; inputs not retained"*. Do not re-run under protocol v2
   and present the output as the same measurement — a new collection means a new
   window, a new global median and a different cut, which is a different
   measurement wearing the same name. That substitution is the exact failure the
   protocol's non-negotiables exist to prevent, and it does not stop being that
   because the cause was an accident.

4. **Amend the protocol.** New precondition, binding on every future run,
   including Hyperliquid:

   > No measurement is canonical unless the hash manifest of its inputs, and
   > the commit of the collector and scorer that produced them, are committed
   > in the same commit as its result.

   This is the form `docs/evidence/gmx_v2/MEASUREMENT_INPUTS.md` already
   declares, and it is stronger than the one this plan carried: it binds the
   *producers* of the inputs, not only the inputs. The plan is corrected to it
   rather than the record being softened to the plan.

   The tool is `seal.py`, in this directory. `python3 seal.py --base <raiz>
   <alvos>` writes `MANIFEST-sha256.txt` (one `sha256  caminho` line per input,
   ordered by the path's bytes, nothing else, so it is reproducible byte for
   byte) and `MANIFEST-root.txt` (the root plus file count and total bytes, kept
   out of the root's own input). `--verify` re-hashes and reports changed,
   missing and new inputs; it is what a stranger runs. It refuses to seal when a
   named target is missing or yields nothing, because a seal that covers less
   than was asked for comes out valid and misleads.

   This is the one amendment that the current failure argues for, and it is
   cheaper than everything it prevents.

5. **Resolve the publication conflict properly.** The per-agent table (address,
   S_RAW, forward PnL) was withheld because it is a scorecard on named third
   parties. That is right, and it also makes the run unreproducible, which is
   wrong. Both are satisfied by publishing the *means* rather than the *result*:
   the discovery script, the discovery rule it actually applied (see the
   correction below), the patched collector, the scorer, the measurement script,
   the aggregates and the manifest. The data is public on-chain. A third party
   re-collects it and derives the per-agent scores themselves; YAAF is not the
   party publishing a judgement on named agents without their consent. Publish
   the rule, not the output of the rule.

6. **Correction, 2026-10-08: the universe was selected on the outcome.** An
   earlier draft of this document recorded the discovery rule as `trades >= 5`.
   That is the default of `discover_gmx_v2.py`, which did not produce the list.
   The generator was `discover_gmx.py`, and its rule is not a trade floor:

   > aggregate every GMX trade action over a rolling window ending at the run
   > instant, keep accounts with `n_trades >= min_trades` (default 10; the
   > minimum among the 500 is exactly 10), rank by **aggregate dollar PnL**, and
   > take the top `max_addrs/2` and the bottom `max_addrs/2`.

   The 500 are therefore the extremes of dollar PnL — 250 largest winners and
   250 largest losers — over a window ending 2026-10-06.

   **The overlap with the forward window is not conditional on the unrecorded
   `--days`.** The window ends 2026-10-06; T2 runs 2026-09-04 → 2026-10-08. Any
   window of more than two days ends inside T2. So the universe was selected
   using information from the period the primary horizon measures, whatever
   `--days` was passed.

   Two consequences, and they are not the same size:

   - **For ρ = 0.2540:** the figure needs a measured correction, not a caveat.
     The selection variable is dollar PnL, which is size-dominated; the primary
     horizon is a sum of R, which is scale-free. Those may be nearly unrelated
     in this sample — the tertiary result (ρ = 0.0092 on dollar PnL) is weak
     evidence that they are. Theory does not settle the direction here, so it is
     measured: ρ computed **within** the top half and **within** the bottom half
     separately, where no middle of the outcome distribution has been removed,
     plus ρ between the discovery PnL and each horizon. If ρ holds inside both
     halves, the extreme-groups inflation story is dead and the figure stands
     with its provenance stated. If it collapses inside the halves, 0.2540 is an
     artifact of selection and must be retired the way 0.4362 and 0.6577 were.
     The data for this is already on disk: `wallets_gmx.txt` carries the
     discovery PnL per address and the result JSON carries the per-agent table.

   - **For Phase 2:** the form is validated and the universe is not. Asked as a
     classification on this same data the score separates at AUC 0.827 in the
     losing half and 0.632 pooled, which is the strongest result in this work and
     the first one shaped like the thesis. But these 500 cannot be used at all. Half of them were
     selected for being the largest dollar losers in a window inside T2 — which
     is selection on the ruin outcome itself. No caveat repairs that; a gate test
     on this universe would be measuring its own construction. Phase 2 requires
     an outcome-blind universe, declared below.

   It also revises something already published. The near-zero tertiary
   correlation is recorded as a finding — *dollar PnL is not predicted*. In a
   sample built from the extremes of dollar PnL, near-zero on that horizon is
   partly what the construction produces. Downgrade the claim to inconclusive
   until it is measured on an outcome-blind universe.

7. **"Frozen before the run" is not verifiable by a third party for this run.**
   The protocol documents were first committed 2026-10-08T14:06:57Z, about nine
   hours after the 05:00:08Z run, and the host mtimes are copy times. One
   bounded claim does survive and should be the one made: the decision rules
   that could have been shopped — the trade floors, the `stability_spec`
   convention, the Yekutieli constant, the universe filter — were in
   `ic_test_gmx_v2.py`, whose working-tree copy has mtime 04:02Z, before the
   run. That is consistent with pre-registration and is not proof of it, because
   mtimes are forgeable. The manifest should say exactly that and claim nothing
   more.

**Effort:** hours. **Gate:** nothing else should start until the inventory is
known, because everything downstream produces evidence that would be stored the
same way.

---

## Phase 1 — Close the scorer

### Corrected 2026-10-09, second time

The amendment is in the file and not in the data. `/stats` on the live API
reports `scorer_versions {"5.0.0-FORMAL": 363}` against
`scorer_version_on_disk "5.1.0-FORMAL"`: **363 of 363 served YAAF records were
produced by the pre-amendment scorer.** Every figure on scores.yelden.fund —
the bands, the 313 EXPERIMENTAL, the 9 VERIFIED, the eligible count — comes
from a scorer without D1+D2+D3 (9 components, W_SUM 0.96, attainable ceiling
88.0208), without D10 (the CVaR floor, measured at +30 points), and with the
Volume Axiom still active.

This plan said the phase was "closed in substance". It was closed in the
*file*. The file is not what produced the data, and the distinction is the
whole phase: a scorer that has been corrected and not re-run publishes the old
specification under the new version number.

So the deliberate re-score is not a coverage chore. It is this phase's gate.
Its three payloads stand: v5.1.0 scores, the EMA reset at the version boundary
with `round_history` cleared and recorded as a dated event, and coverage over
all 500 payloads. Until it runs, the correct public statement is the one the
page now makes for itself: *the scorer was corrected and has not been re-run,
so no count here reflects the current specification.*

The lag is a field now, not a thing to remember: `scorer_version_lag` in
`/stats`, rendered in the page's caption. It empties itself when the re-score
runs.

---

### Closed 2026-10-09

The re-score ran. 783 addresses served, 777 of them under `5.6.0-FORMAL`, with
`RESCORE_20261009.md` carrying the reversibility hashes, the before-and-after
table, and the stated reason for zeroing each of the three state fields.

The phase's own indicator did not reach zero, and the closure says why rather
than rounding it off. `scorer_version_lag` still lists `5.0.0-FORMAL` behind 6
records. Those six are addresses the current specification **declines to score**,
not addresses that were missed: their payload's profile regressed to `unknown`
and the emit filters on profile. Two further records were withheld entirely,
having no payload at all. The mechanism, the decision, and why the two get
different treatment are in `D12_STALE_RECORDS.md`.

What separates this closure from the one this section had to retract is a number.
When the phase was called "closed in substance", **363 of 363** served records
were pre-amendment and no figure on the page reflected the specification. Now
**777 of 783** are current, the 6 exceptions are published as exceptions carrying
`basis=stale` and a reason, and the 2 unverifiable ones are out of every count
while staying readable one address at a time. This phase existed because *a
scorer that has been corrected and not re-run publishes the old specification
under the new version number*. That is resolved.

**The consequence the phase did not anticipate.** Resetting `ema` to
`EMA_INITIAL` leaves one observation per address, and one observation has a
ceiling of `0.85 x 300 + 0.15 x 1000 = 405` against a contract threshold of 500.
Eligibility fell from 4 to 0 **by arithmetic and not by performance**: no agent
could have cleared the threshold in that round whatever it did. The observed
maximum confirms the identity, `255 + 1.5 x 70.6 = 360.9`.

Measured in `docs/evidence/sim_steady_state.py` over the 607 served YAAF
records, holding CF and SF at the values in each record: **34 clear 500 once the
EMA converges**, projected ceiling **715.16**, 4 to 8 collection events for the
leaders. The threshold is reachable under this specification, which was the
better of the two branches — had nothing reached it, what would have been in
question was the threshold against the scale rather than the agents.

Three figures in that measurement were first stated wrongly here, and the
corrections belong to the record:

- Counting `S_RAW >= 50` gives **86**, not 34. That form assumes `CF = SF = 1`;
  the condition is `S_RAW x 10 x CF x SF >= 500`. The assumption overcounted by
  52 agents, and 86 was quoted as a projection before being checked.
- The mean `SISTEMA` **rises** (115.35 to 141.96) while **395 of 607 EMAs fall**.
  The sign of a product's mean was inferred from the sign of one factor's mean,
  which does not follow: the agents whose EMA rises carry higher `CF x SF`.
- `CF x SF` is **not** concentrated low. One sampled agent showed 0.166 and an
  argument was built on it; across the population 253 agents are above 0.4 and 73
  above 0.8.

Published alongside, so the zero cannot be read as a verdict on the agents:
`eligible_at_ema_steady_state` in `/stats`, computed independently of the
simulation and agreeing with it at 34, and the sentence the page now carries.

---

## Phase 1 — the amendment itself

Apply `AMENDMENT_v5.0.2.md`, in the sequence it specifies, with the three
discretionary decisions as declared there.

| Change | Effect |
|---|---|
| **D1** remove component 9 (Smoothness², 0.08) | no formula at this horizon is simultaneously scale-free, sign-aware, n-stable and independent of the return factor |
| **D2** merge components 5 and 6 at 0.16, cap 1.5 | they correlate ρ = +1.0000; the merge removes the double count without recalibration |
| **D3** remove component 11 (Mc, 0.07) | constant 50 for every agent |
| | **W_SUM 0.81, 8 live components, ceiling exactly 100.0000, SISTEMA 1000, fee floor 0.000** |

Then **D6** (`n_obs = n_trades`; the PSR denominator carried a 5.83× error),
then **D5** (rename the field `psr`, which is what it is), then **D7** (the
drawdown unit — R units weighted as per cent; this one does touch the collector,
because that is where the unit is produced).

**Correction to the record:** `STATE.md` §7 says the D1+D2+D3 patch is blocked on
the collector's `compute_yaf_metrics`. It is not — those three are scorer-only.
Fix that line in the same commit, so the state document does not carry a reason
to delay.

**Acceptance test, written before the patch:** a synthetic agent saturating every
component returns S_RAW = 100.0000 exactly; SISTEMA reaches 1000; the monthly fee
reaches 0.000. A patch that does not produce those three numbers is not the
amendment.

**Consequence to publish at the same moment, not later.** Every level-based
number changes: band assignment, `isEligible()`, the fee, and the census
(EXPERIMENTAL 277, PROMISING 34, VERIFIED 5, ELITE 0, LEGENDARY 0 at the
2026-10-07 snapshot). Those were already labelled preliminary pending this
amendment. When it lands they become historical, and every published count must
name the scorer version that produced it. An agent in a band before and after is
not the same agent.

**D8 stays deferred,** with its reason intact: the SF level term duplicates the
EMA, both routes to resolving it move the band boundaries, and that belongs with
a threshold re-derivation that must declare whether it sits inside or outside the
canonical measurement.

**Effort:** a day, most of it in the acceptance test and the re-score.
**Gate:** Phase 2 assigns bands, so Phase 2 runs on the patched scorer.

---

## Phase 2 — Measure the thesis

This is the centre of the plan, and it has never been attempted.

IC answers *does the score rank future returns* — a question about prediction.
The thesis is a question about accountability, and it is not a correlation at
all. It is a classification:

> Of the agents the gate would have admitted, how many subsequently blew up —
> against the agents it would have excluded?

### What must be frozen before it runs (protocol v3)

1. **The outcome variable.** Ruin, defined once, before looking. Candidates: a
   liquidation event in T2 (`n_liquidations > 0`); T2 drawdown beyond a declared
   threshold in R units; cessation of trading following a losing streak. **One is
   primary and the others are pre-registered as secondary.** Choosing the
   definition after seeing which one separates is the trial-shopping the protocol
   already forbids, and it is more tempting here than anywhere else because three
   plausible definitions exist and they will not agree.

2. **The statistic.** Not Spearman. A 2×2 contingency on admitted × ruined, with
   the base rate stated; sensitivity, specificity and likelihood ratio; Fisher
   exact for p; a confidence interval on the **difference in ruin rate** between
   admitted and excluded. That difference is the headline, and it is the first
   number YAAF would have that is about accountability.

3. **The threshold, and it can no longer be 400 by inheritance.** This item
   said SISTEMA 400 — the VERIFIED boundary, the first band with a stake
   floor that means anything. On 2026-10-09 that number was found to be the
   scorer's own `is_eligible` literal, which governs nothing: the contract's
   `SCORE_THRESHOLD_ACTIVE` is **500**, and the gap between the two was
   publishing 9 eligible agents where the contract accepts 4. The scorer field
   has since been removed. So this phase must **re-declare** its threshold
   before the run — 500, to match what governs registration, or 400 with a
   written reason for measuring the gate at a boundary the contract does not
   use. Inheriting 400 in silence would measure the gate against a number this
   project has just taken out of circulation.

3a. **A minimum date, which is new.** The re-score reset the EMA, so every
   address now carries a single observation and the leaders are 4 to 8
   collection events from convergence. Assigning bands today would assign them
   from scores in transit, and the measurement would then describe the EMA's
   transient rather than the gate. This phase has a floor in time now, and it is
   a function of collection cadence rather than of anyone's schedule. The figure
   to watch is `eligible_at_ema_steady_state` converging on `eligible` in
   `/stats`.

3b. **An outcome-blind universe.** Not the existing 500. The selection rule may
   use only information available before T1 ends — registry membership and an
   activity floor over T1 — and may not rank, filter or stratify on PnL,
   drawdown, liquidations or any other quantity measured in the forward window.
   `discover_gmx.py` cannot be used as written: ranking by aggregate PnL over a
   window ending now is exactly the disqualifying step. The discovery pass for
   Phase 2 takes a fixed `until_ts` at the T1 boundary and no PnL ordering.

4. **Power, computed in advance.** Protocol v2 recorded the tenth percentile of
   last-trade dates at 2026-09-22: roughly one agent in ten stopped before the
   window closed. At n = 152 the ruin cell may be too small to resolve anything.
   **Compute the minimum detectable difference before executing.** If the test is
   underpowered, the finding is "underpowered" and the response is to widen the
   universe, not to report it anyway. Component 8 at n = 31 is the standing
   example of why that rule earns its keep.

5. **The slash is a different object and must be labelled as one.** It has never
   fired, so there is no outcome to measure. What can be measured is
   counterfactual: how often the condition would have triggered across the 152
   agents, and whether those agents went on to lose. That is a statement about
   the rule's *calibration*, not about its *effect*, and the published wording
   has to say which.

### Why this precedes Hyperliquid

If the gate does not separate ruin on GMX — clean data, a real registry, history
already on disk — then porting it to a venue with a contested identity layer and
an estimated R-multiple ports an unvalidated mechanism onto worse data, and no
result from there will be interpretable. The prototype exists to be falsified
cheaply.

**Effort:** the protocol is the work; the computation is an afternoon. The data
is already collected.

---

## Phase 3 — Make the history checkable

The live score table is a SQLite file on the VPS with nothing committing it. A
protocol that sells the permanence of track records cannot ask to be trusted
about its own.

Minimal sufficient version: an append-only hash chain over
`(address, S_RAW, SISTEMA, timestamp, scorer_version)`; a daily Merkle root
published at a `.well-known` path and signed with the registry key; a
verification script in the public repo that a stranger can run against any past
date. Sato already demonstrates the pattern one layer up, which makes it harder
to argue the cost is prohibitive.

This lands before Hyperliquid because it is what makes a two-venue claim
auditable. Two numbers from two venues are worth little if either database could
have been edited.

**Effort:** days.

---

## Phase 3b — The credential surface on yelden.fund

Found 2026-10-09 while restoring the onboard link that v16.5 removed. Taking the
MT5 form down removed the page, not the machinery behind it.

What was still live in theme v16.5/16.6:

1. `POST /wp-json/yelden/v1/score-request` — open, `permission_callback =>
   '__return_true'`, accepting `login`/`password`/`server`, writing the password
   in plaintext to `wp_options`, and (via the queued action) forwarding it to
   `api.yelden.fund` with `'sslverify' => false`. The form was gone; the
   endpoint that the form posted to was not.
2. `assets/push_agent_data_now.py`, `generate_agent_data.py`,
   `fetch_myfxbook.py` — three operational scripts shipped inside the theme.
   `wp-content/themes/…/assets/` is served as static files, so the source was
   readable on request, including `WP_TOKEN = "yelden-2026-markowitz"`. A probe
   distinguishes the real path (content returned) from a nonexistent sibling
   (fetch error), so the files were being served.
3. `POST /wp-json/yelden/v1/agent` — guarded by that same token, which falls
   back to the literal in the theme source when the option is unset. This is the
   write path for `yelden_agent_data`, i.e. every figure the `/agent` dashboard
   displays. A public token on the write path of a live-figures page is the
   tamper problem of Phase 3 in its simplest form, one layer above the database.
4. `after_switch_theme` wrote the literal token into the database on activation,
   so removing the default from the `define()` alone would have been undone by
   the next deploy.

Fixed in v16.7: both MT5 routes answer 410 and read nothing; the queued handler
deletes an orphaned job instead of forwarding it; the `/agent` write requires a
token with no code-side default (unset → 503) compared with `hash_equals`; the
three scripts leave the theme and read the token from the environment; the admin
health check verifies TLS; `?yelden_fix` is replaced by `?yelden_token`, which
generates a random token and shows it once.

**Deployed 2026-10-09.** Theme v16.7 is live; `POST /score-request` and
`GET /score-result/*` answer 410 and read nothing, `POST /agent` answers 401.
The four onboard links, the ten sections and the absence of live figures were
verified on the live page.

Not fixed by the deploy, and still owed:

- **Rotate.** The stored `yelden_api_token` still holds the public literal. The
  patch stops it being re-planted and stops it being readable from the theme; it
  does not change the stored value.
- **Clear the orphans.** `?yelden_clean=1` as admin deletes `yelden_job_%`,
  `yelden_result_%`, `yelden_erro_%`. This is the SQL check that was pending,
  available as a URL. Note the theme's own 24h cleanup never touched
  `yelden_job_%` and its `option_id` condition was arbitrary, so orphans
  accumulate whenever Action Scheduler is inactive.
- **Provenance of `yelden_agent_data`.** Closing the write path says who may
  write; it says nothing about where the numbers come from. They were last set
  by a hand-written literal dict in `push_agent_data_now.py` (`s_raw` 70.05,
  `ema` 519.61, `cf` 0.57, `score` 486). The dashboard reads at runtime and
  hardcodes nothing, so the fix belongs upstream: the push should read
  `facts.json`, which makes `/agent` the fourth consumer of the single source
  and closes the last page carrying unlinked figures.

**Effort:** the deploy is minutes; the provenance item rides with `facts.py`.

---

## Phase 4 — Correct the claims

### Found and fixed 2026-10-09: the eligibility count

`scores.yelden.fund` published **9 eligible** where the contract accepts **4**.
The API counted eligibility by reading `payload["is_eligible"]`, the scorer's
field, whose threshold is 400 — the floor of the VERIFIED band. The contract
requires `score >= SCORE_THRESHOLD_ACTIVE`, which is 500. The nine VERIFIED
agents run 405.47 to 520.53; four clear 500, five do not.

The comment directly above the filter asserted the contract's authority while
the code used the scorer's number, which is what made the disagreement look
settled. `facts.json` had already recorded it as `gate_threshold.agree = false`
the same morning; what the field could not say was that the disagreement was
already producing a wrong number on a public page.

The page also stated, as a fact about the contract, *"`isEligible()` returns
true at SISTEMA ≥ 400"* — inside a section titled "Not proven". The caveat was
wrong about which threshold the contract uses.

Fixed: eligibility is computed from `SCORE_THRESHOLD_ACTIVE` read out of the
Solidity source, and the scorer's threshold is read out of the scorer source,
so neither number is typed into the API. Both counts are published side by
side (`eligible`, `eligible_by_scorer_field`, `eligible_margin`) while they
differ, and the page states the margin and the error it used to publish. The
scorer's `is_eligible` still needs removing, which is why the two counts are
still being compared rather than one being deleted.

### Still false on a public surface

`yelden.fund` says the GMX V2 measurement was made *"under a protocol frozen
before the run"*. `MEASUREMENT_INPUTS.md` says the protocol documents were
first committed nine hours after the run and explicitly declines to claim a
verifiable pre-registration. The evidence record is stricter than the page
announcing it. This is the last claim on a public page that the project's own
evidence contradicts.

---

## Phase 4 — the whitepaper

The whitepaper's body is already about accountability — the epigraph is Taleb on
skin in the game, the title is "Accountability", and four of the five problems in
§02's table are accountability problems. Only the Executive Summary sells a
predictor. That is the part to rewrite.

- Lead with accountability. The measured ρ is a diagnostic, not the product.
- Remove **"2.5× more predictive than Sharpe"**. It was never measured against
  Sharpe under any protocol, which retires it on its own.

  **Do not replace it with "win rate out-predicts the composite."** An earlier
  draft of this plan said so, on the pooled figures (+0.4066 against +0.2540).
  Within groups that comparison dissolves: win rate is +0.2666 and +0.2577 across
  the two halves while the composite moves +0.03 to +0.46. Pooling inflates every
  quantity that differs between the halves, and the composite is the one that does
  not. The claim was confounded by the selection and is withdrawn.

  What survives is narrower: in the half where the model has signal, inverse
  volatility alone reaches +0.5624 against the composite's +0.4607, while
  carrying a weight of 0.05 and being tracked by the composite at only +0.2503.
  The model under-weights its best predictor in the regime where it works. That
  belongs with the threshold re-derivation, not with Amendment v5.0.2.
- Correct the GMX census: 445 addresses and 60 agents become **500 and 152**.
- State what the strongest signal actually is, and state it in the form that
  produced it. Asked as a correlation the score is modest and heterogeneous.
  Asked as a classification — does it separate agents whose forward R is positive
  — it reaches **AUC 0.827** in the half where it has signal and **0.632** pooled,
  on an outcome-selected universe. Consistency and ruin-avoidance, not return
  magnitude. The data has been arguing for the thesis all along; the summary was
  arguing for something else, and so was the statistic.
- List the gate and the slash under *not proven* until Phase 2 returns.

`scores.yelden.fund` already does this. The whitepaper and `yelden.fund` do not.
It is one sitting.

---

## Phase 5 — Hyperliquid

Three preconditions, each to be settled **before any Hyperliquid number is
produced**, because each one of them can change what the number means.

### 1. Identity — the hard one

GMX hands you identity: `AIAgentRegistry` v2 at
`0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E` declares that an address is an
agent. Hyperliquid has nothing equivalent. What it has is `approveAgent`: a
master account authorises an API wallet — Hyperliquid calls it an *agent* — to
sign trading actions on its behalf. The agent cannot withdraw.

Two consequences, and the first is structural:

- **An agent address is a signing key, not an account.** Positions and fills
  belong to the master account. Querying `userFills` for the agent address is
  therefore not the Hyperliquid analogue of querying a GMX agent — the trades are
  not there, and the master account may also trade by hand, mixing automated and
  manual flow in one record. **Verify this empirically before designing
  anything**: take one account known to have delegated, pull its fills, and
  establish whether a fill carries any marker of which signer produced it. If it
  does not, then on Hyperliquid "autonomous agent" is a property of a
  *delegation*, not of a wallet, and YAAF's unit of account changes at the venue
  boundary. That is publishable as a finding about the venue; it is not something
  to discover after a correlation has been computed.

- **The enumeration route is the `approveAgent` action itself.** Those actions
  are L1 actions visible in decoded blocks — which is why third-party
  documentation of their payloads exists at all. A discovery pass over decoded
  `approveAgent` actions yields `(master, agent)` pairs: a chain-derived
  equivalent of the Polygon registry, built from what accounts did rather than
  from a contract they opted into. Senpi and similar directories are a second,
  weaker source — self-declared, useful for labelling, not for enumeration.

### 2. The R-multiple

The caveat already published is that Hyperliquid R is estimated from notional,
data quality `medium`, and the earlier Hyperliquid pass returned ρ = −0.0305
(p = 0.62). The structural reason is now specific: **R needs risk at entry, and
Hyperliquid does not expose it.** `clearinghouseState` gives `marginUsed`,
`leverage.rawUsd` and `entryPx` for the *live* position; a closed trade's entry
margin is in no field. Three options, one of which must be declared in advance:

| | Approach | Cost |
|---|---|---|
| a | Reconstruct entry margin from leverage and entry notional | inherits every leverage change mid-position |
| b | Use `closedPnl` normalised by entry notional, and **do not call it R** | honest, and not comparable to GMX |
| c | Score Hyperliquid on a PnL-normalised metric, accepting approximate comparison | weakest claim, clearest provenance |

(b) is probably right, and it carries a conclusion worth stating up front: **the
Hyperliquid score is then not the same number as the GMX score.** That is a
finding about venue comparability, not a failure to be smoothed over in a methods
note.

### 3. The protocol runs unchanged

The entire value of doing Hyperliquid second is that it is an out-of-venue
replication. Same frozen trade floors (≥30 in T1, ≥10 in T2), same split rule
(global median of exit times, recomputed), same statistic, same reproduction
guard, same retention manifest from Phase 0. Where the venue forces a deviation,
the deviation is published with its reason and the result is labelled a different
measurement.

**Stated in advance, so it cannot be spun afterwards:** a replication on an
independent venue with a weaker return construction will most likely return a
**lower** ρ than 0.2540. If it comes back higher, that warrants suspicion, not an
announcement.

The assets that already exist — `wallets_hl_discovered.txt` (100),
`wallets_hl_all.txt` (57), `wallets_hl.txt` (50), `feed_yaaf_hl.py`,
`feed_yaaf_hl_fast.py`, `discover_hl.py` — were built before the protocol existed
and have never run under it. Treat them as drafts. Three wallet files with three
different counts and no payloads is the same provenance gap that produced D9:
nobody can say by what rule any of the three was constructed.

---

## What the final objective is

Not a higher ρ.

> An allocator points at an autonomous agent on the venue where most agent
> volume actually happens, reads a score whose inputs were retained and whose
> history is tamper-evident, and knows — from a measured ruin rate, not from an
> argument — how much less often capital behind that score has been destroyed.

Four things stand between here and that sentence, and they are Phases 0 to 3.
Phase 5 is where it gets used. The correlation is an instrument along the way.

---

## How this fails

Stated plainly, because a plan that has no failure modes has not been thought
through.

**The gate may not separate ruin.** This is the real falsification, and it is
live. If agents above SISTEMA 400 blow up at the same rate as those below, the
thesis is wrong as built. The right response is to publish that and redesign the
gate — not to try the second outcome definition, and then the third.

**The test may be underpowered.** More likely than outright falsification. The
response is a wider universe: 500 addresses is not the venue, and the registry
is not the only source of agent addresses. Widening
costs collection time. Weakening the test costs the protocol.

**Hyperliquid identity may not resolve at acceptable quality.** Then the final
object is reachable only with a declared, weaker unit of account, published as
such.

**One operator, one VPS.** 25 GB, two growing SQLite databases, one reclaim
already needed, failed-login noise in `btmp`, a prior compromised-wallet
incident, and — as of today — a canonical measurement whose inputs cannot be
located from here. This is the most probable cause of the whole thing failing,
and it is the reason Phase 0 is Phase 0.

---

## The recurring error, recorded

Kept because the only use of recording a mistake is that the next session does
not repeat it. From 2026-10-09.

**Seven of one kind: a name was trusted instead of the arithmetic.**

- `load_payload(r[6])` was read as implying a path. The column holds JSON.
- A cron at `0 3 * * *` against records stamped `00:04` was read as a three-hour
  timezone bug. The machine runs in UTC; there was no offset, and the P1
  declaration it would have retracted was correct.
- `EMA_ALPHA = 0.85` was read as the smoothing weight. It is the decay; the
  weight is 0.15. The rounds column then came out as `1` for all 34 agents, and a
  uniform result across a population is a symptom, not a finding.
- A tmux session whose 3d16h uptime coincided with the start of a cadence was
  read as its cause. The session was an idle shell.
- A search filtered on `yaaf|observatory` hid `run_observatory.sh`, because the
  filter was chosen from the hypothesis instead of from the evidence.
- `gate` and `assessable` were seen in a `5.6.0` payload and assumed present in
  the `5.0.0` population. They were added later. The document that called that
  measurement unrecoverable was right and was doubted without evidence.
- `"is_eligible" not in src` was used to test for a removed field. The word
  survives in a comment, so the note asserted a read failure that had not
  happened — a null with the wrong cause, replacing a null with a different wrong
  cause. The correct predicate was already written, the same day, in
  `test_v560_weights_eligible.py`.

In every one the check was a single query, and in two the right answer was
already written in a neighbouring file.

**Two of a worse kind.** A per-agent file was named as something that must not be
committed, and then committed by the very `git add -A` offered in the same
message — the warning was worthless because the command contradicted it. And a
commit message described work that its patch had aborted without writing, so a
public history carried a claim about fields that were still empty. Both were
corrected by following commits rather than by `--amend`: a wrong message in the
history is a smaller problem than a history rewritten to look clean.

**Three of a third kind: a test that failed for its own reasons and nearly
condemned working code.** A replica built with the wrong anchor string. A
`for a in $A` loop written to bash's splitting rules inside zsh, which does not
split. A listing checked at `limit=500` over a population of 783, where the
record being sought sorts last. Each printed a verdict about the implementation
that was false.

**What caught five of the first seven was not judgement.** It was the habit of
asking for the verification output instead of assuming the step worked: the wrong
`facts.py` note surfaced only because a `facts.py | head -2` was in the block.
The atomic-group discipline refused to write on three separate occasions when an
anchor did not match, and each refusal was correct — including one that would
have left a public endpoint raising `NameError`, which is the defect that
discipline was adopted after causing once.

The rules, in the order they were earned:

1. A name is a hypothesis about arithmetic. Check the arithmetic.
2. Choose a search scope from the evidence, not from the hypothesis.
3. A uniform result across a population is a symptom until proven otherwise.
4. A test must establish its own premise before it reports a verdict.
5. Never offer `git add -A` in the same message as a warning about a file.
6. Verify that a patch applied before writing the commit message that describes
   it.
7. Instrument a gate to record what it excludes **before** removing it.

---

## Sequence

| | Phase | Gate to the next |
|---|---|---|
| 0 | Retain the evidence | the inventory is known and the manifest rule is in the protocol |
| 1 | Close the scorer | S_RAW = 100.0000 on the saturation test, in the live code |
| 2 | Measure the gate | protocol v3 frozen *before* the run, power computed *before* the run |
| 3 | Tamper evidence | a stranger can verify a past score from a published root |
| 4 | Correct the claims | no public surface sells a predictor |
| 5 | Hyperliquid | identity verified empirically, R-construction declared, protocol unchanged |

Phases 0 and 4 can run in parallel with anything. Phase 2 depends on Phase 1.
Phase 5 depends on 0, 2 and 3 — on retention because the replication has to be
checkable, on Phase 2 because there is no point porting an unvalidated gate, and
on Phase 3 because two venues' numbers are worth little if either database could
have been edited.

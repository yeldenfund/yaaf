# YAAF — state of the system

**As of:** 2026-10-07
**Scorer:** `yaaf_score_v5_formal.py`, version string `5.0.0-FORMAL`
**Commit:** `b579e56a23f266dc18fa917c14c8e1278f863b54` (`/root/yaaf`)
**Companions:** `IC_PROTOCOL.md` (frozen protocol + first measurement),
`AMENDMENT_v5.0.2.md` (eight defects with arithmetic)

This is a snapshot for the record. Where it quotes agent counts, those are snapshots
too; the live API moves with every scoring run.

---

## 1. What exists

YAAF scores autonomous trading agents from their closed trades and writes the result
to a reputation registry on Polygon mainnet. A score drives three things: a stage
band, an eligibility flag read by the registry contract, and a monthly fee in USDC
that falls as the score rises.

| | |
|---|---|
| Registry (active) | `0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E` — AIAgentRegistry v2 |
| Registry (deprecated) | `0xbC102cDec0DD007E7739ac213b62d5B031B22aF1` — v1, do not cite |
| Venue measured | GMX V2 |
| Public API | `scores.yelden.fund` |
| Separate product | `observatory.yelden.fund` — ERC-8004 + x402 census, not this system |

A **second scorer** exists for market makers. It shares the 0–1000 range and the
same database, but it has nine components, its own bands
(INACTIVE / MARGINAL / PROFICIENT / STRONG / PRIME), an explicit `log₁₀(equity)` size
term, no deflated Sharpe and no CVaR penalty. **It is not comparable to YAAF and was
not audited in any of the work recorded here.** It appears in no specification
document. Roughly a third of everything scored in the database comes from it.

---

## 2. The model as built

```
S_RAW   = clamp( Σ sᵢ·wᵢ / W_SUM − cvar_pen − dd_pen , 0, 100 )
SISTEMA = EMA × CF × SF                                        ∈ [0, 1000]
EMA(t)  = 0.85·EMA(t−1) + 0.15·S_RAW·10        EMA₀ = 300
CF      = min( √(trades/250), 1 )
SF      = min( s̄/45, 1 ) · (1 − σ_s/25)⁺       over the last 8 rounds
fee     = 10 × (1000 − SISTEMA) / 1000  USDC
```

**Weights** (eleven components, summing to 0.96, normalised by that sum under
Amendment v5.0.1):

| # | Component | w | | # | Component | w |
|---|---|---|---|---|---|---|
| 1 | Sharpe × PSR | 0.14 | | 7 | Inverse volatility | 0.05 |
| 2 | Sortino | 0.07 | | 8 | Stability² | 0.09 |
| 3 | Win rate | 0.08 | | 9 | Smoothness² | 0.08 |
| 4 | Profit factor | 0.10 | | 10 | PF percentile | 0.12 |
| 5 | Average R | 0.07 | | 11 | Market context | 0.07 |
| 6 | Expectancy | 0.09 | | | | |

**Caps:** Sharpe 2.5 · Sortino 8.0 · PF 2.5 · Avg R 1.5 · Expectancy 0.6 ·
Vol 2.0 · Calmar 4.0
**Penalties:** `cvar_pen = min(CVaR₉₅/2, 1) × 15` · `dd_pen = max_dd × 0.20`
**Gates:** 30 closed trades minimum; volume axiom at 0.1% of initial balance
**Bands:** <200 EXPERIMENTAL · <400 PROMISING · <600 VERIFIED · <800 ELITE · ≥800 LEGENDARY
**Stake floors:** 50 / 200 / 500 / 1000 / 2000 USDC by band

---

## 3. What has been measured

One pre-registered test, protocol frozen before the run, on GMX V2.

| Horizon | ρ | p | 95% CI |
|---|---|---|---|
| **Primary — summed R over T2** | **+0.6577** | <0.0001 | **[0.3955, 0.8207]** |
| Secondary — mean R over T2 | +0.6532 | <0.0001 | [0.3889, 0.8182] |
| Tertiary — summed PnL over T2 | +0.2173 | 0.2425 | [−0.1484, 0.5308] |

**The horizon is part of the claim:** the score computed over ~18 days of trading
ranks the following ~12 days. T1 spans a median of 17.1 days (maximum 18.6); the cut
is the global median `exit_time`, 2026-09-25T03:00:16Z.

**Sample:** 100 payloads collected → 69 dropped below the 30-trade floor in T1 → 0
dropped in T2 → **31 agents measured**. The floor follows from the specification, not
from the measurement, and the figure therefore describes agents the scorer would
score in production — 31% of the collected universe, not GMX agents generally.

**Validity:** re-scoring reproduced every S_RAW to `0.000e+00` against the stored run;
no pair of addresses exceeds Jaccard 0.30 on their T1 timestamps; leave-one-out moves
ρ by at most 0.0820 and winsorising by 0.0043; the score is uncorrelated with trade
count (−0.0967, p=0.61) and trade count is uncorrelated with summed R (+0.0137,
p=0.94), so the volume path is severed at both ends.

**Against dollars the score predicts nothing.** The tertiary interval contains zero.
YAAF ranks skill per unit of risk, not profitability. One measured agent makes the
point on its own: S_RAW 0, forward −15.66 R, forward **+US$9,315**.

### Component-level IC (exploratory; BHY, c(12) = 3.1032)

Seven of eleven survive as positive: PF percentile +0.5960, win rate +0.5636,
Sharpe×PSR +0.5069, Sortino +0.4929, expectancy and average R +0.4881, with the
standalone PSR at +0.4972. The max-drawdown penalty reads −0.5024, which is the
penalty working: a larger penalty preceded worse forward performance.

Profit factor (+0.3914), inverse volatility (+0.3581) and the CVaR penalty (−0.4194)
are inconclusive after correction. **Stability² lands at −0.0218, p_BHY = 1.0000, and
was deliberately left untouched** — the decision rule, fixed before the run, acts only
on a component that is *significantly negative*, because at n = 31 "not significant"
means no power, not no signal.

Raw profit factor is inconclusive while its percentile is significant: the same
quantity, ranked against peers, carries more forward signal than the absolute ratio.

### Effective dimensionality

Nine components carry variance. Eigenvalues explain 62.1 / 20.7 / 6.6 / 5.0 per cent —
**four factors reach 90%**. Average R and expectancy correlate **+1.0000** (the same
variable); Sharpe, Sortino, average R and expectancy sit between +0.986 and +1.000 and
together carry 0.37 of the 0.96 weight, **38.5% of the score on one dimension**.

"Eleven components" describes the formula, not the information.

### Retired

`ρ = 0.4362`, published in Whitepaper v16, has no surviving script, dataset or log,
and the scorer version behind it is unknown. **Retired; not to be cited, including by
us.**

---

## 4. Known defects

Eight, each with its arithmetic, in `AMENDMENT_v5.0.2.md`. None was found by reading
the specification; all came from running the code against real trades.

| | Defect | Effect |
|---|---|---|
| D1 | Smoothness² pinned at zero | 0.0 for 31 of 31; 8.3% of the score is a constant |
| D2 | Average R and expectancy are one variable | ρ = +1.0000; 16.7% of the score, double-counted and kinked |
| D3 | Market context is a constant | 50.0 for everyone; a fixed +3.6458 in every S_RAW |
| D4 | S_RAW cannot reach 100 | ceiling 88.0208; SISTEMA max 880.2; fee floor 1.198 USDC |
| D5 | The `dsr` field is a PSR | `n_trials = 1`, so `√(2 ln N)` never applies |
| D6 | Wrong degrees of freedom in the PSR | σ inflated 5.83×; ≤ +0.50 S_RAW, but the probability is wrong |
| D7 | Drawdown penalty in R, weighted as per cent | scale 0.20 calibrated for a quantity it never receives |
| D8 | The stability factor duplicates the score's level | ρ(s̄, SF) = +0.9976; compresses the scale against fixed bands |

**D4 corrects Amendment v5.0.1**, which claimed SISTEMA reaches 1000 and the fee
reaches zero. Both are false as the code stands — and both become true when D1, D2 and
D3 are resolved: the resulting eight components sum to **W_SUM = 0.81 with a ceiling of
exactly 100.0000**. The change set is selected by the arithmetic, not chosen.

**D8, measured rather than assumed.** CF is saturated at 1 for 246 of 316 agents
(77.8%), so the trade-count factor is not what holds the population down. SF reduces in
practice to `min(s̄/45, 1)` — its dispersion term never activates, because σ never
approaches the reference of 25 — which makes SISTEMA the score multiplied by a monotone
function of itself. That preserves rank but compresses the scale against fixed band
thresholds: 78 of 277 agents in the lowest band (28.2%) would sit one band higher at
CF = SF = 1, while ELITE and above are empty either way. Three competing explanations
were tested and rejected: state not persisting (round history is full, median 8 of 8),
the 202 agents at SISTEMA = 0 being unmeasured (they scored 0 in every recorded round;
their EMA spread of 8.4–255 is decay time from the 300 seed, not skill), and a perverse
incentive to trade less (more trades does raise score dispersion, +0.6896, but
dispersion does not lower SF, −0.0935 at p = 0.32).

---

## 5. What may be published, and what may not

> **Rank-based claims survived every defect. Level-based claims survived none.**

The correlation is a Spearman statistic and passes through the miscalibrated PSR, the
dead smoothness, the constant market context and the duplicated mean R unchanged,
because each defect is approximately monotone in what remains.

| Publishable | Preliminary, pending Amendment v5.0.2 |
|---|---|
| ρ and its interval | Stage assignment |
| Relative ordering of agents | `isEligible()` under the contract |
| Which components carry signal | Monthly fee in USDC |
| That dollar PnL is not predicted | Any count of agents per band |

The `dsr` field has been removed from the public API, because it was served as a
probability and the probability is wrong.

---

## 6. Where things run

| | |
|---|---|
| Host | VPS `plongen`, `94.141.97.5` |
| Scorer (canonical) | `/root/yaaf/scorer/yaaf_score_v5_formal.py`, symlinked into the observatory — one file, no second copy |
| Collector, database, API, docs | `/root/aiagentregistry-observatory/` |
| Scores API | `scores_api.py` on `127.0.0.1:9200`, systemd unit `scores-api`, behind Caddy |
| `scores.yelden.fund` | static measurement record at `/`; `/stats`, `/scores`, `/leaderboard`, `/agents`, `/health` proxied to the API |
| Evidence | `docs/IC_PROTOCOL.md`, `docs/AMENDMENT_v5.0.2.md`, `docs/evidence/*.py`, `docs/evidence/*_result.json` |

**Population, snapshot of 2026-10-07:** 316 YAAF-scored addresses —
EXPERIMENTAL 277, PROMISING 34, VERIFIED 5, ELITE 0, LEGENDARY 0. Median S_RAW ≈ 22
against a ceiling of 88.02. A separate, unaudited engine scores the market makers.

**Operational notes.** Disk is 25 GB with two growing SQLite databases; a reclaim
earlier today freed 1.6 GB. `/var/log/btmp` holds ~32 MB of failed SSH logins. A GitHub
personal access token was exposed in a chat transcript and must be revoked if that has
not already been done.

---

## 7. Open

**Blocked on one paste.** The patch for D1 + D2 + D3 needs the collector's
`compute_yaf_metrics` alongside the scorer, because the two must change together and in
that order. Three decisions inside it are discretionary and are declared in the
amendment: the merged component's cap (recommended 1.5), the removal rather than repair
of Smoothness² (no available formula is simultaneously scale-free, sign-aware,
n-stable and independent of the return factor at this horizon), and the penalty
rescaling (12.9% → 12.8% of core; recorded, not corrected).

**Sequenced after it.** D6 and D5 — fix the degrees of freedom, rename the field `psr`,
and handle multiplicity at the protocol level rather than guessing a trial count that
cannot be known for a third party's agent. Then D7's unit.

**Deliberately deferred.** D8's resolution — removing the factor's level term or
re-deriving the band thresholds — moves band boundaries, so it belongs with a
threshold revision and must declare whether that revision is part of the canonical
measurement or an event after it. Agents in a band before and after are not the same
population.

**The canonical measurement waits for data.** Changing the scorer invalidates
ρ = 0.6577. Re-scoring the same 31 agents over the same 31-day window produces a second
number from the same sample and no new information, while creating the opportunity to
publish whichever looks better. The next measurement runs on fresh history, with the
canonical figure declared before the run.

**Decisions that are not technical.** Whether the repository opens, and under what
terms — on a public chain, hashing an address protects nothing, because the trades
themselves are re-identifiable from their timestamps, so the choice is between naming
agents with consent and withholding trade data, not between raw and anonymised. And
what contact, if any, the public page carries for prospective allocators.

---

## 8. How this was done, for whoever picks it up

Three practices did the work, and they are cheaper than the errors they caught.

**Import production, never reimplement it.** Every measurement script imports
`compute_yaf_metrics` from the collector and the scorer itself, so the measurement
exercises the same code path that produces published scores. A draft that rebuilt
metrics by hand would have reported four components as constants and produced a
fabricated null result about the very component under investigation.

**Guard the reproduction.** `component_ic.py` recomputes each S_RAW and aborts if it
differs from the stored run. A divergence in code path stops being a silent error and
becomes a halt.

**Compute before concluding.** Four verdicts written into these scripts before any real
number existed turned out wrong: a threshold on |R| versus collateral, the sign
convention on penalties, "not measurable" for agents that had simply scored zero, and a
"confirmed" perverse incentive that the floor had manufactured. The arithmetic
corrected all four. The scripts that only compute, and leave the conclusion to a
reader, were the ones that never misled.

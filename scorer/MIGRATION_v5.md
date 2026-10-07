# YAAF v5 — closing the code ↔ whitepaper gap

## What diverged

`yelden_scorer_api.py` declares `v5.5` in its header, but `calculate_sraw()`
implemented what its own inline comment calls "S_RAW v4.1": 9 components, where
Whitepaper v16 section 3.1 documents 11 components plus 2 penalties.

| | Whitepaper v16 | Code v5.5 | Now |
|---|---|---|---|
| Components | 11 | 9 | 11 |
| Pf Percentile (0.12) | yes | absent | implemented |
| Mc / Independence (0.07) | yes | absent | implemented |
| CVaR penalty | yes | absent | implemented |
| Weight sum | 0.96 (text claimed 1.00) | 1.02 | 0.96, normalised to 1.00 |
| CF | sqrt(n/250) | sqrt(n/200) | sqrt(n/250) |
| SISTEMA | EMA x CF x SF | EMA x CF (no SF) | EMA x CF x SF |
| SISTEMA ceiling | 1000 | ~405 | 1000 |
| Fee model | documented (5.1) | absent | implemented |
| Stake denomination | USDC (4.1) | YLD (`s_min_yld`) | USDC |

## The bug that froze the protocol's economics

v5.5 computed:

    ema = 300 * 0.85 + s_raw * 10 * 0.15

That is a **single** EMA step from a hard-coded constant, not the whitepaper's
recurrence. Since `s_raw` is capped at 100, the maximum EMA was
`255 + 150 = 405`. With `cf <= 1`, SISTEMA could never exceed 405.

Consequences: the **ELITE (600+) and LEGENDARY (800+) bands were unreachable**,
and `isEligible()` — which requires SISTEMA >= 400 — was effectively impossible
to satisfy. No agent would ever have passed the integration gate.

The EMA is now iterated across scoring rounds, as
`EMA(t) = 0.85 x EMA(t-1) + 0.15 x S_RAW x 10` requires, converging to
`S_RAW x 10`.

This also means that any SISTEMA score above 405 quoted in older material
**could not have come from this code** — those values were mathematically
unreachable.

## Interpretation decisions

The whitepaper is ambiguous on four points. Each choice below was validated
empirically; see `compare.py`.

**Pf Percentile** — "% of 1,000 random portfolios beaten". Null model: hold the
|P&L| magnitudes fixed and draw each sign at random with p=0.5, yielding a
no-skill operator with identical position sizing. Shuffling trade order would
not work — Profit Factor is invariant under permutation.

**Mc (Independence)** — `(1-|beta|)^2 x 100`, with beta read as the lag-1
autocorrelation of per-trade P&L, not a market beta.

**CVaR** — normalised by the **average win**, not the average loss. Against the
average loss the penalty landed between 9.74 and 11.45 across every test case:
a constant offset rather than a discriminator. Against the average win it ranges
from 7.00 to 15.00 and is monotonic in agent quality.

**SF** — the "last 8 S_RAW" are the last 8 **scoring rounds** over accumulated
history, not 8 disjoint slices. Slices of ~15 trades produce noise-dominated
S_RAW, sigma exceeds 25, and SF collapses to zero even for sound agents.
Cumulative windows are used, discarding the first half of the record so the
warm-up does not dominate sigma.

## Determinism

Pf Percentile resampling is seeded from a SHA-256 digest of the trade record.
Identical input always produces an identical score — a requirement for a score
that is committed on-chain and must be independently verifiable.

## Integration

    cp yaaf_v5.py scorer/

In `yelden_scorer_api.py`, remove the existing `calculate_sraw()` (roughly lines
149–331) and replace it with:

    from yaaf_v5 import calculate_sraw

The signature and return shape are compatible. Every field consumed by
`save_to_leaderboard()` and by the WordPress endpoint is still present.
`s_min_yld` is replaced by `s_min_usdc`; `monthly_fee_usdc`, `is_eligible`,
`pf_percentile`, `mc` and `cvar_penalty` are new.

Validation: `python3 compare.py` runs v5.5 and v5 side by side on the same data.

## Open items

- `STAKE_FLOORS_USDC` carries the v5.5 values (50/200/500/1000/2000)
  redenominated from YLD. The whitepaper does not specify stake floors, so these
  need a decision.
- An agent with no edge (WR 50%, payoff 1.0) still reaches SISTEMA ~242
  (PROMISING). It sits below the 400 gate, but the framework's floor is
  generous. This is calibration, not divergence.

# YAAF — Yelden Agent Accountability Framework

> Accountability infrastructure for autonomous trading agents.  
> Score. Allocate. Slash. On-chain.

[![Tests](https://img.shields.io/badge/tests-69%20passing-brightgreen)](./test)
[![Solidity](https://img.shields.io/badge/solidity-0.8.20-blue)](./contracts)
[![Mainnet](https://img.shields.io/badge/polygon-mainnet-8247e5)](https://polygonscan.com/address/0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

*"An agent that cannot lose cannot be trusted."* — Taleb, Skin in the Game

---

## The Problem

Autonomous trading agents manage capital at scale. None are accountable.

An agent that underperforms today can stop, restart under a new address, and continue
operating with no track record, no consequence, and no mechanism for capital allocators
to distinguish skill from luck.

YAAF is the scoring and enforcement layer that changes that.

---

## Empirical Validation

YAAF's S_RAW score was tested against future returns across three venues.

| Venue | Data Quality | n | IC — YAAF | IC — Sharpe |
|---|---|---|---|---|
| **GMX V2** | **high** (real collateral) | 60 | **0.4362 (p=0.0005)** | 0.1747 (p=0.18) |
| Hyperliquid | medium (estimated R) | 268 | −0.0305 (p=0.62) | 0.1144 (p=0.06) |
| Darwinex | low (smoothed) | ~80 | 0.1411 (p<1e−30) | — |

**YAAF is 2.5× more predictive than Sharpe when real R-multiples are used.**

The predictive power is directly proportional to data quality — validating the
Volume Axiom as a fundamental gate, not a decorative constraint.

---

## The YAAF Score

### S_RAW v5 — 11 Components + 2 Penalties

| # | Component | Weight | Formula |
|---|---|---|---|
| 1 | Sharpe × DSR | 0.14 | min(SR/2.5, 1) × 100 × DSR |
| 2 | Sortino × CF | 0.07 | min(Sortino/8, 1) × 100 × min(n_loss/20, 1) |
| 3 | Win Rate | 0.08 | WR × 100 |
| 4 | Profit Factor | 0.10 | min((PF-1)/1.5, 1) × 100 |
| 5 | Avg R | 0.07 | min(AvgR/1.5, 1) × 100 |
| 6 | Expectancy | 0.09 | min(max(E(R),0)/0.6, 1) × 100 |
| 7 | Inv. Volatility | 0.05 | max(1 − σ_d/2, 0) × 100 |
| 8 | Stability² | 0.09 | (1/(1+σ_mSharpe))² × 100 |
| 9 | Smoothness² | 0.08 | min(Calmar/4, 1)² × 100 |
| 10 | Pf Percentile | 0.12 | % of 1,000 random portfolios beaten |
| 11 | Mc (Independence) | 0.07 | (1 − \|β\|)² × 100 |
| — | CVaR penalty | − | min(CVaR/2, 1) × 15 |
| — | Max DD penalty | − | MaxDD% × 0.20 |

The weights above are the calibrated values of the Formal Specification. They sum to 0.96 and
are divided by that sum before being applied, so S_RAW is bounded in [0, 100] while relative
importance is preserved exactly (Amendment v5.0.1).

Four components admit more than one reading; the Formal Specification fixes them so any third
party can reproduce a published score:

- **Pf Percentile** — K = 1,000 vectors drawn from N(0, σ_r) with the same length as the agent's
  R-multiple series. The component is the percentage of those random portfolios whose annualised
  Sharpe the agent's real Sharpe exceeds.
- **Mc (Independence)** — β is the correlation between the agent's daily aggregated R and the
  daily returns of the underlying market. Own edge is rewarded; market beta is not.
- **CVaR penalty** — expected shortfall of the R-multiple series at α = 0.95, loss side, taken
  positive. Coherent and tail-sensitive (Rockafellar & Uryasev, 2000).
- **SF** — the "last 8 S_RAW" are the eight most recent scoring *rounds*, carried in the agent's
  persisted state. Each round contributes one EMA update.

Scoring is deterministic: every random stream used by the Pf Percentile is seeded, so a score
committed on-chain can be recomputed by anyone holding the same trades.
See [`scorer/MIGRATION_v5.md`](./scorer/MIGRATION_v5.md).

### SISTEMA — Time-Compounding Score [0–1000]

```
SISTEMA(t) = EMA(t) × CF(t) × SF(t)

EMA(t) = 0.85 × EMA(t−1) + 0.15 × S_RAW × 10   # memory, EMA₀ = 300, one update per round
CF     = min(√(trades/250), 1.0)                  # confidence, full at 250 trades
SF     = min(mean(last 8 S_RAW)/45, 1) × (1 − σ_s/25)  # safety factor
```

### Score Bands

| Band | SISTEMA | Interpretation |
|---|---|---|
| EXPERIMENTAL | 0–199 | Insufficient track record |
| PROMISING | 200–399 | Emerging performance |
| VERIFIED | 400–599 | Consistent performer — `isEligible()` threshold |
| ELITE | 600–799 | Top-tier |
| LEGENDARY | 800–1000 | Exceptional |

### Data Quality Tiers

Every score carries an explicit quality multiplier:

| Tier | Definition | Multiplier |
|---|---|---|
| **high** | Real collateral / R-multiple from source | 1.00 |
| **medium** | R-multiple estimated from notional | 0.50 |
| **low** | Returns smoothed by intermediary | 0.25 |

```
C_allocated = min(C_kelly, C_stage) × quality_multiplier
```

---

## AIAgentRegistry — Polygon Mainnet

**Address:** `0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E`

Any protocol integrates in two lines:

```solidity
IAgentRegistry registry = IAgentRegistry(0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E);
require(registry.isEligible(agent), "Agent not eligible");
```

`isEligible()` returns true when:
- SISTEMA ≥ 400 (VERIFIED or above)
- Data quality tier is `high` or `medium`
- No pending slash event

### Slash Mechanism

Dual-trigger — fires on drawdown OR capital loss, whichever is higher.
Closes the "24% loophole" (agent stops at 24% DD to avoid 25% threshold).

| Level | Trigger | Penalty |
|---|---|---|
| WARNING | Grade 1 misconduct | 10% of stake |
| SUSPENSION | Grade 2 misconduct | 50% of stake |
| BAN | Critical fraud | 100% of stake + deregistration |

### Fee Model

```
monthly_fee = base_rate × (1000 − SISTEMA) / 1000
```

Score 1000 → 0 USDC. Excellence is free. Mediocrity costs.
All fees in USDC/USDT/MATIC. No native token.

---

## Live Data

**Observatory:** 478 traders scored across GMX V2 and Hyperliquid. Updates every 6h.

**Live agents in production:**

| Agent | Venue | Status |
|---|---|---|
| Pepperstone bot | cTrader | Live — 16 closed trades |
| FTMO bot | cTrader | Live — 9 closed trades |
| OKX balancer | OKX | Live — BTC/ETH/SOL/AVAX/gold/USD |
| IBKR equities | Interactive Brokers | Live — US stocks |

All four will be registered on-chain as they accumulate ≥30 closed trades.

---

## Repository Structure

```
yaaf/
├── contracts/
│   └── AIAgentRegistry.sol       # Core contract — Polygon mainnet
├── test/
│   └── AIAgentRegistry.test.js   # 69 tests passing
├── scorer/
│   ├── yaaf_score_v5_formal.py   # Normative scoring engine — 11 components
│   ├── MIGRATION_v5.md           # What changed in v5 and why
│   ├── AMENDMENT_v5.0.1.md       # Weight normalisation amendment
│   └── leaderboard.json          # Persistent agent leaderboard
├── observatory/
│   └── README.md                 # Multi-chain agent census
├── docs/
│   ├── Yelden_Whitepaper_v16.pdf
│   └── Yelden_Whitepaper_v16.docx
├── hardhat.config.js
├── package.json
└── README.md
```

---

## Getting Started

```bash
git clone https://github.com/yeldenfund/yaaf
cd yaaf
npm install
npx hardhat test
```

**Run scorer locally:**
```bash
cd scorer
pip install flask flask-limiter flask-cors httpx python-dotenv
python yelden_scorer_api.py
# POST http://localhost:8080/join — any MT5 credentials → full YAAF score
```

---

## Roadmap

| Phase | Timeline | Milestone |
|---|---|---|
| Foundation | ✅ Complete | YAAF v5 · AIAgentRegistry · Observatory (478 traders) |
| cTrader Integration | Q4 2026 | cTrader API collector · Pepperstone + FTMO registered on-chain |
| Multi-Agent Onboarding | Q1 2027 | 10+ agents registered · first external agents |
| Genesis Scorer Program | Q1 2027 | 3–5 independent scorers · multi-scorer consensus |
| Formal Audit | Q2 2027 | Code4rena or Sherlock |
| Chainlink Oracle | Q2 2027 | Decentralised score submission |

---

## Known Limitations

1. **Single scorer** — founder holds `SCORER_ROLE`. Genesis Scorer Program is the fix (Q1 2027).
2. **No formal audit** — pre-audit. Code4rena / Sherlock planned Q2 2027.
3. **cTrader integration in progress** — Pepperstone and FTMO agents live but not yet scored on-chain.
4. **Short track record** — current fleet has ~25 closed trades across cTrader accounts.
5. **Data quality variance** — Hyperliquid scores carry 0.50× quality multiplier.

---

## References

- Bailey, D.H. & López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management*, 40(5).
- Kelly, J.L. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal*, 35.
- Rockafellar, R.T. & Uryasev, S. (2000). Optimization of Conditional Value-at-Risk. *Journal of Risk*, 2(3).
- Markowitz, H. (1952). Portfolio Selection. *Journal of Finance*, 7(1).
- Taleb, N.N. (2018). Skin in the Game. Random House.
- Van Tharp, T. (1998). Trade Your Way to Financial Freedom. McGraw-Hill.

---

## Contact

**Paulo Longen** — Founder  
yeldenfund@gmail.com · [@yeldenfund](https://x.com/yeldenfund) · [yelden.fund](https://yelden.fund)

Looking for a technical co-founder with production Solidity experience.
Chainlink DON integration is the next critical layer.

---

*YAAF — yelden.fund — Polygon Mainnet — October 2026*

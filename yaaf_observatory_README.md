# Observatory — Multi-Chain Agent Census

Continuous scoring of autonomous trading agents across on-chain venues.
478 traders scored. Scores update every 6 hours.

## Venues

| Venue | Traders | Data Quality | R-multiple basis |
|---|---|---|---|
| GMX V2 | 60 | high | `initialCollateralDeltaAmount` (real collateral) |
| Hyperliquid | 418 | medium | Notional × 1% (estimated) |
| **Total** | **478** | — | — |

## Data Quality Impact

YAAF's predictive power depends directly on data quality:

| Quality | IC (YAAF) | IC (Sharpe) | Multiplier |
|---|---|---|---|
| high (GMX V2) | 0.4362 (p=0.0005) | 0.1747 (p=0.18) | 1.00 |
| medium (Hyperliquid) | −0.0305 (p=0.62) | 0.1144 (p=0.06) | 0.50 |

When real R-multiples are used, YAAF is 2.5× more predictive than Sharpe.
When estimated from notional, the edge vanishes.

## Pipeline

```
discover_gmx_v2.py      — fetch active traders from GMX V2 subgraph
feed_yaaf_gmx.py        — compute S_RAW for each trader
emit_yaaf_gmx.py        — write scores to AIAgentRegistry on-chain

discover_hyperliquid.py — fetch active traders from Hyperliquid API
feed_yaaf_hl.py         — compute S_RAW (medium quality tier)
emit_yaaf_hl.py         — write scores on-chain
```

## Running

```bash
# GMX V2 — high quality
python discover_gmx_v2.py
python feed_yaaf_gmx.py
python emit_yaaf_gmx.py

# Hyperliquid — medium quality
python discover_hyperliquid.py
python feed_yaaf_hl.py
python emit_yaaf_hl.py
```

## Upcoming

- cTrader integration (Q4 2026) — high quality, real stop-loss R-multiples
- dYdX integration (Q1 2027) — medium quality

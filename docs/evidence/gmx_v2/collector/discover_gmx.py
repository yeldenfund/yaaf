"""Descobre top traders GMX por PnL agregado."""
import json
import sys
from collections import defaultdict
from pathlib import Path

from collectors.gmx import fetch_trade_actions


def discover_top_traders(days: int = 30, min_trades: int = 10, max_addrs: int = 200) -> list[dict]:
    """Pega TradeActions recentes e agrega por conta."""
    import time
    since_ts = int(time.time()) - days * 86400

    import time
    until_ts = int(time.time()) + 60
    print(f"coletando tradeActions desde {days}d atrás...")
    all_trades = []
    cursor = since_ts
    pages = 0
    while cursor < until_ts:
        try:
            batch = fetch_trade_actions(since_ts=cursor, until_ts=until_ts, limit=200)
        except Exception as e:
            print(f"  erro na página {pages}: {e}")
            break
        if not batch:
            break
        all_trades.extend(batch)
        pages += 1
        # avança cursor para o último timestamp + 1
        last_ts = max(t["t"] for t in batch)
        if last_ts == cursor:
            cursor += 1
        else:
            cursor = last_ts
        if pages % 5 == 0:
            print(f"  página {pages}: {len(all_trades)} trades, cursor={cursor}")

    print(f"\ntotal: {len(all_trades)} trades")

    # agrega por conta
    by_account = defaultdict(lambda: {
        "n_trades": 0, "pnl": 0.0, "volume": 0.0, "markets": set(), "liquidations": 0
    })
    for t in all_trades:
        addr = t.get("account")
        if not addr:
            continue
        a = by_account[addr]
        a["n_trades"] += 1
        a["pnl"] += t["closed_pnl"]
        a["volume"] += t["usd_notional"]
        a["markets"].add(t["market"])
        if t["dir"] == "LIQUIDATION":
            a["liquidations"] += 1

    # ordena por PnL
    ranked = sorted(by_account.items(), key=lambda kv: -kv[1]["pnl"])

    # filtra por min_trades primeiro
    filtered = [(a, s) for a, s in ranked if s["n_trades"] >= min_trades]

    # mix: metade top, metade bottom (para ter losers também)
    n_total = len(filtered)
    n_each = max_addrs // 2
    top = filtered[:n_each]
    bottom = filtered[-n_each:] if n_total > n_each else []
    seen = set()
    mixed = []
    for a, s in top + bottom:
        if a in seen:
            continue
        seen.add(a)
        mixed.append((a, s))

    out = []
    for addr, s in mixed:
        out.append({
            "address": addr,
            "n_trades": s["n_trades"],
            "pnl_usd": round(s["pnl"], 2),
            "volume_usd": round(s["volume"], 2),
            "n_markets": len(s["markets"]),
            "liquidations": s["liquidations"],
            "pnl_per_trade": round(s["pnl"] / s["n_trades"], 2),
        })
        if len(out) >= max_addrs:
            break

    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--min-trades", type=int, default=10)
    ap.add_argument("--max-addrs", type=int, default=200)
    ap.add_argument("--out", default="wallets_gmx.txt")
    args = ap.parse_args()

    traders = discover_top_traders(args.days, args.min_trades, args.max_addrs)
    print(f"\ntop {len(traders)} traders GMX:")
    print(f"{'address':<44} {'trades':>7} {'pnl':>14} {'liq':>5} {'markets':>8}")
    for t in traders[:20]:
        print(f"{t['address']:<44} {t['n_trades']:>7} {t['pnl_usd']:>14,.2f} "
              f"{t['liquidations']:>5} {t['n_markets']:>8}")

    # salva
    lines = [f"{t['address']}  # pnl={t['pnl_usd']} trades={t['n_trades']} liq={t['liquidations']}"
             for t in traders]
    Path(args.out).write_text("\n".join(lines))
    print(f"\n[ok] {len(traders)} endereços salvos em {args.out}")

    Path("gmx_discover_raw.json").write_text(json.dumps(traders, indent=2))

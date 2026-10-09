"""Coleta trades GMX por trader, agrupa por lifecycle, calcula métricas YAAF."""
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from collectors.gmx import load_tokens, load_markets, _post, normalize
from store import sqlite as db


def fetch_trader_trades(account: str, tokens: dict, markets: dict,
                        days: int = 90, max_pages: int = 50) -> list:
    """Pega TradeActions de um trader, paginando por timestamp."""
    since_ts = int(time.time()) - days * 86400
    until_ts = int(time.time()) + 60
    query = """
    query($account: String!, $since: Int!, $until: Int!, $limit: Int!) {
      tradeActions(
        where: {account_eq: $account, eventName_eq: "OrderExecuted",
                orderType_in: [4,5,6,7], timestamp_gte: $since, timestamp_lt: $until}
        limit: $limit, orderBy: timestamp_ASC
      ) {
        account marketAddress positionLifecycleId basePnlUsd pnlUsd
        sizeDeltaUsd positionSizeInUsd initialCollateralDeltaAmount initialCollateralTokenAddress
        positionFeeAmount borrowingFeeAmount fundingFeeAmount
        priceImpactUsd liquidationFeeAmount executionPrice
        isLong orderType reason timestamp transactionHash
      }
    }
    """
    all_actions = []
    cursor = since_ts
    pages = 0
    while cursor < until_ts and pages < max_pages:
        try:
            data = _post(query, {"account": account, "since": cursor,
                                  "until": until_ts, "limit": 200})
        except Exception as e:
            print(f"    erro: {e}")
            break
        batch = data.get("tradeActions", []) or []
        if not batch:
            break
        all_actions.extend(batch)
        pages += 1
        last_ts = batch[-1]["timestamp"]
        cursor = last_ts + 1 if last_ts == cursor else last_ts
    return [n for n in (normalize(a, tokens, markets) for a in all_actions) if n is not None]


def group_by_lifecycle(trades: list) -> list:
    """Agrupa trades por positionLifecycleId — cada lifecycle = um trade completo."""
    by_lc = defaultdict(list)
    for t in trades:
        lc = t.get("lifecycle_id")
        if lc:
            by_lc[lc].append(t)

    out = []
    for lc, ts in by_lc.items():
        if not ts:
            continue
        # PnL total = soma
        pnl = sum(x["closed_pnl"] for x in ts)
        collateral = sum(x["collateral"] for x in ts)
        fees = sum(x["fee"] for x in ts)
        volume = sum(x["usd_notional"] for x in ts)
        r = pnl / collateral if collateral > 0 else 0.0

        # aberto/fechado: primeiro/último timestamp
        ts_sorted = sorted(ts, key=lambda x: x["t"])
        out.append({
            "market": ts_sorted[0]["market"],
            "entry_time": ts_sorted[0]["t"],
            "exit_time": ts_sorted[-1]["t"],
            "pnl": pnl,
            "collateral": collateral,
            "fees": fees,
            "volume": volume,
            "r_multiple": r,
            "n_fills": len(ts),
            "is_liquidation": any(x["dir"] == "LIQUIDATION" for x in ts),
        })
    return sorted(out, key=lambda x: x["exit_time"])


def compute_yaf_metrics(trades: list) -> dict:
    import numpy as np
    if not trades:
        return {"trades": 0}
    r = np.array([t["r_multiple"] for t in trades], dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return {"trades": 0}
    pnl = np.array([t["pnl"] for t in trades], dtype=float)

    # filtra trades com r_multiple exatamente zero (não fecharam ou PnL nulo)
    r_nonzero = r[np.abs(r) > 1e-9]
    wins = r_nonzero[r_nonzero > 0]
    losses = r_nonzero[r_nonzero < 0]

    sharpe_r = (r.mean() / (r.std() + 1e-12)) * (252 ** 0.5) if len(r) > 1 else 0.0
    downside = r[r < 0]
    sortino_r = (r.mean() / (downside.std() + 1e-12)) * (252 ** 0.5) if len(downside) > 1 else 0.0

    gross_win = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else 0.0

    return {
        "trades": len(trades),
        "sharpe_r": float(sharpe_r),
        "sortino_r": float(sortino_r),
        "win_rate": float(len(wins) / len(r_nonzero)) if len(r_nonzero) else 0.0,
        "profit_factor": float(pf),
        "avg_r": float(r.mean()),
        "expectancy_r": float(r.mean()),
        "vol_r": float(r.std()),
        "max_dd_pct": float(_max_dd(r)),
        "stability": float(_stability(trades)),
        "smoothness": float(_smoothness(pnl)),
        "skew": float(_skew(r)),
        "kurt": float(_kurt(r)),
        "total_pnl": float(pnl.sum()),
        "n_liquidations": int(sum(1 for t in trades if t.get("is_liquidation"))),
    }


def _max_dd(r):
    import numpy as np
    eq = np.cumsum(r)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    return float(dd.max()) if len(dd) else 0.0

def _stability(trades):
    import numpy as np
    r = np.array([t["r_multiple"] for t in trades])
    if len(r) < 2: return 0.5
    m, s = r.mean(), r.std()
    if s < 1e-12: return 1.0
    return float(((r > m - 2*s) & (r < m + 2*s)).mean())

def _smoothness(pnl):
    import numpy as np
    if len(pnl) < 2: return 0.5
    inc = np.diff(pnl)
    return float(max(0.0, 1.0 - inc.std() / (abs(pnl).mean() + 1e-12)))

def _skew(r):
    import numpy as np
    if len(r) < 3: return 0.0
    c = (r - r.mean()) / (r.std() + 1e-12)
    return float((c ** 3).mean())

def _kurt(r):
    import numpy as np
    if len(r) < 3: return 3.0
    c = (r - r.mean()) / (r.std() + 1e-12)
    return float((c ** 4).mean())


def persist_trades(address: str, trades: list):
    """Persiste trades GMX no SQLite (schema comum)."""
    if not trades:
        return 0
    c = db.conn()
    rows = []
    for t in trades:
        rows.append((
            address,
            datetime.fromtimestamp(t["exit_time"], tz=timezone.utc).isoformat(),
            t["market"],
            "SELL" if t["pnl"] > 0 else "BUY",  # placeholder
            t.get("dir", "TRADE"),
            None,  # liquidity
            t["collateral"],  # price slot? não — usar None e adaptar
            t["r_multiple"],
            t["volume"],
            t["fees"],
            None, None, None,
        ))
    # esta parte precisa adaptar o schema — placeholder
    c.close()
    return len(rows)


def main():
    from eth_utils import to_checksum_address   # D9: account_eq e' sensivel a caixa
    wallets_file = sys.argv[1] if len(sys.argv) > 1 else "wallets_gmx_all.txt"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    out_dir = Path("yaaf_payloads_gmx")
    out_dir.mkdir(exist_ok=True)

    tokens = load_tokens()
    markets = load_markets()

    # lê todos os endereços do master (normalizado para minúsculas)
    all_addrs = []
    master_meta = {}
    for line in Path(wallets_file).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # separa endereço do comentário
        if "#" in line:
            addr_part, comment = line.split("#", 1)
        else:
            addr_part, comment = line, ""
        addr_part = addr_part.strip()
        if not addr_part.startswith("0x") or len(addr_part) != 42:
            continue
        try:
            a = to_checksum_address(addr_part)   # D9: canonicaliza, nunca minusculiza
        except Exception:
            continue
        # parse do comentário: source=subsquid trades=19 pnl=-1010.59 liq=0
        meta = {}
        for token in comment.split():
            if "=" in token:
                k, v = token.split("=", 1)
                meta[k] = v
        master_meta[a.lower()] = meta        # chave em minuscula, valor em checksum
        all_addrs.append(a)

    # filtra só os que ainda não têm payload (case-insensitive)
    done = {f.stem.lower() for f in Path("yaaf_payloads_gmx").glob("*.json")
            if not f.stem.startswith("_")}
    addrs = []
    for a in all_addrs:
        if a.lower() in done:
            continue
        meta = master_meta.get(a.lower(), {})
        try:
            n = int(meta.get("trades", 0))
        except (ValueError, TypeError):
            n = 0
        # só processa se tem >= 5 trades registados
        if n >= 5:
            addrs.append(a)

    print(f"master: {len(all_addrs)} endereços · processados: {len(done)} · "
          f"faltando: {len(addrs)}")
    if not addrs:
        print("[ok] nada a fazer — todos processados")
        return

    results = []
    for i, addr in enumerate(addrs, 1):
        try:
            trades_raw = fetch_trader_trades(addr, tokens, markets, days=days)
            trades = group_by_lifecycle(trades_raw)
            metrics = compute_yaf_metrics(trades)
            payload = {
                "agent_id": addr,
                "source": "gmx",
                "ts": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics,
                "trades": trades[:500],  # cap
            }
            # só grava se tiver trades (evita poluir com vazios)
            if not metrics.get("trades"):
                print(f"  [{i}/{len(addrs)}] {addr[:12]} SKIP (0 trades)")
                continue
            (out_dir / f"{addr}.json").write_text(json.dumps(payload, indent=2, default=str))
            results.append(payload)
            print(f"  [{i}/{len(addrs)}] {addr[:12]} trades={metrics['trades']:>4} "
                  f"pnl=${metrics['total_pnl']:>12,.2f} wr={metrics['win_rate']*100:>5.1f}% "
                  f"liq={metrics['n_liquidations']}")
        except Exception as e:
            print(f"  [{i}/{len(addrs)}] {addr[:12]} ERRO: {e}")
        time.sleep(0.5)

    (out_dir / "_summary.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\n[ok] {len(results)} payloads em {out_dir}/")


if __name__ == "__main__":
    main()

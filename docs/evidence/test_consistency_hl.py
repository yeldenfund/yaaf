"""Testa estabilidade do YAAF na Hyperliquid."""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from metrics.r_multiples import fills_to_trades
from store import sqlite as db
from yaaf_score_v5_formal import yelden_score
from scipy.stats import spearmanr

N_WINDOWS = 4

def get_fills(addr):
    c = db.conn()
    rows = c.execute("""
        SELECT t, market, side, type, price, size, usd_notional, fee,
               position_side_before, position_size_before, entry_price_before
        FROM fills WHERE address=? ORDER BY t ASC
    """, (addr,)).fetchall()
    c.close()
    return [{"t": r[0], "market": r[1], "side": r[2], "dir": r[3],
             "price": r[4], "size": r[5], "usd_notional": r[6], "fee": r[7],
             "start_position": r[10] if r[10] is not None else 0.0} for r in rows]

def compute_yaaf(trades):
    if len(trades) < 10: return None
    pnls = np.array([t.get("pnl", 0) for t in trades], dtype=float)
    r = np.array([t.get("r_multiple", 0) for t in trades], dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 5: return None
    profits = [float(p) for p in pnls if np.isfinite(p)]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    metrics = {"trades": len(trades),
        "sharpe_r": float((r.mean()/(r.std()+1e-12))*np.sqrt(252)),
        "sortino_r": 0.0,
        "win_rate": float(len(r[r>0])/len(r)) if len(r) else 0,
        "profit_factor": float(sum(wins)/abs(sum(losses))) if losses else 99.0,
        "avg_r": float(r.mean()), "expectancy_r": float(r.mean()),
        "vol_r": float(r.std()), "max_dd_pct": 5.0,
        "stability": 0.5, "smoothness": 0.5, "skew": 0.0, "kurt": 3.0}
    state = {"ema": 300, "round_history": [], "total_trades": 0}
    try:
        r2 = yelden_score(metrics=metrics, state=state, trades=trades, initial_balance=11000.0)
        return r2["s_raw"] if r2 else None
    except Exception:
        return None

def compute_sharpe(trades):
    r = np.array([t.get("r_multiple", 0) for t in trades], dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 5: return None
    return float((r.mean()/(r.std()+1e-12))*np.sqrt(252))

def main():
    c = db.conn()
    addrs = [r[0] for r in c.execute(
        "SELECT address, COUNT(*) FROM fills WHERE address LIKE '0x%' "
        "GROUP BY address HAVING COUNT(*) >= 80").fetchall()]
    c.close()
    print(f"enderecos HL com >=80 fills: {len(addrs)}")
    agents = []
    for addr in addrs:
        fills = get_fills(addr)
        trades = sorted(fills_to_trades(fills), key=lambda x: x["exit_time"])
        if len(trades) < 40: continue
        ws = len(trades) // N_WINDOWS
        if ws < 10: continue
        yaafs, sharpes, ok = [], [], True
        for i in range(N_WINDOWS):
            w = trades[i*ws:(i+1)*ws]
            y, s = compute_yaaf(w), compute_sharpe(w)
            if y is None or s is None: ok = False; break
            yaafs.append(y); sharpes.append(s)
        if not ok: continue
        agents.append({"addr": addr, "yaafs": yaafs, "sharpes": sharpes})
    print(f"agentes com {N_WINDOWS} janelas: {len(agents)}")
    if len(agents) < 10: return
    yw = np.array([a["yaafs"] for a in agents])
    sw = np.array([a["sharpes"] for a in agents])
    yc, sc = [], []
    for i in range(N_WINDOWS):
        for j in range(i+1, N_WINDOWS):
            r1, _ = spearmanr(yw[:, i], yw[:, j])
            r2, _ = spearmanr(sw[:, i], sw[:, j])
            yc.append(r1); sc.append(r2)
    print(f"\n=== Estabilidade (HL) ===")
    print(f"YAAF:   {np.mean(yc):.3f}")
    print(f"Sharpe: {np.mean(sc):.3f}")
    print(f"Vencedor: {'YAAF' if np.mean(yc) > np.mean(sc) else 'Sharpe'}")
    ycv = np.std(yw, axis=1) / (np.abs(np.mean(yw, axis=1)) + 1e-9)
    scv = np.std(sw, axis=1) / (np.abs(np.mean(sw, axis=1)) + 1e-9)
    print(f"YAAF CV:   {np.mean(ycv):.3f}")
    print(f"Sharpe CV: {np.mean(scv):.3f}")
    Path("test_consistency_hl_result.json").write_text(json.dumps({
        "n_agents": len(agents),
        "yaaf_stability": float(np.mean(yc)),
        "sharpe_stability": float(np.mean(sc)),
        "yaaf_cv": float(np.mean(ycv)),
        "sharpe_cv": float(np.mean(scv)),
    }, indent=2))
    print("\n[ok] test_consistency_hl_result.json")

if __name__ == "__main__":
    main()

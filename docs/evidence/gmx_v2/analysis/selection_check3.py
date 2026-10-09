#!/usr/bin/env python3
"""
Tres perguntas que decidem como rotular o rho=0.2540.

1. O +0.46 da metade de baixo e so win rate? Mede o IC de cada componente
   dentro de cada grupo, e a correlacao entre S_RAW e cada componente.
2. Os ganhadores revertem? Mede PnL da descoberta x soma de R em T2 DENTRO de
   cada grupo (o +0.58 global e quase todo entre grupos).
3. O sinal da metade de baixo e classificatorio? Mede se o S_RAW separa quem
   tem soma de R positiva em T2 — a forma da Fase 2, nao uma correlacao.

Nao recalcula S_RAW. Imprime. Nao conclui.

Uso:
  python3 selection_check3.py docs/evidence/ic_test_gmx_v2_result.json wallets_gmx.txt
"""
import json
import re
import sys

import numpy as np
from scipy import stats

COMP = ["s_winrate", "s_stability", "s_pf_pct", "s_vol", "s_sharpe", "s_sortino",
        "s_pf", "s_avg_r", "s_expectancy", "s_smoothness", "s_mc"]


def sp(x, y, rot, largura=46):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 10 or len(set(x[ok])) < 3:
        print(f"  {rot:<{largura}} n={n:<4} (sem variacao suficiente)")
        return None
    r, p = stats.spearmanr(x[ok], y[ok])
    se = 1.0 / np.sqrt(n - 3)
    lo, hi = np.tanh(np.arctanh(r) - 1.96 * se), np.tanh(np.arctanh(r) + 1.96 * se)
    print(f"  {rot:<{largura}} n={n:<4} rho={r:+.4f}  p={p:.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]")
    return r


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    tab = json.load(open(sys.argv[1], encoding="utf-8"))["observacoes"]
    pat = re.compile(r"^(0x[0-9a-fA-F]{40})\s*#\s*pnl=(-?[\d.]+)\s+trades=(\d+)\s+liq=(\d+)")
    desc = [(m.group(1).lower(), float(m.group(2)))
            for m in (pat.match(l.strip()) for l in open(sys.argv[2], encoding="utf-8")) if m]
    meio = len(desc) // 2
    grupo = {a: ("topo" if i < meio else "base") for i, (a, _) in enumerate(desc)}
    dpnl = dict(desc)

    med = [{"g": grupo[str(o["agent"]).lower()], "s": float(o["s_raw"]),
            "r": float(o["sum_r_t2"]), "d": dpnl[str(o["agent"]).lower()],
            **{c: o.get(c) for c in COMP if c in o}}
           for o in tab if str(o["agent"]).lower() in grupo]
    print(f"join: {len(med)} de {len(tab)}\n")

    print("=== 1. IC de cada componente contra soma de R em T2, por grupo ===")
    for g in ("topo", "base"):
        sub = [m for m in med if m["g"] == g]
        print(f"\n  grupo {g} (n={len(sub)}):")
        sp([m["s"] for m in sub], [m["r"] for m in sub], "    S_RAW (referencia)")
        for c in COMP:
            if c in sub[0]:
                sp([m[c] for m in sub], [m["r"] for m in sub], f"    {c}")

    print("\n=== 1b. o S_RAW e um proxy de qual componente, dentro de cada grupo? ===")
    for g in ("topo", "base"):
        sub = [m for m in med if m["g"] == g]
        print(f"\n  grupo {g}:")
        for c in COMP:
            if c in sub[0]:
                sp([m["s"] for m in sub], [m[c] for m in sub], f"    S_RAW x {c}")

    print("\n=== 2. reversao: PnL da descoberta x soma de R em T2, DENTRO do grupo ===")
    sp([m["d"] for m in med], [m["r"] for m in med], "global (referencia)")
    for g in ("topo", "base"):
        sub = [m for m in med if m["g"] == g]
        sp([m["d"] for m in sub], [m["r"] for m in sub], f"[{g}]")

    print("\n=== 3. forma da Fase 2: o S_RAW separa quem tem soma de R > 0 em T2? ===")
    for g in ("topo", "base", None):
        sub = [m for m in med if g is None or m["g"] == g]
        rot = g or "todos"
        pos = [m for m in sub if m["r"] > 0]
        neg = [m for m in sub if m["r"] <= 0]
        if len(pos) < 5 or len(neg) < 5:
            print(f"  {rot:<8} n={len(sub):<4} pos={len(pos)} neg={len(neg)}  (celula pequena)")
            continue
        sp_, sn = [m["s"] for m in pos], [m["s"] for m in neg]
        u, pu = stats.mannwhitneyu(sp_, sn, alternative="two-sided")
        auc = u / (len(sp_) * len(sn))
        print(f"  {rot:<8} n={len(sub):<4} R>0: {len(pos):>3} (S_RAW mediana {np.median(sp_):6.2f})"
              f"   R<=0: {len(neg):>3} (mediana {np.median(sn):6.2f})"
              f"   AUC={auc:.3f}  p={pu:.4f}")
        for lim in (20.0, 30.0, 40.0):
            acima = [m for m in sub if m["s"] >= lim]
            abaixo = [m for m in sub if m["s"] < lim]
            if len(acima) >= 5 and len(abaixo) >= 5:
                ta = sum(1 for m in acima if m["r"] > 0) / len(acima)
                tb = sum(1 for m in abaixo if m["r"] > 0) / len(abaixo)
                print(f"           corte S_RAW {lim:>5.0f}: acima {len(acima):>3} agentes, "
                      f"{ta:5.1%} com R>0   |  abaixo {len(abaixo):>3}, {tb:5.1%} com R>0   "
                      f"diferenca {ta-tb:+.1%}")

    print("\nfim. nenhum veredito foi escrito neste script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

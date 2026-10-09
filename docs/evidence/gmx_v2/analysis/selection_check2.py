#!/usr/bin/env python3
"""
Dois diagnosticos sobre o resultado do selection_check.py.

(a) Restricao de amplitude no PREDITOR. Se o S_RAW quase nao varia na metade de
    cima, o rho=+0.0254 daquele grupo e artefato de amplitude, nao evidencia de
    que o score falha para agentes bons.

(b) Colisor por tamanho. A selecao foi em PnL em dolares, que e aproximadamente
    tamanho x R. Condicionar em |PnL| extremo induz relacao entre tamanho e R.
    Se o S_RAW tocar tamanho, herda uma relacao com R que nao e dele. Mede-se
    com rho(S_RAW, volume) e com a parcial de Spearman controlando volume.

Proxy de tamanho: volume_usd do gmx_discover_raw.json, se existir. Sem ele,
|pnl|/trades do wallets_gmx.txt, que e mais grosseiro e vem marcado na saida.

Nao recalcula S_RAW. Imprime. Nao conclui.

Uso:
  python3 selection_check2.py docs/evidence/ic_test_gmx_v2_result.json \
                              wallets_gmx.txt [gmx_discover_raw.json]
"""
import json
import re
import sys

import numpy as np
from scipy import stats

COMPONENTES = ["s_sharpe", "s_sortino", "s_winrate", "s_pf", "s_avg_r", "s_expectancy",
               "s_vol", "s_stability", "s_smoothness", "s_pf_pct", "s_mc"]


def sp(x, y, rot):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 10:
        print(f"  {rot:<48} n={n:<4} (menos de 10)")
        return
    r, p = stats.spearmanr(x[ok], y[ok])
    se = 1.0 / np.sqrt(n - 3)
    lo, hi = np.tanh(np.arctanh(r) - 1.96 * se), np.tanh(np.arctanh(r) + 1.96 * se)
    print(f"  {rot:<48} n={n:<4} rho={r:+.4f}  p={p:.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]")


def parcial(x, y, z, rot):
    """Spearman parcial: rankeia os tres, remove a projecao linear de z dos dois."""
    x, y, z = (np.asarray(v, float) for v in (x, y, z))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    n = int(ok.sum())
    if n < 15:
        print(f"  {rot:<48} n={n:<4} (menos de 15)")
        return
    rx, ry, rz = (stats.rankdata(v[ok]) for v in (x, y, z))
    rz = np.column_stack([np.ones(n), rz])
    ex = rx - rz @ np.linalg.lstsq(rz, rx, rcond=None)[0]
    ey = ry - rz @ np.linalg.lstsq(rz, ry, rcond=None)[0]
    r, _ = stats.pearsonr(ex, ey)
    se = 1.0 / np.sqrt(n - 4)          # um grau a menos pelo controle
    lo, hi = np.tanh(np.arctanh(r) - 1.96 * se), np.tanh(np.arctanh(r) + 1.96 * se)
    print(f"  {rot:<48} n={n:<4} rho={r:+.4f}            IC95 [{lo:+.4f}, {hi:+.4f}]")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    res = json.load(open(sys.argv[1], encoding="utf-8"))
    tab = res["observacoes"]

    pat = re.compile(r"^(0x[0-9a-fA-F]{40})\s*#\s*pnl=(-?[\d.]+)\s+trades=(\d+)\s+liq=(\d+)")
    desc = []
    for linha in open(sys.argv[2], encoding="utf-8"):
        m = pat.match(linha.strip())
        if m:
            desc.append((m.group(1).lower(), float(m.group(2)), int(m.group(3)), int(m.group(4))))
    meio = len(desc) // 2
    grupo = {a: ("topo" if i < meio else "base") for i, (a, *_) in enumerate(desc)}
    dpnl = {a: p for a, p, _, _ in desc}
    dliq = {a: l for a, _, _, l in desc}

    tam, fonte = {}, None
    if len(sys.argv) > 3:
        try:
            for t in json.load(open(sys.argv[3], encoding="utf-8")):
                tam[t["address"].lower()] = float(t["volume_usd"])
            fonte = f"volume_usd de {sys.argv[3]}"
        except Exception as e:
            print(f"(raw json nao utilizavel: {e})")
    if not tam:
        for a, p, n, _ in desc:
            tam[a] = abs(p) / n if n else np.nan
        fonte = "|pnl|/trades do wallets_gmx.txt  <-- proxy GROSSEIRO"
    print(f"proxy de tamanho: {fonte}\n")

    med = []
    for o in tab:
        a = str(o["agent"]).lower()
        if a in grupo:
            med.append({"a": a, "g": grupo[a], "s": float(o["s_raw"]),
                        "r": float(o["sum_r_t2"]), "mr": float(o["mean_r_t2"]),
                        "pl": float(o["sum_pnl_t2"]), "d": dpnl[a],
                        "z": tam.get(a, np.nan), "liq": dliq[a],
                        "n1": o.get("n_t1"), "n2": o.get("n_t2"),
                        "comp": {c: o.get(c) for c in COMPONENTES if c in o}})
    print(f"join: {len(med)} de {len(tab)}\n")

    print("=== (a) dispersao do PREDITOR por grupo ===")
    print(f"  {'grupo':<8} {'n':>4} {'min':>8} {'p25':>8} {'mediana':>8} {'p75':>8} "
          f"{'max':>8} {'sd':>8} {'IQR':>8}")
    for g in ("topo", "base", None):
        v = np.array([m["s"] for m in med if g is None or m["g"] == g])
        rot = g or "todos"
        q = np.percentile(v, [25, 50, 75])
        print(f"  {rot:<8} {len(v):>4} {v.min():>8.2f} {q[0]:>8.2f} {q[1]:>8.2f} "
              f"{q[2]:>8.2f} {v.max():>8.2f} {v.std(ddof=1):>8.2f} {q[2]-q[0]:>8.2f}")
    print("\n  componentes em zero, por grupo (quantos agentes, de n):")
    for g in ("topo", "base"):
        sub = [m for m in med if m["g"] == g]
        if not sub or not sub[0]["comp"]:
            continue
        linha = []
        for c in sub[0]["comp"]:
            z = sum(1 for m in sub if (m["comp"].get(c) or 0) < 1e-9)
            linha.append(f"{c.replace('s_',''):>10}={z:>3}/{len(sub)}")
        for i in range(0, len(linha), 4):
            print(f"  {g:<6} " + "  ".join(linha[i:i+4]))

    print("\n=== (b) o preditor toca tamanho? ===")
    sp([m["s"] for m in med], [m["z"] for m in med], "S_RAW x tamanho (global)")
    for g in ("topo", "base"):
        sub = [m for m in med if m["g"] == g]
        sp([m["s"] for m in sub], [m["z"] for m in sub], f"S_RAW x tamanho [{g}]")
    sp([m["z"] for m in med], [m["r"] for m in med], "tamanho x soma R em T2 (global)")
    sp([m["z"] for m in med], [m["d"] for m in med], "tamanho x PnL da descoberta (global)")

    print("\n=== (b) parcial: S_RAW x soma R em T2, controlando tamanho ===")
    parcial([m["s"] for m in med], [m["r"] for m in med], [m["z"] for m in med],
            "global, controlando tamanho")
    for g in ("topo", "base"):
        sub = [m for m in med if m["g"] == g]
        sp([m["s"] for m in sub], [m["r"] for m in sub], f"[{g}] sem controle (referencia)")
        parcial([m["s"] for m in sub], [m["r"] for m in sub], [m["z"] for m in sub],
                f"[{g}] controlando tamanho")

    print("\n=== por tercil de tamanho dentro da metade de baixo ===")
    sub = [m for m in med if m["g"] == "base" and np.isfinite(m["z"])]
    if len(sub) >= 30:
        cortes = np.percentile([m["z"] for m in sub], [33.333, 66.667])
        for i, rot in enumerate(("tamanho baixo", "tamanho medio", "tamanho alto")):
            if i == 0:
                k = [m for m in sub if m["z"] <= cortes[0]]
            elif i == 1:
                k = [m for m in sub if cortes[0] < m["z"] <= cortes[1]]
            else:
                k = [m for m in sub if m["z"] > cortes[1]]
            sp([m["s"] for m in k], [m["r"] for m in k], f"S_RAW x soma R  [base/{rot}]")

    print("\n=== contexto: o que mais difere entre os grupos ===")
    for campo, rot in (("n1", "trades em T1"), ("n2", "trades em T2"),
                       ("liq", "liquidacoes na descoberta")):
        for g in ("topo", "base"):
            v = [m[campo] for m in med if m["g"] == g and m[campo] is not None]
            if v:
                print(f"  {rot:<28} {g:<6} mediana={np.median(v):>10.1f}  media={np.mean(v):>10.1f}")

    print("\nfim. nenhum veredito foi escrito neste script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

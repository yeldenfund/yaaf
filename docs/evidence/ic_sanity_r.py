#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ic_sanity_r.py — testa a integridade do alvo primario (r_multiple) e explica
o agente que pontuou S_RAW = 0.

Duas perguntas, nessa ordem de importancia:

  A) O `r_multiple` dos payloads e' bem formado? Se o denominador (colateral)
     chega perto de zero em alguns trades, |R| infla artificialmente e o alvo
     primario carrega erro de medicao. Isso contaminaria o rho=0.6577 inteiro,
     nao so um agente.

  B) Qual gate zerou 0x3855808A...? Com 35 trades em T1 e sem excecao, o zero
     e' calculado. Interessa saber se foi penalidade estourando o core ou
     axioma de volume.

A secao (C) e' SENSIBILIDADE, nao resultado. O numero reportado continua sendo
o pre-registrado em IC_PROTOCOL.md. Remover agente e winsorizar depois de ver
o resultado seria exatamente o que o protocolo proibe; o que se faz com uma
sensibilidade e' declarar se o achado e' fragil, nunca trocar o headline.

Rodar de /root/aiagentregistry-observatory.
"""
import json
import sys
from pathlib import Path

OBS = Path("/root/aiagentregistry-observatory")
SCORER = Path("/root/yaaf/scorer")
EVID = Path("docs/evidence")

for p in (str(OBS), str(SCORER), str(EVID)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ic_test_gmx import spearman, INITIAL_BALANCE              # noqa: E402
from feed_yaaf_gmx import compute_yaf_metrics                  # noqa: E402
from yaaf_score_v5_formal import (                             # noqa: E402
    yelden_score, enrich_metrics_from_trades,
)

ZERO = "0x3855808A7f42DbaeBacf07291e0AE0A7ED692eCb"


def q(v, p):
    v = sorted(v)
    if not v:
        return float("nan")
    i = p * (len(v) - 1)
    lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def finito(x):
    try:
        x = float(x)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def payloads():
    out = {}
    for f in sorted((OBS / "yaaf_payloads_gmx").glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("trades"), list):
            out[d.get("agent_id", "?")] = d
    return out


def main():
    res = json.loads((EVID / "ic_test_gmx_result.json").read_text())
    obs = res["observacoes"]
    corte = float(res["corte_exit_time"])
    pls = payloads()
    medidos = [o["agent"] for o in obs]
    print(f"agentes medidos: {len(medidos)}   corte: {res['corte_data']}\n")

    # ─────────────────────────────────────────────────────────────────────────
    print("=" * 72)
    print("A) INTEGRIDADE DO r_multiple NOS TRADES DE T2")
    print("=" * 72)

    rs, cols, pares, extremos = [], [], [], []
    sem_col = 0
    for a in medidos:
        d = pls.get(a)
        if not d:
            continue
        for t in d["trades"]:
            et = finito(t.get("exit_time"))
            if et is None or et < corte:
                continue
            r = finito(t.get("r_multiple"))
            c = finito(t.get("collateral"))
            pnl = finito(t.get("pnl"))
            if r is None:
                continue
            rs.append(r)
            if c is None or c == 0:
                sem_col += 1
            else:
                cols.append(c)
                pares.append((abs(r), c))
                if pnl is not None:
                    extremos.append((abs(r), r, c, pnl, pnl / c, a))

    print(f"trades em T2 com r_multiple: {len(rs)}")
    print(f"  sem colateral utilizavel : {sem_col}")
    if rs:
        print(f"  R  min/p01/p25/med/p75/p99/max:")
        print(f"     {min(rs):+.3f} / {q(rs,.01):+.3f} / {q(rs,.25):+.3f} / "
              f"{q(rs,.50):+.3f} / {q(rs,.75):+.3f} / {q(rs,.99):+.3f} / {max(rs):+.3f}")
        for lim in (3, 5, 10, 25):
            n = sum(1 for r in rs if abs(r) > lim)
            print(f"     |R| > {lim:<3} : {n:4d}  ({100*n/len(rs):5.2f}%)")
    if cols:
        print(f"  colateral min/p01/med/max: {min(cols):.4f} / {q(cols,.01):.4f} / "
              f"{q(cols,.50):.4f} / {max(cols):.4f}")

    if len(pares) > 4:
        rho, p, lo, hi = spearman([x[0] for x in pares], [x[1] for x in pares])
        pp = f"{p:.4g}" if p is not None else "—"
        print(f"\n  |R| ~ colateral : rho={rho:+.4f}  p={pp}  n={len(pares)}")
        print("  Hipotese do denominador: rho fortemente NEGATIVO = |R| grande")
        print("  aparece onde o colateral e' pequeno. Isso e' artefato, nao sinal.")

    # r_multiple declarado confere com pnl/colateral?
    if extremos:
        difs = [abs(e[1] - e[4]) for e in extremos]   # |r_multiple - pnl/colateral|
        print(f"\n  |r_multiple - pnl/colateral| med/p99/max: "
              f"{q(difs,.50):.4f} / {q(difs,.99):.4f} / {max(difs):.4f}")
        print("  Se a mediana for ~0, r_multiple = pnl/colateral e o risco por")
        print("  trade e' o colateral. Se divergir muito, o denominador e' outro")
        print("  e precisa ser documentado antes de usar R como alvo.")

        print("\n  10 maiores |R| em T2:")
        extremos.sort(reverse=True)
        print(f"    {'R':>10} {'colateral':>12} {'pnl':>12} {'pnl/col':>10}  agente")
        for ar, r, c, pnl, imp, a in extremos[:10]:
            print(f"    {r:>+10.3f} {c:>12.4f} {pnl:>+12.2f} {imp:>+10.3f}  {a[:14]}…")

    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print(f"B) POR QUE {ZERO[:14]}… PONTUOU 0")
    print("=" * 72)
    d = pls.get(ZERO)
    if not d:
        print("  payload nao encontrado")
    else:
        t1 = [t for t in d["trades"]
              if finito(t.get("exit_time")) is not None
              and finito(t["exit_time"]) < corte]
        m = compute_yaf_metrics(t1)
        print(f"  trades em T1: {len(t1)}")
        print("\n  compute_yaf_metrics(T1):")
        for k in sorted(m):
            v = m[k]
            print(f"    {k:18} = {v:.6f}" if isinstance(v, float) else f"    {k:18} = {v}")
        m2 = enrich_metrics_from_trades(dict(m), t1)
        novos = {k: m2[k] for k in m2 if k not in m}
        if novos:
            print("\n  enrich_metrics_from_trades acrescentou:")
            for k in sorted(novos):
                v = novos[k]
                print(f"    {k:18} = {v:.6f}" if isinstance(v, float) else f"    {k:18} = {v}")
        r = yelden_score(metrics=m2,
                         state={"ema": 300.0, "round_history": [], "total_trades": 0},
                         trades=t1, initial_balance=INITIAL_BALANCE)
        print("\n  yelden_score() completo:")
        print(json.dumps(r, indent=4, default=str, sort_keys=True))

    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("C) SENSIBILIDADE — NAO SUBSTITUI O NUMERO REPORTADO")
    print("=" * 72)
    s = [o["sraw_t1"] for o in obs]
    sr = [o["sum_r_t2"] for o in obs]
    base = spearman(s, sr)[0]
    print(f"  pre-registrado (primario)        rho={base:+.4f}  n={len(obs)}")

    keep = [o for o in obs if o["agent"] != ZERO]
    rho = spearman([o["sraw_t1"] for o in keep], [o["sum_r_t2"] for o in keep])[0]
    print(f"  sem o agente de S_RAW=0          rho={rho:+.4f}  n={len(keep)}  "
          f"(delta {rho-base:+.4f})")

    # winsorizacao do alvo nos percentis 5/95
    lo, hi = q(sr, .05), q(sr, .95)
    w = [min(max(v, lo), hi) for v in sr]
    rho = spearman(s, w)[0]
    print(f"  alvo winsorizado em p05/p95      rho={rho:+.4f}  n={len(obs)}  "
          f"(delta {rho-base:+.4f})")
    print("\n  Winsorizar quase nao deve mexer: Spearman usa postos, e winsorizar")
    print("  preserva ordem. Se mexer muito, ha empates sendo criados nas pontas.")
    print("  Leitura honesta: deltas pequenos = achado robusto; delta grande ao")
    print("  remover UM agente de 31 = achado fragil, e isso vai no protocolo.")

    out = EVID / "ic_sanity_r_result.json"
    out.write_text(json.dumps({
        "n_trades_t2": len(rs),
        "sem_colateral": sem_col,
        "r_p01": q(rs, .01) if rs else None,
        "r_p99": q(rs, .99) if rs else None,
        "r_min": min(rs) if rs else None,
        "r_max": max(rs) if rs else None,
        "abs_r_maior_que": {str(l): sum(1 for r in rs if abs(r) > l) for l in (3, 5, 10, 25)},
        "rho_absR_colateral": spearman([x[0] for x in pares], [x[1] for x in pares])[0]
                              if len(pares) > 4 else None,
        "sensibilidade": {
            "pre_registrado": base,
            "sem_agente_zero": spearman([o["sraw_t1"] for o in keep],
                                        [o["sum_r_t2"] for o in keep])[0],
            "winsorizado_p05_p95": spearman(s, w)[0],
        },
    }, indent=2, default=str))
    print(f"\n[ok] {out}")


if __name__ == "__main__":
    main()

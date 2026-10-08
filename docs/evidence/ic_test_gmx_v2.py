#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ic_test_gmx_v2.py — medicao canonica do YAAF no universo corrigido.

Implementa docs/IC_PROTOCOL_v2.md, congelado em 2026-10-08 ANTES desta execucao.
Nao modificar sem emitir v3 do protocolo.

Faz tudo que o v2 exige, num arquivo so:
  1. tres horizontes pre-registrados (primario = soma de R em T2)
  2. IC por componente com correcao BH e BHY
  3. dimensionalidade efetiva
  4. teste pre-registrado do componente 8: implementado vs formula da Spec
  5. sensibilidade leave-one-out e winsorizacao
  6. cobertura temporal e contagem de descartes

NAO escreve veredito. Computa e imprime; a conclusao e' de quem le. Quatro
vereditos automaticos escritos nesta serie de scripts sairam errados com
numeros certos, todos em pontos onde a conclusao foi codificada antes de
existir dado real.

Principio de desenho, herdado do v1: nada de metricas reimplementadas. Importa
`compute_yaf_metrics` do coletor de producao e o scorer. A unica coisa
calculada aqui e' a estabilidade segundo a Spec, que nao existe em producao e
entra como VARIAVEL CANDIDATA medida ao lado, nunca alimentada no score.

Rodar de /root/aiagentregistry-observatory.
"""
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OBS = Path("/root/aiagentregistry-observatory")
SCORER = Path("/root/yaaf/scorer")
EVID = Path("docs/evidence")
OUT = EVID / "ic_test_gmx_v2_result.json"

# docs/evidence PRIMEIRO: existe outra ic_test_gmx.py fora dele, nao canonica.
for _p in (str(EVID), str(OBS), str(SCORER)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ic_test_gmx                                              # noqa: E402
if not hasattr(ic_test_gmx, "spearman"):
    sys.exit(f"ABORTADO: {ic_test_gmx.__file__} nao e' o modulo canonico.")
from ic_test_gmx import spearman, INITIAL_BALANCE                # noqa: E402
from feed_yaaf_gmx import compute_yaf_metrics                    # noqa: E402
from yaaf_score_v5_formal import (                               # noqa: E402
    yelden_score, enrich_metrics_from_trades, VERSION_SCORE,
)

PAYLOADS = OBS / "yaaf_payloads_gmx"
WALLETS = OBS / "wallets_gmx.txt"
MIN_T1, MIN_T2 = 30, 10

COMPONENTES = [
    ("s_sharpe", "1  Sharpe x PSR"), ("s_sortino", "2  Sortino"),
    ("s_winrate", "3  Win rate"), ("s_pf", "4  Profit factor"),
    ("s_avg_r", "5  Avg R"), ("s_expectancy", "6  Expectancy"),
    ("s_vol", "7  Inv. volatility"), ("s_stability", "8  Stability2"),
    ("s_smoothness", "9  Smoothness2"), ("s_pf_pct", "10 PF percentile"),
    ("s_mc", "11 Market context"),
]
EXTRAS = [("cvar_pen", "pen CVaR"), ("dd_penalty", "pen MaxDD"), ("dsr", "PSR")]


# ── estabilidade segundo a Spec Formal ─────────────────────────────────────
# Convencao DECLARADA no protocolo v2, antes desta execucao:
#   Sharpe mensal = media(R)/desvio(R) dentro do mes calendario, SEM anualizar.
#   Meses com menos de 2 trades sao descartados.
#   sigma_mSharpe = desvio populacional desses Sharpes mensais.
#   Agentes com menos de 2 meses utilizaveis -> None, reportados a parte,
#   sem valor substituto inventado.
def stability_spec(trades):
    por_mes = defaultdict(list)
    for t in trades:
        et = t.get("exit_time")
        r = t.get("r_multiple")
        if et is None or r is None:
            continue
        try:
            r = float(r)
            if not math.isfinite(r):
                continue
            d = datetime.fromtimestamp(float(et), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
        por_mes[(d.year, d.month)].append(r)
    sharpes = []
    for _, rs in sorted(por_mes.items()):
        if len(rs) < 2:
            continue
        a = np.array(rs, dtype=float)
        s = a.std()
        sharpes.append(float(a.mean() / s) if s > 1e-12 else 0.0)
    if len(sharpes) < 2:
        return None, len(sharpes)
    sigma = float(np.std(sharpes))
    return (1.0 / (1.0 + sigma)) ** 2 * 100.0, len(sharpes)


def bh_adjust(p, c=1.0):
    m = len(p)
    idx = sorted(range(m), key=lambda i: p[i])
    adj, prev = [1.0] * m, 1.0
    for rank in range(m, 0, -1):
        i = idx[rank - 1]
        prev = min(prev, min(1.0, p[i] * m * c / rank))
        adj[i] = prev
    return adj


def q(v, p):
    v = sorted(v)
    if not v:
        return float("nan")
    i = p * (len(v) - 1)
    lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def git_hash(d):
    try:
        return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def main():
    # ── universo declarado ─────────────────────────────────────────────────
    declarados = set()
    if WALLETS.exists():
        for l in WALLETS.read_text().splitlines():
            a = l.split("#")[0].strip()
            if a.startswith("0x") and len(a) == 42:
                declarados.add(a.lower())
    print(f"universo declarado ({WALLETS.name}): {len(declarados)} enderecos")

    arquivos = [f for f in sorted(PAYLOADS.glob("*.json")) if not f.stem.startswith("_")]
    fora = [f.stem for f in arquivos if f.stem.lower() not in declarados]
    if fora:
        print(f"  [ALERTA] {len(fora)} payload(s) fora do universo declarado — EXCLUIDOS")
    arquivos = [f for f in arquivos if f.stem.lower() in declarados]

    payloads, todos_ts = [], []
    for f in arquivos:
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if not (isinstance(d, dict) and isinstance(d.get("trades"), list)):
            continue
        d["_stem"] = f.stem
        payloads.append(d)
        todos_ts += [float(t["exit_time"]) for t in d["trades"]
                     if t.get("exit_time") is not None]
    print(f"payloads no universo: {len(payloads)}   trades: {len(todos_ts)}")
    if not todos_ts:
        print("sem trades"); return 1

    corte = float(np.median(todos_ts))
    fmt = lambda x: datetime.fromtimestamp(x, tz=timezone.utc).isoformat()
    print(f"janela: {fmt(min(todos_ts))[:10]} -> {fmt(max(todos_ts))[:10]}")
    print(f"corte (mediana global): {fmt(corte)}")
    print(f"  T1 {(corte-min(todos_ts))/86400:.1f} dias · T2 {(max(todos_ts)-corte)/86400:.1f} dias")

    # ── por agente ─────────────────────────────────────────────────────────
    obs, desc = [], {"sem_trades": 0, "t1_curto": 0, "t2_curto": 0, "sraw_nulo": 0}
    for p in payloads:
        tr = [t for t in p["trades"] if t.get("exit_time") is not None]
        if not tr:
            desc["sem_trades"] += 1; continue
        t1 = [t for t in tr if float(t["exit_time"]) < corte]
        t2 = [t for t in tr if float(t["exit_time"]) >= corte]
        if len(t1) < MIN_T1:
            desc["t1_curto"] += 1; continue
        if len(t2) < MIN_T2:
            desc["t2_curto"] += 1; continue
        m = compute_yaf_metrics(t1)
        if not m.get("trades"):
            desc["sraw_nulo"] += 1; continue
        m = enrich_metrics_from_trades(m, t1)
        try:
            res = yelden_score(metrics=m,
                               state={"ema": 300.0, "round_history": [], "total_trades": 0},
                               trades=t1, initial_balance=INITIAL_BALANCE)
        except Exception:
            desc["sraw_nulo"] += 1; continue
        if not res or res.get("s_raw") is None:
            desc["sraw_nulo"] += 1; continue

        spec_st, n_meses_uteis = stability_spec(t1)
        meses = len({(datetime.fromtimestamp(float(t["exit_time"]), tz=timezone.utc).year,
                      datetime.fromtimestamp(float(t["exit_time"]), tz=timezone.utc).month)
                     for t in t1})
        rs = [float(t.get("r_multiple", 0.0)) for t in t2]
        rs = [v for v in rs if math.isfinite(v)]
        pn = [float(t.get("pnl", 0.0)) for t in t2]
        pn = [v for v in pn if math.isfinite(v)]
        row = {"agent": p.get("agent_id", p["_stem"]),
               "n_t1": len(t1), "n_t2": len(t2),
               "meses_t1": meses, "meses_uteis": n_meses_uteis,
               "s_raw": float(res["s_raw"]),
               "stability_spec": spec_st,
               "sum_r_t2": float(sum(rs)),
               "mean_r_t2": float(sum(rs)/len(rs)) if rs else 0.0,
               "sum_pnl_t2": float(sum(pn))}
        for k, _ in COMPONENTES + EXTRAS:
            v = res.get(k)
            row[k] = float(v) if isinstance(v, (int, float)) else None
        obs.append(row)

    n = len(obs)
    print(f"\ndescartes: {desc}")
    print(f"agentes medidos: {n}")
    if n < 10:
        print("amostra pequena demais"); return 1

    # ── horizontes ─────────────────────────────────────────────────────────
    s = [o["s_raw"] for o in obs]
    print("\n" + "=" * 72)
    print("HORIZONTES PRE-REGISTRADOS")
    print("=" * 72)
    resultados = {}
    for nome, chave in (("primario_soma_r", "sum_r_t2"),
                        ("secundario_media_r", "mean_r_t2"),
                        ("terciario_pnl_abs", "sum_pnl_t2")):
        rho, p_, lo, hi = spearman(s, [o[chave] for o in obs])
        resultados[nome] = {"rho": rho, "p": p_, "ic95_lo": lo, "ic95_hi": hi, "n": n}
        ic = f"[{lo:.4f}, {hi:.4f}]" if lo is not None else "—"
        pp = f"{p_:.4g}" if p_ is not None else "—"
        print(f"  {nome:22} rho={rho:+.4f}  p={pp:>10}  IC95% {ic}")

    # ── cobertura ──────────────────────────────────────────────────────────
    mm = sorted(o["meses_t1"] for o in obs)
    print("\n" + "=" * 72)
    print("COBERTURA TEMPORAL DE T1")
    print("=" * 72)
    print(f"  meses distintos min/p10/mediana/p90/max: "
          f"{mm[0]} / {q(mm,.10):.0f} / {q(mm,.50):.0f} / {q(mm,.90):.0f} / {mm[-1]}")
    for k in (2, 3, 6):
        c = sum(1 for x in mm if x >= k)
        print(f"  com >= {k} meses: {c}/{n} ({100*c/n:.1f}%)")

    # ── IC por componente ──────────────────────────────────────────────────
    alvo = [o["sum_r_t2"] for o in obs]
    comp, ps, nomes = {}, [], []
    for k, rot in COMPONENTES + EXTRAS:
        v = [o[k] for o in obs]
        ok = [i for i, x in enumerate(v) if x is not None and math.isfinite(x)]
        if len(ok) < 5:
            comp[k] = {"rotulo": rot, "status": "ausente", "n": len(ok)}; continue
        vv = [v[i] for i in ok]
        if max(vv) - min(vv) < 1e-12:
            comp[k] = {"rotulo": rot, "status": "constante", "valor": vv[0], "n": len(ok)}
            continue
        rho, p_, lo, hi = spearman(vv, [alvo[i] for i in ok])
        comp[k] = {"rotulo": rot, "rho": rho, "p_raw": p_, "ic95_lo": lo,
                   "ic95_hi": hi, "n": len(ok)}
        if p_ is not None:
            ps.append(p_); nomes.append(k)
    if ps:
        m_ = len(ps); cm = sum(1.0/i for i in range(1, m_+1))
        bh, bhy = bh_adjust(ps, 1.0), bh_adjust(ps, cm)
        for i, k in enumerate(nomes):
            comp[k]["p_bh"], comp[k]["p_bhy"] = bh[i], bhy[i]
        print("\n" + "=" * 72)
        print(f"IC POR COMPONENTE   n={n}   {m_} testes   c({m_})={cm:.4f}")
        print("=" * 72)
        print(f"  {'componente':<20} {'rho':>8} {'p_raw':>9} {'p_BH':>8} {'p_BHY':>8}")
        for k, rot in COMPONENTES + EXTRAS:
            r = comp[k]
            if "status" in r:
                print(f"  {rot:<20} {'—':>8} {'—':>9} {'—':>8} {'—':>8}  "
                      f"{r['status'].upper()} {r.get('valor','')}")
            else:
                print(f"  {rot:<20} {r['rho']:>+8.4f} {r['p_raw']:>9.4g} "
                      f"{r['p_bh']:>8.4f} {r['p_bhy']:>8.4f}")

    # ── teste pre-registrado do componente 8 ───────────────────────────────
    print("\n" + "=" * 72)
    print("COMPONENTE 8 — TESTE PRE-REGISTRADO (IC_PROTOCOL_v2.md)")
    print("=" * 72)
    com_spec = [i for i, o in enumerate(obs) if o["stability_spec"] is not None]
    sem_spec = n - len(com_spec)
    print(f"  agentes com sigma_mSharpe definido : {len(com_spec)}/{n}")
    print(f"  agentes com < 2 meses utilizaveis  : {sem_spec}  (sem valor substituto)")
    c8 = {"n_com_spec": len(com_spec), "n_sem_spec": sem_spec}
    if len(com_spec) >= 10:
        sub_s = [obs[i]["s_raw"] for i in com_spec]
        sub_a = [obs[i]["sum_r_t2"] for i in com_spec]
        impl = [obs[i]["s_stability"] for i in com_spec]
        spec = [obs[i]["stability_spec"] for i in com_spec]
        for rot, v, key in (("implementada (+/-2 sigma)", impl, "implementada"),
                            ("Spec ((1/(1+sig_m))^2) ", spec, "spec")):
            if v and max(v) - min(v) > 1e-12:
                rho, p_, lo, hi = spearman(v, sub_a)
                c8[key] = {"rho": rho, "p": p_, "ic95_lo": lo, "ic95_hi": hi,
                           "n": len(com_spec)}
                print(f"  {rot}  rho={rho:+.4f}  p={p_:.4g}" if p_ is not None
                      else f"  {rot}  rho={rho:+.4f}")
            else:
                c8[key] = {"status": "constante"}
                print(f"  {rot}  CONSTANTE")
        r2, _, _, _ = spearman(impl, spec)
        c8["rho_entre_as_duas"] = r2
        print(f"  correlacao entre as duas formas        rho={r2:+.4f}")
        print("\n  Regra declarada antes da execucao: trocar o componente so se a")
        print("  forma da Spec mostrar IC significativamente melhor apos BHY.")
        print("  Igual ou pior, fica como esta e a divergencia vira limitacao.")

    # ── dimensionalidade ───────────────────────────────────────────────────
    uteis = [k for k, _ in COMPONENTES if "status" not in comp[k]]
    dim = {"nota": "menos de 2 componentes com variancia"}
    if len(uteis) >= 2:
        M = [[o[k] for o in obs] for k in uteis]
        R = [[1.0]*len(uteis) for _ in uteis]
        for i in range(len(uteis)):
            for j in range(i+1, len(uteis)):
                R[i][j] = R[j][i] = spearman(M[i], M[j])[0]
        ev = sorted(np.linalg.eigvalsh(np.array(R)).tolist(), reverse=True)
        pct = [100.0*e/sum(ev) for e in ev]
        cum, n90 = 0.0, len(ev)
        for i, x in enumerate(pct, 1):
            cum += x
            if cum >= 90.0:
                n90 = i; break
        print("\n" + "=" * 72)
        print("DIMENSIONALIDADE EFETIVA")
        print("=" * 72)
        print(f"  componentes com variancia: {len(uteis)} de 11")
        print(f"  variancia explicada (%)  : {[round(x,1) for x in pct]}")
        print(f"  fatores para 90%         : {n90}")
        acima = [(abs(R[i][j]), uteis[i], uteis[j], R[i][j])
                 for i in range(len(uteis)) for j in range(i+1, len(uteis))
                 if abs(R[i][j]) > 0.90]
        acima.sort(reverse=True)
        for _, a_, b_, r_ in acima:
            print(f"    {a_:<14} x {b_:<14} rho={r_:+.4f}")
        dim = {"componentes": uteis, "autovalores": ev, "variancia_pct": pct,
               "fatores_90pct": n90,
               "pares_acima_090": [{"a": a_, "b": b_, "rho": r_} for _, a_, b_, r_ in acima]}

    # ── sensibilidade ──────────────────────────────────────────────────────
    base = resultados["primario_soma_r"]["rho"]
    loo = [spearman([s[j] for j in range(n) if j != i],
                    [alvo[j] for j in range(n) if j != i])[0] - base for i in range(n)]
    pior = max(range(n), key=lambda i: abs(loo[i]))
    lo_t, hi_t = q(alvo, .05), q(alvo, .95)
    rho_w = spearman(s, [min(max(v, lo_t), hi_t) for v in alvo])[0]
    print("\n" + "=" * 72)
    print("SENSIBILIDADE")
    print("=" * 72)
    print(f"  primario                     rho={base:+.4f}")
    print(f"  leave-one-out, maior |delta| {abs(loo[pior]):.4f}  "
          f"(removendo {obs[pior]['agent'][:14]}…)")
    print(f"  winsorizado p05/p95          rho={rho_w:+.4f}  "
          f"(delta {rho_w-base:+.4f})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "protocolo": "IC_PROTOCOL_v2.md (congelado 2026-10-08)",
        "scorer": str(SCORER / "yaaf_score_v5_formal.py"),
        "scorer_version": VERSION_SCORE,
        "scorer_commit": git_hash(SCORER.parent),
        "observatory_commit": git_hash(OBS),
        "universo": {"arquivo": str(WALLETS), "declarados": len(declarados),
                     "payloads_no_universo": len(payloads),
                     "payloads_excluidos_fora_do_universo": len(fora)},
        "rodado_em": datetime.now(timezone.utc).isoformat(),
        "corte": corte, "corte_data": fmt(corte),
        "janela": {"inicio": fmt(min(todos_ts)), "fim": fmt(max(todos_ts)),
                   "t1_dias": (corte-min(todos_ts))/86400,
                   "t2_dias": (max(todos_ts)-corte)/86400},
        "min_trades_t1": MIN_T1, "min_trades_t2": MIN_T2,
        "descartes": desc, "n": n,
        "resultados": resultados,
        "componentes": comp,
        "componente_8_teste": c8,
        "dimensionalidade": dim,
        "sensibilidade": {"leave_one_out_max": abs(loo[pior]),
                          "winsorizado": rho_w, "delta_winsor": rho_w-base},
        "observacoes": obs,
    }, indent=2, default=str))
    print(f"\n[ok] {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

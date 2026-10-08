#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
component_ic.py — IC por componente, correcao de multiplicidade e
dimensionalidade efetiva do YAAF v5.0.

EXPLORATORIO E DIAGNOSTICO. Nao reponderar com base nesta saida: os pesos
atuais sao defensaveis porque foram fixados antes de ver estes dados. Reponderar
aqui converte a medicao out-of-sample de IC_PROTOCOL.md em ajuste in-sample e
destroi o unico argumento que o rho=0.6577 tem. Se os dados pedirem emenda, a
emenda e' de especificacao e valida-se em dados FUTUROS.

PRINCIPIO DE DESENHO, como em ic_test_gmx.py: nada de metricas reimplementadas.
Importa `compute_yaf_metrics` do coletor de producao e
`enrich_metrics_from_trades` do scorer. Alem disso, GUARDA DE REPRODUCAO: o
S_RAW recalculado e' comparado com o `sraw_t1` ja gravado em
ic_test_gmx_result.json, e o script ABORTA se divergir. Um caminho de codigo
diferente deixa de ser erro silencioso e passa a ser parada.

Regra de decisao assimetrica (n=31, 11 testes, poder baixo):
  - negativo e significativo apos BHY -> caso para emenda
  - nao significativo                  -> poder insuficiente, nada se mexe
  - positivo e significativo           -> o componente se sustenta
"NAO significativo" nao e' evidencia de inutilidade.

Rodar de /root/aiagentregistry-observatory.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OBS = Path("/root/aiagentregistry-observatory")
SCORER = Path("/root/yaaf/scorer")
EVID = Path("docs/evidence")
IC_RESULT = EVID / "ic_test_gmx_result.json"
OUT = EVID / "component_ic_result.json"

for p in (str(OBS), str(SCORER), str(EVID)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ic_test_gmx import spearman, INITIAL_BALANCE, MIN_TRADES_T1, MIN_TRADES_T2  # noqa: E402
from feed_yaaf_gmx import compute_yaf_metrics                                    # noqa: E402
from yaaf_score_v5_formal import yelden_score, enrich_metrics_from_trades        # noqa: E402

# Os 11 componentes, com o nome do contrato ao lado da chave real do scorer.
COMPONENTES = [
    ("s_sharpe",     "1  Sharpe/DSR"),
    ("s_sortino",    "2  Sortino"),
    ("s_winrate",    "3  Win rate"),
    ("s_pf",         "4  Profit factor"),
    ("s_avg_r",      "5  Avg R"),
    ("s_expectancy", "6  Expectancy"),
    ("s_vol",        "7  Inv. volatility"),
    ("s_stability",  "8  Stability2"),
    ("s_smoothness", "9  Smoothness2"),
    ("s_pf_pct",     "10 PF percentile"),
    ("s_mc",         "11 Market context"),
]
# Fora dos 11, mas entram no S_RAW e valem IC proprio.
EXTRAS = [("cvar_pen", "pen CVaR"), ("dd_penalty", "pen MaxDD"), ("dsr", "DSR")]


def bh_adjust(p, c=1.0):
    """Step-up de Benjamini-Hochberg; c=sum(1/i) da a versao Yekutieli."""
    m = len(p)
    idx = sorted(range(m), key=lambda i: p[i])
    adj, prev = [1.0] * m, 1.0
    for rank in range(m, 0, -1):
        i = idx[rank - 1]
        prev = min(prev, min(1.0, p[i] * m * c / rank))
        adj[i] = prev
    return adj


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


def score_full(trades):
    """Caminho de producao, devolvendo o dict inteiro do yelden_score."""
    m = compute_yaf_metrics(trades)
    if not m.get("trades"):
        return None
    m = enrich_metrics_from_trades(m, trades)
    try:
        return yelden_score(metrics=m,
                            state={"ema": 300.0, "round_history": [], "total_trades": 0},
                            trades=trades, initial_balance=INITIAL_BALANCE)
    except Exception as e:
        print(f"    [erro] yelden_score: {e}")
        return None


def main():
    ref = json.loads(IC_RESULT.read_text())
    corte = float(ref["corte_exit_time"])
    sraw_ref = {o["agent"]: o["sraw_t1"] for o in ref["observacoes"]}
    alvo_ref = {o["agent"]: o["sum_r_t2"] for o in ref["observacoes"]}
    print(f"referencia: {IC_RESULT}  n={len(sraw_ref)}  corte={ref['corte_data']}")

    pls = payloads()
    obs = []
    for a in sraw_ref:
        d = pls.get(a)
        if not d:
            print(f"    [aviso] payload ausente: {a}")
            continue
        tr = [t for t in d["trades"] if t.get("exit_time") is not None]
        t1 = [t for t in tr if float(t["exit_time"]) < corte]
        t2 = [t for t in tr if float(t["exit_time"]) >= corte]
        if len(t1) < MIN_TRADES_T1 or len(t2) < MIN_TRADES_T2:
            continue
        res = score_full(t1)
        if not res:
            continue
        meses = {(datetime.fromtimestamp(float(t["exit_time"]), tz=timezone.utc).year,
                  datetime.fromtimestamp(float(t["exit_time"]), tz=timezone.utc).month)
                 for t in t1}
        ts = [float(t["exit_time"]) for t in t1]
        row = {"agent": a, "s_raw": res.get("s_raw"),
               "sum_r_t2": alvo_ref[a],
               "n_t1": len(t1), "n_t2": len(t2),
               "n_meses_t1": len(meses),
               "span_dias_t1": (max(ts) - min(ts)) / 86400.0}
        for k, _ in COMPONENTES + EXTRAS:
            v = res.get(k)
            row[k] = float(v) if isinstance(v, (int, float)) else None
        obs.append(row)

    # ── GUARDA DE REPRODUCAO ────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("GUARDA DE REPRODUCAO")
    print("=" * 72)
    difs = [(abs(o["s_raw"] - sraw_ref[o["agent"]]), o["agent"]) for o in obs
            if o["s_raw"] is not None]
    if len(obs) != len(sraw_ref) or not difs:
        print(f"  ABORTADO: {len(obs)} agentes recalculados vs {len(sraw_ref)} na referencia.")
        return 1
    pior, qual = max(difs)
    print(f"  agentes: {len(obs)}   maior |S_RAW_recalc - S_RAW_ref| = {pior:.3e}  ({qual[:14]}…)")
    if pior > 1e-9:
        print("  ABORTADO: o caminho de codigo divergiu do que produziu o rho=0.6577.")
        print("  Nenhum IC por componente e' comparavel ate isso ser resolvido.")
        return 1
    print("  OK — mesmo caminho de codigo, bit a bit.")

    n = len(obs)
    alvo = [o["sum_r_t2"] for o in obs]

    # ── cobertura mensal ────────────────────────────────────────────────────
    meses = sorted(o["n_meses_t1"] for o in obs)
    spans = sorted(o["span_dias_t1"] for o in obs)
    med_meses = meses[n // 2]
    ge6 = sum(1 for m in meses if m >= 6)
    print("\n" + "=" * 72)
    print("COBERTURA TEMPORAL DE T1  (decide se a Spec Formal e' computavel)")
    print("=" * 72)
    print(f"  meses distintos  min/mediana/max : {meses[0]} / {med_meses} / {meses[-1]}")
    print(f"  span em dias     min/mediana/max : {spans[0]:.1f} / {spans[n//2]:.1f} / {spans[-1]:.1f}")
    print(f"  agentes com >= 6 meses           : {ge6}/{n}")
    print(f"  agentes com >= 2 meses           : {sum(1 for m in meses if m >= 2)}/{n}")
    if med_meses < 2:
        print("  VEREDITO: sigma do Sharpe mensal e' indefinido na mediana da populacao.")
        print("  A Spec Formal (1/(1+sigma_mSharpe))^2 NAO e' computavel aqui, e a")
        print("  emenda honesta e' 'remover ou redefinir o componente', nunca")
        print("  'implementar a formula com um fallback escolhido na hora'.")
    elif med_meses < 6:
        print("  VEREDITO: computavel na forma, fragil no conteudo — sigma sobre 2 a 5")
        print("  observacoes mensais tem erro padrao enorme. Aplicavel so com o")
        print("  numero de meses declarado junto do score.")

    # ── IC por componente ───────────────────────────────────────────────────
    res_comp, ps, nomes = {}, [], []
    for k, rotulo in COMPONENTES + EXTRAS:
        v = [o[k] for o in obs]
        ok = [i for i, x in enumerate(v) if x is not None and math.isfinite(x)]
        if len(ok) < 5:
            res_comp[k] = {"rotulo": rotulo, "status": "ausente", "n": len(ok)}
            continue
        vv = [v[i] for i in ok]
        if max(vv) - min(vv) < 1e-12:
            res_comp[k] = {"rotulo": rotulo, "status": "constante",
                           "valor": vv[0], "n": len(ok)}
            continue
        rho, p, lo, hi = spearman(vv, [alvo[i] for i in ok])
        res_comp[k] = {"rotulo": rotulo, "rho": rho, "p_raw": p,
                       "ic95_lo": lo, "ic95_hi": hi, "n": len(ok),
                       "distintos": len(set(vv))}
        if p is not None:
            ps.append(p); nomes.append(k)

    if ps:
        m = len(ps)
        cm = sum(1.0 / i for i in range(1, m + 1))
        bh, bhy = bh_adjust(ps, 1.0), bh_adjust(ps, cm)
        for i, k in enumerate(nomes):
            r = res_comp[k]
            r["p_bh"], r["p_bhy"] = bh[i], bhy[i]
            if bhy[i] < 0.05:
                r["status"] = "negativo_significativo" if r["rho"] < 0 else "positivo_significativo"
            else:
                r["status"] = "inconclusivo"
        print("\n" + "=" * 72)
        print(f"IC POR COMPONENTE   n={n}   {m} testes   c({m})={cm:.4f}")
        print("=" * 72)
        print(f"  {'componente':<20} {'rho':>8} {'p_raw':>8} {'p_BH':>8} {'p_BHY':>8}  status")
        for k, rotulo in COMPONENTES + EXTRAS:
            r = res_comp[k]
            if r["status"] in ("constante", "ausente"):
                extra = f"= {r.get('valor')}" if r["status"] == "constante" else ""
                print(f"  {rotulo:<20} {'—':>8} {'—':>8} {'—':>8} {'—':>8}  {r['status'].upper()} {extra}")
            else:
                print(f"  {rotulo:<20} {r['rho']:>+8.4f} {r['p_raw']:>8.4f} "
                      f"{r['p_bh']:>8.4f} {r['p_bhy']:>8.4f}  {r['status']}")

    # ── dimensionalidade efetiva ────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("DIMENSIONALIDADE EFETIVA  (11 componentes sao 11 dimensoes?)")
    print("=" * 72)
    uteis = [k for k, _ in COMPONENTES
             if res_comp[k]["status"] not in ("constante", "ausente")]
    dim = {"nota": "menos de 2 componentes com variancia"}
    if len(uteis) >= 2:
        M = [[o[k] for o in obs] for k in uteis]
        R = [[1.0] * len(uteis) for _ in uteis]
        for i in range(len(uteis)):
            for j in range(i + 1, len(uteis)):
                R[i][j] = R[j][i] = spearman(M[i], M[j])[0]
        ev = sorted(np.linalg.eigvalsh(np.array(R)).tolist(), reverse=True)
        tot = sum(ev)
        pct = [100.0 * e / tot for e in ev]
        cum, n90 = 0.0, len(ev)
        for i, x in enumerate(pct, 1):
            cum += x
            if cum >= 90.0:
                n90 = i; break
        print(f"  componentes com variancia : {len(uteis)} de 11")
        print(f"  variancia explicada (%)   : {[round(x,1) for x in pct]}")
        print(f"  fatores para 90%          : {n90}")
        print(f"  Leitura: {n90} de {len(uteis)} significa que reponderar componentes")
        print("  colineares nao faz o que parece fazer — mover um peso move os outros.")
        acima = [(abs(R[i][j]), uteis[i], uteis[j], R[i][j])
                 for i in range(len(uteis)) for j in range(i + 1, len(uteis))
                 if abs(R[i][j]) > 0.90]
        acima.sort(reverse=True)
        if acima:
            print(f"\n  pares com |rho| > 0.90 (praticamente a mesma variavel):")
            for _, a, b, r in acima:
                print(f"    {a:<14} x {b:<14} rho={r:+.4f}")
        dim = {"componentes": uteis, "matriz_rho": R, "autovalores": ev,
               "variancia_pct": pct, "fatores_90pct": n90,
               "pares_acima_090": [{"a": a, "b": b, "rho": r} for _, a, b, r in acima]}

    # ── sensibilidade ───────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SENSIBILIDADE")
    print("=" * 72)
    sr = [o["s_raw"] for o in obs]
    base = spearman(sr, alvo)[0]
    print(f"  primario reproduzido              rho={base:+.4f}   "
          f"(referencia {ref['resultados']['primario_soma_r']['rho']:+.4f})")
    loo = []
    for i in range(n):
        idx = [j for j in range(n) if j != i]
        loo.append(spearman([sr[j] for j in idx], [alvo[j] for j in idx])[0] - base)
    pior_i = max(range(n), key=lambda i: abs(loo[i]))
    print(f"  leave-one-out, maior |delta|      {abs(loo[pior_i]):.4f}  "
          f"ao remover {obs[pior_i]['agent'][:14]}…")
    sens_comp = {}
    for k, rotulo in COMPONENTES:
        r = res_comp[k]
        if r["status"] in ("constante", "ausente"):
            continue
        v = [o[k] for o in obs]
        b = r["rho"]
        d = max(abs(spearman([v[j] for j in range(n) if j != i],
                             [alvo[j] for j in range(n) if j != i])[0] - b)
                for i in range(n))
        sens_comp[k] = d
        if d > 0.15:
            print(f"  [FRAGIL] {rotulo}: um agente move o IC em {d:.4f}")

    OUT.write_text(json.dumps({
        "aviso": "EXPLORATORIO — nao reponderar pesos com esta saida",
        "protocolo_base": "IC_PROTOCOL.md v1",
        "rodado_em": datetime.now(timezone.utc).isoformat(),
        "n": n, "n_testes": len(ps),
        "guarda_reproducao_max_dif": pior,
        "primario_reproduzido": base,
        "cobertura": {"meses_mediana": med_meses, "meses_min": meses[0],
                      "meses_max": meses[-1], "agentes_ge_6_meses": ge6,
                      "span_dias_mediana": spans[n // 2]},
        "componentes": res_comp,
        "dimensionalidade": dim,
        "sensibilidade": {"leave_one_out_max": abs(loo[pior_i]),
                          "por_componente_loo_max": sens_comp},
        "observacoes": obs,
    }, indent=2, default=str))
    print(f"\n[ok] {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

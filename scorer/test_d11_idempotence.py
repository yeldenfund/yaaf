#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_d11_idempotence.py — teste de aceitacao de D11, escrito ANTES do patch.

D11: o scorer para de acumular total_trades. Ele recebe uma OBSERVACAO, nao um
delta, e somar por dentro assume silenciosamente que o chamador manda deltas.
Com payloads que sao snapshot do historico inteiro, a soma conta o mesmo
historico de novo a cada rodada: em producao a razao medida foi 83,5x
(3.671.818 em yaaf_state contra 43.984 declarados nos payloads), o que pregou
CF = min(sqrt(trades/250), 1) em 1,0 para toda a populacao.

O que este teste cobre e o que NAO cobre:

  COBRE   total_trades e cf idempotentes sob a mesma observacao; cf
          discriminando de novo abaixo de CF_N_STAR.
  NAO     a EMA e o round_history continuam avancando a cada chamada. Isso e
  COBRE   correto para D11: a EMA e o suavizador, e e o PIPELINE que nao deve
          re-pontuar observacao inalterada (P1, com sha do payload). Um teste
          que exigisse EMA idempotente aqui estaria cobrando de D11 uma coisa
          que D11 nao entrega.

Uso:
    python3 test_d11_idempotence.py [caminho/do/scorer.py]
    YAAF_SCORER_PY=... python3 test_d11_idempotence.py
"""
import importlib.util
import os
import sys

PADRAO = "/root/yaaf/scorer/yaaf_score_v5_formal.py"
TOL = 1e-9


def carrega(caminho):
    spec = importlib.util.spec_from_file_location("sc", caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def trade(r, i):
    """Um trade minimo e plausivel: r e o R-multiple."""
    return {"market": "X", "entry_time": 1780000000 + i * 3600,
            "exit_time": 1780000000 + i * 3600 + 60,
            "pnl": 100.0 * r, "collateral": 100.0, "fees": 1.0,
            "volume": 2000.0, "r_multiple": float(r), "n_fills": 1,
            "is_liquidation": False}


def observacao(n):
    """Uma observacao com n trades, alternando ganho e perda."""
    rs = [0.9 if i % 3 else -0.5 for i in range(n)]
    trades = [trade(r, i) for i, r in enumerate(rs)]
    wins = [r for r in rs if r > 0]
    losses = [-r for r in rs if r < 0]
    metrics = {
        "trades": n,
        "sharpe_r": 1.1, "sortino_r": 2.0,
        "win_rate": len(wins) / n,
        "profit_factor": (sum(wins) / sum(losses)) if losses else 5.0,
        "avg_r": sum(rs) / n, "expectancy_r": sum(rs) / n,
        "vol_r": 0.7, "max_dd_pct": 8.0,
        "stability": 0.9, "smoothness": 0.5, "skew": 0.2, "kurt": 3.0,
        "total_pnl": 100.0 * sum(rs), "n_liquidations": 0,
    }
    return metrics, trades


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("YAAF_SCORER_PY", PADRAO)
    if not os.path.isfile(caminho):
        print("ABORTADO: nao achei o scorer em %s" % caminho)
        return 2
    sc = carrega(caminho)
    print("scorer : %s" % caminho)
    print("versao : %s" % sc.VERSION_SCORE)
    print("CF_N_STAR = %s" % sc.CF_N_STAR)
    print()

    falhas = []

    def checa(nome, ok, detalhe=""):
        print("  %-62s %s" % (nome, "ok" if ok else "FALHOU"))
        if detalhe:
            print("      %s" % detalhe)
        if not ok:
            falhas.append(nome)

    # ---- A: idempotencia de total_trades e cf -------------------------
    print("A) a mesma observacao, duas vezes")
    n = 65
    metrics, trades = observacao(n)
    metrics = sc.enrich_metrics_from_trades(metrics, trades)

    st0 = {"ema": 300.0, "round_history": [], "total_trades": 0}
    r1 = sc.yelden_score(metrics=metrics, state=st0, trades=trades, initial_balance=11000.0)
    st1 = r1["new_state"]
    r2 = sc.yelden_score(metrics=metrics, state=st1, trades=trades, initial_balance=11000.0)

    checa("total_trades da 1a chamada == n trades observados",
          r1["new_state"]["total_trades"] == n,
          "obtido %s, esperado %s" % (r1["new_state"]["total_trades"], n))
    checa("total_trades nao cresce na 2a chamada",
          r2["new_state"]["total_trades"] == r1["new_state"]["total_trades"],
          "1a %s, 2a %s" % (r1["new_state"]["total_trades"], r2["new_state"]["total_trades"]))
    checa("cf identico nas duas chamadas",
          abs(r2["cf"] - r1["cf"]) < TOL,
          "1a %.6f, 2a %.6f" % (r1["cf"], r2["cf"]))

    # ---- B: cf volta a discriminar ------------------------------------
    print()
    print("B) cf discrimina abaixo de CF_N_STAR")
    import math
    for n_t in (50, 100, 249, 250, 1000):
        m, t = observacao(n_t)
        m = sc.enrich_metrics_from_trades(m, t)
        r = sc.yelden_score(metrics=m, state={"ema": 300.0, "round_history": [], "total_trades": 0},
                            trades=t, initial_balance=11000.0)
        esperado = min(math.sqrt(n_t / sc.CF_N_STAR), 1.0)
        checa("n=%-5d cf == min(sqrt(n/%s),1)" % (n_t, sc.CF_N_STAR),
              abs(r["cf"] - esperado) < 1e-6,
              "obtido %.6f, esperado %.6f" % (r["cf"], esperado))

    # ---- C: o que D11 NAO muda ---------------------------------------
    print()
    print("C) o que D11 deliberadamente nao muda")
    checa("s_raw identico nas duas chamadas (nao depende do estado)",
          abs(r2["s_raw"] - r1["s_raw"]) < TOL,
          "1a %.6f, 2a %.6f" % (r1["s_raw"], r2["s_raw"]))
    checa("a EMA continua avancando (e o suavizador; P1 trata a repeticao)",
          abs(r2["ema_new"] - r1["ema_new"]) > TOL,
          "1a %.4f, 2a %.4f" % (r1["ema_new"], r2["ema_new"]))
    checa("round_history continua acumulando (territorio de P1, nao de D11)",
          len(r2["new_state"]["round_history"]) == len(r1["new_state"]["round_history"]) + 1,
          "1a %d entradas, 2a %d" % (len(r1["new_state"]["round_history"]),
                                     len(r2["new_state"]["round_history"])))

    print()
    if falhas:
        print("=== %d FALHA(S) ===" % len(falhas))
        for f in falhas:
            print("  - %s" % f)
        print()
        print("Se as falhas sao as de (A) e (B), e o codigo ANTES de D11 e o")
        print("teste esta fazendo o seu trabalho. Aplique o patch e rode de novo.")
        return 1
    print("=== tudo passou: D11 esta no lugar ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_v560_weights_eligible.py — teste de aceitacao de v5.6.0, escrito ANTES
do patch.

v5.6.0 faz duas coisas:

  1. W = 1/N sobre os componentes vivos, W_SUM = 1,0. Declarado em
     SPEC_CHANGE_v5.4.0.md -- o numero no nome daquele arquivo e a ordem de
     declaracao, nao a de codigo, porque v5.5.0 entrou primeiro. Custo medido:
     rho 0,9944 contra os pesos calibrados, 18 dos 20 primeiros preservados.

  2. Sai `is_eligible` do scorer. O limiar de elegibilidade e do contrato
     (SCORE_THRESHOLD_ACTIVE = 500); o campo do scorer usava 400 e foi o que
     fez a pagina publica anunciar 9 elegiveis onde o contrato aceita 4. Um
     campo que nao governa nada e pode contradizer quem governa nao deve
     existir.

O teto algebrico tem que continuar exatamente 100: `core = sum(s_i*w_i)/W_SUM`
e a divisao preserva a escala, entao peso igual nao mexe no teto. Se mexer, o
patch errou.

Uso:  python3 test_v560_weights_eligible.py [caminho/do/scorer.py]
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
    return {"market": "X", "entry_time": 1780000000 + i * 3600,
            "exit_time": 1780000000 + i * 3600 + 60,
            "pnl": 100.0 * r, "collateral": 100.0, "fees": 1.0,
            "volume": 2000.0, "r_multiple": float(r), "n_fills": 1,
            "is_liquidation": False}


def observacao(n=90):
    rs = [0.9 if i % 3 else -0.5 for i in range(n)]
    wins = [r for r in rs if r > 0]
    losses = [-r for r in rs if r < 0]
    m = {"trades": n, "sharpe_r": 0.30, "sortino_r": 1.2,
         "win_rate": len(wins) / n,
         "profit_factor": (sum(wins) / sum(losses)) if losses else 5.0,
         "avg_r": sum(rs) / n, "expectancy_r": sum(rs) / n, "vol_r": 0.8,
         "max_dd_r": 6.0, "stability": 0.9, "smoothness": 0.5,
         "skew": 0.0, "kurt": 3.0, "total_pnl": 100.0 * sum(rs),
         "n_liquidations": 0}
    return m, [trade(r, i) for i, r in enumerate(rs)]


ESTADO = {"ema": 300.0, "round_history": [], "total_trades": 0}


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("YAAF_SCORER_PY", PADRAO)
    if not os.path.isfile(caminho):
        print("ABORTADO: nao achei o scorer em %s" % caminho)
        return 2
    sc = carrega(caminho)
    print("scorer : %s" % caminho)
    print("versao : %s" % sc.VERSION_SCORE)
    print("W      : %s" % "  ".join("%s %.4f" % (k, v) for k, v in sorted(sc.W.items())))
    print("W_SUM  : %.4f" % sc.W_SUM)
    print()

    falhas = []

    def checa(nome, ok, det=""):
        print("  %-62s %s" % (nome, "ok" if ok else "FALHOU"))
        if det:
            print("      %s" % det)
        if not ok:
            falhas.append(nome)

    n = len(sc.W)

    # ---- 1. os pesos --------------------------------------------------
    print("1) W = 1/N sobre os componentes vivos")
    checa("todos os pesos iguais a 1/%d" % n,
          all(abs(v - 1.0 / n) < TOL for v in sc.W.values()),
          "distintos: %s" % sorted({round(v, 6) for v in sc.W.values()}))
    checa("W_SUM == 1.0", abs(sc.W_SUM - 1.0) < TOL, "obtido %.10f" % sc.W_SUM)
    checa("W_SUM == soma de W", abs(sc.W_SUM - sum(sc.W.values())) < TOL,
          "W_SUM %.10f, soma %.10f" % (sc.W_SUM, sum(sc.W.values())))
    checa("nenhum componente removido voltou",
          "smoothness" not in sc.W and "mc" not in sc.W,
          "chaves: %s" % " ".join(sorted(sc.W)))

    # ---- 2. o teto algebrico nao se move ------------------------------
    print()
    print("2) o teto algebrico continua exatamente 100")
    teto = sum(100.0 * w for w in sc.W.values()) / sc.W_SUM
    checa("sum(100*w)/W_SUM == 100.0000", abs(teto - 100.0) < 1e-9,
          "obtido %.10f" % teto)

    # ---- 3. is_eligible saiu ------------------------------------------
    print()
    print("3) is_eligible nao e mais emitido pelo scorer")
    m, t = observacao()
    m = sc.enrich_metrics_from_trades(m, t)
    r = sc.yelden_score(metrics=m, state=dict(ESTADO), trades=t,
                        initial_balance=11000.0)
    checa("'is_eligible' ausente do resultado", "is_eligible" not in r,
          "ainda presente: %r" % r.get("is_eligible"))
    import io
    src = io.open(caminho, encoding="utf-8").read()
    checa("nenhum literal 'sistema >= 400' no fonte",
          "sistema >= 400" not in src)
    checa("a palavra is_eligible sobra apenas em comentario, se sobrar",
          all(l.strip().startswith("#") for l in src.splitlines()
              if "is_eligible" in l),
          "linhas de codigo com is_eligible: %s"
          % [l.strip()[:60] for l in src.splitlines()
             if "is_eligible" in l and not l.strip().startswith("#")])

    # ---- 4. o que nao deve ter mudado ---------------------------------
    print()
    print("4) o que v5.6.0 nao toca")
    for nome, attr in (("CAP_DD", "CAP_DD"), ("DD_PEN_WEIGHT", "DD_PEN_WEIGHT"),
                       ("EMA_INITIAL", "EMA_INITIAL"), ("CF_N_STAR", "CF_N_STAR"),
                       ("MIN_TRADES_SRAW", "MIN_TRADES_SRAW")):
        checa("%s continua presente" % nome, hasattr(sc, attr),
              "ausente" if not hasattr(sc, attr) else str(getattr(sc, attr)))
    checa("psr continua no resultado (v5.3.0)", "psr" in r)
    checa("max_dd_source continua no resultado (v5.5.0)", "max_dd_source" in r)

    print()
    if falhas:
        print("=== %d FALHA(S) ===" % len(falhas))
        for f in falhas:
            print("  - %s" % f)
        print()
        print("Antes do patch espero falhar nos pesos, no W_SUM e nos tres de")
        print("is_eligible. O teto e o bloco 4 tem que passar ANTES tambem --")
        print("se falharem antes, o scorer nao esta no estado que eu suponho.")
        return 1
    print("=== tudo passou: v5.6.0 esta no lugar ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_v550_dd_cap.py — teste de aceitacao de v5.5.0, escrito ANTES do patch.

v5.5.0 faz tres coisas:

  1. dd_pen = min(max_dd_r, CAP_DD) * DD_PEN_WEIGHT, com CAP_DD = 20 R.
     Medido: a forma sem teto pisa 11 de 302 agentes e e dominada pela cauda
     (p99 = 136 R -> 27 pontos; max = 281 R -> 56 pontos, contra S_RAW medio
     de 26). Com teto em 20 R a penalidade maxima e 4 pontos, o piso cai para
     6 de 302, e rho contra a base e 0,9927 com os mesmos 18 do top-20.

  2. A chave passa a ser max_dd_r, porque o valor e o drawdown da curva de R
     acumulado -- verificado por aritmetica contra um payload real, diferenca
     0,000e+00. max_dd_pct continua sendo LIDA, como legado em R, porque os
     500 payloads selados a carregam e reescreve-los quebraria o manifesto.
     O scorer registra qual chave leu.

  3. Some a substituicao em score_yaaf que injetava uma porcentagem genuina
     sob a chave de R. Era o unico caminho pelo qual a chave legada carregava
     porcentagem; sem ela, legado deixa de ser ambiguo.

O teste nao cobre o item 3, que esta em emit_yaaf_final.py e nao no scorer --
ele e verificado por grep no patch.

Uso:  python3 test_v550_dd_cap.py [caminho/do/scorer.py]
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


def observacao(n=90, dd=None, chave="max_dd_r"):
    rs = [0.9 if i % 3 else -0.5 for i in range(n)]
    wins = [r for r in rs if r > 0]
    losses = [-r for r in rs if r < 0]
    m = {"trades": n, "sharpe_r": 0.30, "sortino_r": 1.2,
         "win_rate": len(wins) / n,
         "profit_factor": (sum(wins) / sum(losses)) if losses else 5.0,
         "avg_r": sum(rs) / n, "expectancy_r": sum(rs) / n, "vol_r": 0.8,
         "stability": 0.9, "smoothness": 0.5, "skew": 0.0, "kurt": 3.0,
         "total_pnl": 100.0 * sum(rs), "n_liquidations": 0}
    if dd is not None:
        m[chave] = float(dd)
    return m, [trade(r, i) for i, r in enumerate(rs)]


ESTADO = {"ema": 300.0, "round_history": [], "total_trades": 0}


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("YAAF_SCORER_PY", PADRAO)
    if not os.path.isfile(caminho):
        print("ABORTADO: nao achei o scorer em %s" % caminho)
        return 2
    sc = carrega(caminho)
    cap = getattr(sc, "CAP_DD", None)
    print("scorer   : %s" % caminho)
    print("versao   : %s" % sc.VERSION_SCORE)
    print("CAP_DD   : %s" % (cap if cap is not None else "(ausente)"))
    print("DD_PEN_W : %.4f" % sc.DD_PEN_WEIGHT)
    print()

    falhas = []

    def checa(nome, ok, det=""):
        print("  %-62s %s" % (nome, "ok" if ok else "FALHOU"))
        if det:
            print("      %s" % det)
        if not ok:
            falhas.append(nome)

    def pontua(dd, chave="max_dd_r", **extra):
        m, t = observacao(dd=dd, chave=chave)
        m.update(extra)
        m = sc.enrich_metrics_from_trades(m, t)
        if dd is not None:
            m[chave] = float(dd)        # o enrich nao deve sobrescrever isto
        return sc.yelden_score(metrics=m, state=dict(ESTADO), trades=t,
                               initial_balance=11000.0)

    # ---- 1. o teto ----------------------------------------------------
    print("1) dd_pen = min(max_dd_r, CAP_DD) * DD_PEN_WEIGHT")
    checa("CAP_DD existe e vale 20", cap == 20.0, "obtido %r" % (cap,))
    if cap == 20.0:
        w = sc.DD_PEN_WEIGHT
        # chave legada de proposito: e a que existe antes e depois do patch,
        # entao uma falha aqui no pre-patch e genuina
        for dd, esp in ((0.0, 0.0), (5.0, 5.0 * w), (19.999, 19.999 * w),
                        (20.0, 20.0 * w), (50.0, 20.0 * w), (281.24, 20.0 * w)):
            r = pontua(dd, chave="max_dd_pct")
            got = float(r["dd_penalty"])
            checa("max_dd_r=%-8.3f -> dd_penalty %.4f" % (dd, esp),
                  abs(got - esp) < 1e-6, "obtido %.6f" % got)

    # ---- 2. abaixo do teto nada muda ----------------------------------
    print()
    print("2) abaixo do teto o patch e inocuo")
    a, b = pontua(5.0, chave="max_dd_pct"), pontua(10.0, chave="max_dd_pct")
    checa("dd_penalty cresce abaixo do teto",
          float(b["dd_penalty"]) > float(a["dd_penalty"]) + TOL,
          "5R -> %.4f ; 10R -> %.4f" % (a["dd_penalty"], b["dd_penalty"]))
    c, d = pontua(50.0, chave="max_dd_pct"), pontua(200.0, chave="max_dd_pct")
    checa("dd_penalty constante acima do teto",
          abs(float(c["dd_penalty"]) - float(d["dd_penalty"])) < TOL,
          "50R -> %.4f ; 200R -> %.4f" % (c["dd_penalty"], d["dd_penalty"]))
    checa("S_RAW igual para 50R e 200R (o teto absorveu a cauda)",
          abs(float(c["s_raw"]) - float(d["s_raw"])) < TOL,
          "50R -> %.4f ; 200R -> %.4f" % (c["s_raw"], d["s_raw"]))

    # ---- 3. as duas chaves --------------------------------------------
    print()
    print("3) max_dd_r manda; max_dd_pct e lida como legado em R")
    novo = pontua(12.0, chave="max_dd_r")
    legado = pontua(12.0, chave="max_dd_pct")
    checa("a chave legada da o mesmo dd_penalty que a nova",
          abs(float(novo["dd_penalty"]) - float(legado["dd_penalty"])) < TOL,
          "nova %.4f ; legada %.4f" % (novo["dd_penalty"], legado["dd_penalty"]))
    checa("o scorer registra max_dd_source", "max_dd_source" in novo,
          "ausente" if "max_dd_source" not in novo else str(novo["max_dd_source"]))
    if "max_dd_source" in novo:
        checa("source diz max_dd_r quando a nova chave existe",
              novo["max_dd_source"] == "max_dd_r", str(novo["max_dd_source"]))
        checa("source nomeia o legado quando so a antiga existe",
              "max_dd_pct" in str(legado.get("max_dd_source", "")),
              str(legado.get("max_dd_source")))
    ambas = pontua(12.0, chave="max_dd_r", max_dd_pct=999.0)
    checa("com as duas presentes, max_dd_r vence",
          abs(float(ambas["dd_penalty"]) - float(novo["dd_penalty"])) < TOL,
          "ambas %.4f ; so a nova %.4f" % (ambas["dd_penalty"], novo["dd_penalty"]))
    checa("max_dd_r aparece no resultado", "max_dd_r" in novo,
          "ausente" if "max_dd_r" not in novo else "%.4f" % novo["max_dd_r"])

    # ---- 4. o piso ----------------------------------------------------
    print()
    print("4) o teto deixa de pisar por cauda de drawdown")
    sem_dd = pontua(0.0, chave="max_dd_pct")
    cauda = pontua(281.24, chave="max_dd_pct")
    checa("S_RAW com 281R nao e zero (nao foi pisado pela cauda)",
          float(cauda["s_raw"]) > 0.0,
          "S_RAW %.4f (sem dd: %.4f)" % (cauda["s_raw"], sem_dd["s_raw"]))

    print()
    if falhas:
        print("=== %d FALHA(S) ===" % len(falhas))
        for f in falhas:
            print("  - %s" % f)
        print()
        print("Antes do patch espero falhar em tudo que depende de CAP_DD,")
        print("de max_dd_source e de max_dd_r. Se falhar algo mais, me mande")
        print("a saida inteira antes de aplicar nada.")
        return 1
    print("=== tudo passou: v5.5.0 esta no lugar ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

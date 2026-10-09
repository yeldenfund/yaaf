#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_d5_d6_psr.py — teste de aceitacao de D5 e D6, escrito ANTES do patch.

D6: o T do PSR tem que ser o numero de TRADES, nao de dias. O `sharpe` que
entra na formula e o `sharpe_r`, calculado sobre R-multiplos por trade; usar a
contagem de dias no denominador mede a incerteza de uma serie que nao e a que
gerou aquele Sharpe. A razao media entre as duas e o 5,83x que a Emenda v5.0.2
registra.

D5: o campo chamado `dsr` contem um PSR. O desconto de multiplos testes so e
aplicado quando n_trials > 1, e nada no pipeline passa n_trials. O nome afirma
uma correcao que nao foi feita.

Dois jeitos de testar o D6, de proposito:

  INVARIANCIA   o psr nao muda quando metrics["n_daily"] muda. Robusto: nao
                depende de eu ter lido a formula certo.
  RECALCULO     o psr devolvido bate com a formula publicada, recalculada aqui
                com T = n_trades. Forte, mas vale o que valer a minha leitura
                da formula — por isso vem acompanhado do primeiro.

Uso:  python3 test_d5_d6_psr.py [caminho/do/scorer.py]
"""
import importlib.util
import math
import os
import sys

PADRAO = "/root/yaaf/scorer/yaaf_score_v5_formal.py"
TOL = 1e-9


def carrega(caminho):
    spec = importlib.util.spec_from_file_location("sc", caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def psr_esperado(sr, T, skew=0.0, kurt=3.0, n_trials=1):
    """A formula publicada, recalculada aqui. Bailey & Lopez de Prado (2014)."""
    T = max(int(T), 2)
    kurt = max(kurt, 1.0)
    inner = max(1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr, 1e-12)
    sigma = math.sqrt(inner / (T - 1))
    if sigma < 1e-12:
        return 1.0 if sr > 0 else 0.0
    z = sr / sigma
    if n_trials > 1:
        z -= math.sqrt(2.0 * math.log(max(n_trials, 1)))
    return min(max(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))), 0.0), 1.0)


def trade(r, i):
    return {"market": "X", "entry_time": 1780000000 + i * 3600,
            "exit_time": 1780000000 + i * 3600 + 60,
            "pnl": 100.0 * r, "collateral": 100.0, "fees": 1.0,
            "volume": 2000.0, "r_multiple": float(r), "n_fills": 1,
            "is_liquidation": False}


def observacao(n, sharpe=0.08, skew=0.20, kurt=3.0):
    """sharpe deliberadamente baixo: com Sharpe alto o PSR satura em 1,0 e o
    recalculo passaria trivialmente, sem distinguir T nenhum. A guarda logo
    abaixo exige que os tres casos de T de fato discriminem."""
    rs = [0.9 if i % 3 else -0.5 for i in range(n)]
    wins = [r for r in rs if r > 0]
    losses = [-r for r in rs if r < 0]
    metrics = {
        "trades": n, "sharpe_r": sharpe, "sortino_r": 2.0,
        "win_rate": len(wins) / n,
        "profit_factor": (sum(wins) / sum(losses)) if losses else 5.0,
        "avg_r": sum(rs) / n, "expectancy_r": sum(rs) / n,
        "vol_r": 0.7, "max_dd_pct": 8.0, "stability": 0.9, "smoothness": 0.5,
        "skew": skew, "kurt": kurt, "total_pnl": 100.0 * sum(rs),
        "n_liquidations": 0,
    }
    return metrics, [trade(r, i) for i, r in enumerate(rs)]


ESTADO = {"ema": 300.0, "round_history": [], "total_trades": 0}


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("YAAF_SCORER_PY", PADRAO)
    if not os.path.isfile(caminho):
        print("ABORTADO: nao achei o scorer em %s" % caminho)
        return 2
    sc = carrega(caminho)
    print("scorer : %s" % caminho)
    print("versao : %s" % sc.VERSION_SCORE)
    print()

    falhas = []

    def checa(nome, ok, detalhe=""):
        print("  %-62s %s" % (nome, "ok" if ok else "FALHOU"))
        if detalhe:
            print("      %s" % detalhe)
        if not ok:
            falhas.append(nome)

    def pontua(metrics, trades, n_trials=1, **extra):
        """Devolve (resultado, metricas_usadas).

        As metricas usadas importam: o enrich recalcula skew e kurt a partir
        dos trades, sobrescrevendo o que foi declarado. Calcular a expectativa
        com os valores declarados, e nao com os usados, produziria uma falha
        falsa no recalculo depois do patch.
        """
        m = sc.enrich_metrics_from_trades(dict(metrics), trades)
        m.update(extra)
        r = sc.yelden_score(metrics=m, state=dict(ESTADO), trades=trades,
                            initial_balance=11000.0, n_trials=n_trials)
        return r, m

    def valor(r):
        """O PSR, sob qualquer um dos dois nomes, para o teste rodar antes e depois."""
        return r.get("psr", r.get("dsr"))

    n = 90
    metrics, trades = observacao(n)

    # ---- D6 por invariancia ------------------------------------------
    print("D6) o T do PSR nao vem de n_daily")
    a, _ = pontua(metrics, trades, n_daily=3)
    b, _ = pontua(metrics, trades, n_daily=300)
    checa("psr identico com n_daily=3 e n_daily=300",
          abs(valor(a) - valor(b)) < TOL,
          "n_daily=3 -> %.10f ; n_daily=300 -> %.10f" % (valor(a), valor(b)))

    # ---- D6 por recalculo --------------------------------------------
    print()
    print("D6) o psr devolvido bate com a formula, com T = n_trades")
    esperados = []
    for n_t in (30, 90, 400):
        m0, t = observacao(n_t)
        r, usadas = pontua(m0, t, n_daily=7)
        esp = psr_esperado(usadas["sharpe_r"], n_t,
                           usadas.get("skew", 0.0), usadas.get("kurt", 3.0))
        esperados.append(esp)
        checa("n_trades=%-4d psr == formula com T=n_trades" % n_t,
              abs(valor(r) - esp) < 1e-6,
              "obtido %.10f, esperado %.10f (sharpe %.4f skew %.4f kurt %.4f)"
              % (valor(r), esp, usadas["sharpe_r"],
                 usadas.get("skew", 0.0), usadas.get("kurt", 3.0)))
    checa("os tres casos discriminam entre si (nao saturaram)",
          max(esperados) - min(esperados) > 0.05,
          "esperados: " + ", ".join("%.4f" % e for e in esperados))

    # ---- D5 nomes e auditabilidade -----------------------------------
    print()
    print("D5) o campo diz o que e, e o denominador fica auditavel")
    r, _ = pontua(metrics, trades)
    checa("'psr' presente no resultado", "psr" in r)
    checa("'dsr' ausente do resultado", "dsr" not in r,
          "ainda presente" if "dsr" in r else "")
    checa("psr_n_obs == n_trades", r.get("psr_n_obs") == n,
          "psr_n_obs=%r, n_trades=%d" % (r.get("psr_n_obs"), n))
    checa("psr_n_trials == 1", r.get("psr_n_trials") == 1,
          "psr_n_trials=%r" % (r.get("psr_n_trials"),))

    # ---- o desconto de multiplos testes continua funcionando ---------
    print()
    print("guarda) o caminho DSR (n_trials > 1) nao foi quebrado")
    um, _ = pontua(metrics, trades, n_trials=1)
    dez, _ = pontua(metrics, trades, n_trials=10)
    checa("n_trials=10 devolve valor menor que n_trials=1",
          valor(dez) < valor(um),
          "1 -> %.10f ; 10 -> %.10f" % (valor(um), valor(dez)))

    print()
    if falhas:
        print("=== %d FALHA(S) ===" % len(falhas))
        for f in falhas:
            print("  - %s" % f)
        print()
        print("Antes do patch espero falhar em: a invariancia de n_daily, os tres")
        print("recalculos, e os quatro de nome e auditabilidade. Se falhar algo")
        print("mais, me mande a saida inteira antes de aplicar nada.")
        return 1
    print("=== tudo passou: D5 e D6 estao no lugar ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

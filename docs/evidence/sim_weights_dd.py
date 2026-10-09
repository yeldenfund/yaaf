#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sim_weights_dd.py — a ordenação do composto é sensível aos pesos e à unidade
do drawdown?

Somente leitura. Lê os payloads selados, calcula S_RAW sob variantes da regra,
e compara. Não toca no banco, não escreve score, não imprime endereço.

AS VARIANTES

  base          os pesos atuais, DD_PEN_WEIGHT como está
  dd_x0         o mesmo, com dd_pen removido (peso 0)
  dd_x0.1       o mesmo, dd_pen a um décimo  -- equivale a ler max_dd em R
                onde hoje se lê por cento, ou a recalibrar o peso para 0,02
  dd_x10        o mesmo, dd_pen dez vezes    -- o inverso
  1/N           peso igual para os 8 componentes vivos, DD como está
  1/N + dd_x0   peso igual e sem penalidade de drawdown

Multiplicar max_dd por k é idêntico a trocar DD_PEN_WEIGHT por 0,20k, então
estas seis variantes cobrem a unidade e a calibração de uma vez.

O QUE A SAÍDA RESPONDE

  piso          quantos agentes saem com S_RAW = 0. No piso eles empatam, e
                empate é perda de ordenação, não informação.
  rho           Spearman contra a base, calculado SÓ entre os agentes que
                nenhuma das duas variantes jogou no piso -- comparar incluindo
                empates mede a quantidade de empates, não a concordância.
  rho_todos     o mesmo incluindo os pisados, para a diferença entre os dois
                números ficar visível em vez de escondida na escolha.
  bandas        distribuição por faixa, porque a banda é o que o contrato lê
  topo          sobreposição do top-20, porque é dele que sai alocação

O QUE A SAÍDA NÃO RESPONDE

Qual regra PREVÊ melhor. Isto mede concordância de ordenação numa população
só, e numa que foi selecionada pelo desfecho -- os 500 endereços são os
maiores ganhadores e perdedores em dólar de uma janela. Se duas regras
ordenam igual aqui, a escolha entre elas é de simplicidade e honestidade, não
de desempenho. Se ordenam diferente, isto diz onde, não qual acerta. Comparar
poder preditivo é a Fase 2 e precisa da janela adiante.

Uso:
    python3 sim_weights_dd.py [dir_de_payloads] [--scorer CAMINHO] [--json saida.json]
"""
import argparse
import json
import math
import os
import sys
import importlib.util
from collections import Counter

PAYLOADS_PADRAO = "/root/aiagentregistry-observatory/yaaf_payloads_gmx"
SCORER_PADRAO = "/root/yaaf/scorer/yaaf_score_v5_formal.py"
MIN_TRADES = 30          # o mesmo piso que emit_yaaf_gmx.py aplica
TOP_K = 20


def carrega_scorer(caminho):
    spec = importlib.util.spec_from_file_location("sc", caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def postos(xs):
    """Postos com média nos empates."""
    pares = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(pares):
        j = i
        while j + 1 < len(pares) and xs[pares[j + 1]] == xs[pares[i]]:
            j += 1
        media = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[pares[k]] = media
        i = j + 1
    return r


def spearman(a, b):
    """Spearman por Pearson sobre os postos. None se não houver variância."""
    if len(a) < 3:
        return None
    ra, rb = postos(a), postos(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    dbb = math.sqrt(sum((x - mb) ** 2 for x in rb))
    if da < 1e-12 or dbb < 1e-12:
        return None
    return num / (da * dbb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payloads", nargs="?", default=PAYLOADS_PADRAO)
    ap.add_argument("--scorer", default=SCORER_PADRAO)
    ap.add_argument("--json", default=None)
    ap.add_argument("--top", type=int, default=TOP_K)
    args = ap.parse_args()

    if not os.path.isdir(args.payloads):
        print("ABORTADO: nao achei o diretorio %s" % args.payloads)
        return 2
    if not os.path.isfile(args.scorer):
        print("ABORTADO: nao achei o scorer %s" % args.scorer)
        return 2

    sc = carrega_scorer(args.scorer)
    W_BASE = dict(sc.W)
    DD_BASE = sc.DD_PEN_WEIGHT
    n_comp = len(W_BASE)

    print("scorer        : %s" % sc.VERSION_SCORE)
    print("componentes   : %d   W_SUM %.4f   DD_PEN_WEIGHT %.4f"
          % (n_comp, sc.W_SUM, DD_BASE))
    print("payloads      : %s" % args.payloads)
    print("piso de trades: %d" % MIN_TRADES)
    print()

    # --- carrega as observacoes uma vez ------------------------------------
    obs = []
    arquivos = sorted(f for f in os.listdir(args.payloads)
                      if f.endswith(".json") and not f.startswith("_"))
    lidos = pulados = erros = 0
    for nome in arquivos:
        try:
            with open(os.path.join(args.payloads, nome), encoding="utf-8") as fh:
                p = json.load(fh)
        except Exception:
            erros += 1
            continue
        lidos += 1
        metrics = p.get("metrics") or {}
        trades = p.get("trades") or []
        if int(metrics.get("trades") or 0) < MIN_TRADES:
            pulados += 1
            continue
        obs.append((sc.enrich_metrics_from_trades(dict(metrics), trades), trades))
    print("lidos %d   abaixo do piso de trades %d   ilegiveis %d   avaliados %d"
          % (lidos, pulados, erros, len(obs)))
    if len(obs) < 10:
        print("ABORTADO: poucas observacoes para comparar ordenacao.")
        return 1
    print()

    # --- as variantes -------------------------------------------------------
    peso_igual = {k: 1.0 / n_comp for k in W_BASE}
    # Impresso de proposito: 1/N sobre as chaves de W nao pode ressuscitar um
    # componente que a emenda removeu -- se a chave nao esta em W, ela nao
    # recebe peso. Quem conferir isto esta conferindo que o 1/N e sobre os
    # componentes VIVOS, nao sobre a lista historica.
    print("pesos atuais  : " + "  ".join("%s %.2f" % (k, v)
                                         for k, v in sorted(W_BASE.items())))
    print("1/N           : %.4f em cada um dos %d acima" % (1.0 / n_comp, n_comp))
    print()
    variantes = [
        ("base",         W_BASE,     1.0),
        ("dd_x0",        W_BASE,     0.0),
        ("dd_x0.1",      W_BASE,     0.1),
        ("dd_x10",       W_BASE,    10.0),
        ("1/N",          peso_igual, 1.0),
        ("1/N + dd_x0",  peso_igual, 0.0),
    ]

    estado = {"ema": 300.0, "round_history": [], "total_trades": 0}
    resultados = {}
    for nome, W, k in variantes:
        sc.W = dict(W)
        sc.W_SUM = sum(W.values())
        sc.DD_PEN_WEIGHT = DD_BASE * k
        s_raws, stages = [], []
        for metrics, trades in obs:
            r = sc.yelden_score(metrics=dict(metrics), state=dict(estado),
                                trades=trades, initial_balance=11000.0)
            s_raws.append(float(r["s_raw"]))
            stages.append(r["stage"])
        resultados[nome] = {"s_raw": s_raws, "stage": stages,
                            "w_sum": sc.W_SUM, "dd_peso": sc.DD_PEN_WEIGHT}
    # devolve o scorer ao estado em que estava
    sc.W, sc.W_SUM, sc.DD_PEN_WEIGHT = W_BASE, sum(W_BASE.values()), DD_BASE

    base = resultados["base"]["s_raw"]
    piso_base = [i for i, v in enumerate(base) if v <= 0.0]

    print("%-13s %7s %7s %7s %7s %8s %8s %6s" %
          ("variante", "W_SUM", "dd_pes", "medio", "max", "piso", "rho", "top%d" % args.top))
    print("-" * 74)
    saida = {"scorer": sc.VERSION_SCORE, "n_avaliados": len(obs),
             "min_trades": MIN_TRADES, "variantes": {}}

    for nome, _W, _k in variantes:
        v = resultados[nome]
        xs = v["s_raw"]
        piso = [i for i, x in enumerate(xs) if x <= 0.0]
        vivos = [i for i in range(len(xs))
                 if i not in set(piso) and i not in set(piso_base)]
        rho = spearman([base[i] for i in vivos], [xs[i] for i in vivos]) if vivos else None
        rho_todos = spearman(base, xs)
        ordem_b = sorted(range(len(base)), key=lambda i: -base[i])[:args.top]
        ordem_v = sorted(range(len(xs)), key=lambda i: -xs[i])[:args.top]
        over = len(set(ordem_b) & set(ordem_v))
        print("%-13s %7.4f %7.4f %7.2f %7.2f %4d/%-3d %8s %4d/%d" % (
            nome, v["w_sum"], v["dd_peso"],
            sum(xs) / len(xs), max(xs), len(piso), len(xs),
            ("%.4f" % rho) if rho is not None else "n/d",
            over, args.top))
        saida["variantes"][nome] = {
            "w_sum": v["w_sum"], "dd_peso": v["dd_peso"],
            "s_raw_medio": sum(xs) / len(xs), "s_raw_max": max(xs),
            "n_piso": len(piso), "n": len(xs),
            "rho_vs_base_sem_piso": rho, "rho_vs_base_com_piso": rho_todos,
            "top_overlap": over, "top_k": args.top,
            "bandas": dict(Counter(v["stage"])),
        }

    print()
    print("rho e Spearman contra a base entre os nao-pisados pelas duas; abaixo,")
    print("o mesmo incluindo os pisados, para a diferenca ficar visivel:")
    for nome in saida["variantes"]:
        d = saida["variantes"][nome]
        a = d["rho_vs_base_sem_piso"]
        b = d["rho_vs_base_com_piso"]
        print("  %-13s sem piso %8s   com piso %8s" % (
            nome,
            ("%.4f" % a) if a is not None else "n/d",
            ("%.4f" % b) if b is not None else "n/d"))

    print()
    print("bandas por variante:")
    ordem = ["EXPERIMENTAL", "PROMISING", "VERIFIED", "ELITE", "LEGENDARY"]
    print("  %-13s %s" % ("", "  ".join("%12s" % s for s in ordem)))
    for nome in saida["variantes"]:
        b = saida["variantes"][nome]["bandas"]
        print("  %-13s %s" % (nome, "  ".join("%12d" % b.get(s, 0) for s in ordem)))

    print()
    print("Como ler: se todos os rho sem piso ficarem acima de ~0,98 e o top%d"
          % args.top)
    print("mudar pouco, a escolha de pesos e de unidade do drawdown nao muda")
    print("quem fica na frente de quem, e deve ser decidida por simplicidade e")
    print("honestidade de nome -- o que favorece 1/N e nomear o campo pela")
    print("unidade que ele carrega. Se algum rho cair, a escolha e substantiva,")
    print("e a coluna do piso diz se a causa e reordenacao ou empate no zero.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(saida, fh, indent=2, ensure_ascii=False)
        print()
        print("gravado: %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sim_dd_cap.py — onde o teto da penalidade de drawdown deve ficar?

Somente leitura. Não toca no banco, não escreve score, não imprime endereço.

A FORMA TESTADA

    dd_pen = min(max_dd_r, CAP) * DD_PEN_WEIGHT

em vez de `max_dd_r * DD_PEN_WEIGHT`. Limitar o produto é idêntico a limitar
o fator, então isto se simula passando `min(max_dd_r, CAP)` como métrica --
sem alterar o scorer, o que mantém a simulação separada da implementação.

Os pesos são 1/N sobre os oito componentes vivos em todas as variantes com
teto, porque essa parte já foi decidida e medida (rho 0,9944 contra os pesos
calibrados, SPEC_CHANGE_v5.4.0). Aqui a única coisa que varia é o teto.

O QUE A SAÍDA RESPONDE

  piso     quantos saem com S_RAW = 0. No piso empatam, e empate é perda de
           ordenação. É o número que a forma sem teto faz crescer.
  empate   quantos ficam ACIMA do teto e portanto empatam entre si naquele
           componente -- o custo próprio desta forma, nomeado em vez de
           escondido
  rho      Spearman contra a base atual, entre os não-pisados pelas duas
  topo     sobreposição do top-20

A PERGUNTA

Se rho ficar praticamente igual entre os tetos, o teto move só nível e deve
ser escolhido pelo que ele diz -- a partir de quantos R a perda deixa de
mudar o veredito. Se rho mudar entre os tetos, o teto move ordenação e a
escolha é substantiva.

Uso:
    python3 sim_dd_cap.py [dir_payloads] [--scorer CAMINHO] [--caps 10,20,40]
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
MIN_TRADES = 30
CHAVE_DD = "max_dd_pct"      # o nome atual; D7_FINDINGS propoe max_dd_r


def carrega_scorer(caminho):
    spec = importlib.util.spec_from_file_location("sc", caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def postos(xs):
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
    if len(a) < 3:
        return None
    ra, rb = postos(a), postos(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((x - mb) ** 2 for x in rb))
    if da < 1e-12 or db < 1e-12:
        return None
    return num / (da * db)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payloads", nargs="?", default=PAYLOADS_PADRAO)
    ap.add_argument("--scorer", default=SCORER_PADRAO)
    ap.add_argument("--caps", default="10,20,40")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if not os.path.isdir(args.payloads):
        print("ABORTADO: nao achei %s" % args.payloads)
        return 2
    if not os.path.isfile(args.scorer):
        print("ABORTADO: nao achei %s" % args.scorer)
        return 2
    caps = [float(c) for c in args.caps.split(",") if c.strip()]

    sc = carrega_scorer(args.scorer)
    W_BASE = dict(sc.W)
    DD_W = sc.DD_PEN_WEIGHT
    n_comp = len(W_BASE)
    peso_igual = {k: 1.0 / n_comp for k in W_BASE}

    print("scorer        : %s" % sc.VERSION_SCORE)
    print("componentes   : %d   W_SUM %.4f   DD_PEN_WEIGHT %.4f"
          % (n_comp, sc.W_SUM, DD_W))
    print("1/N           : %.4f em cada um de: %s"
          % (1.0 / n_comp, " ".join(sorted(W_BASE))))
    print("chave do dd   : %s   (em R, conforme D7_FINDINGS)" % CHAVE_DD)
    print()

    obs = []
    arqs = sorted(f for f in os.listdir(args.payloads)
                  if f.endswith(".json") and not f.startswith("_"))
    lidos = pulados = erros = 0
    for nome in arqs:
        try:
            with open(os.path.join(args.payloads, nome), encoding="utf-8") as fh:
                p = json.load(fh)
        except Exception:
            erros += 1
            continue
        lidos += 1
        m = p.get("metrics") or {}
        t = p.get("trades") or []
        if int(m.get("trades") or 0) < MIN_TRADES:
            pulados += 1
            continue
        obs.append((sc.enrich_metrics_from_trades(dict(m), t), t))
    print("lidos %d   abaixo do piso %d   ilegiveis %d   avaliados %d"
          % (lidos, pulados, erros, len(obs)))
    if len(obs) < 10:
        print("ABORTADO: poucas observacoes.")
        return 1
    print()

    estado = {"ema": 300.0, "round_history": [], "total_trades": 0}

    def roda(W, cap):
        """cap None = sem teto. Devolve (s_raws, stages, n_acima_do_teto)."""
        sc.W = dict(W)
        sc.W_SUM = sum(W.values())
        sc.DD_PEN_WEIGHT = DD_W
        s_raws, stages, acima = [], [], 0
        for metrics, trades in obs:
            m = dict(metrics)
            v = m.get(CHAVE_DD)
            if cap is not None and isinstance(v, (int, float)):
                if float(v) > cap:
                    acima += 1
                m[CHAVE_DD] = min(float(v), cap)
            r = sc.yelden_score(metrics=m, state=dict(estado), trades=trades,
                                initial_balance=11000.0)
            s_raws.append(float(r["s_raw"]))
            stages.append(r["stage"])
        return s_raws, stages, acima

    variantes = [("base (W calibrado, sem teto)", W_BASE, None),
                 ("1/N  sem teto", peso_igual, None)]
    for c in caps:
        variantes.append(("1/N  teto %g R" % c, peso_igual, c))
    variantes.append(("1/N  sem dd (referencia)", peso_igual, 0.0))

    base_s, _bst, _ = roda(W_BASE, None)
    piso_base = set(i for i, v in enumerate(base_s) if v <= 0.0)

    saida = {"scorer": sc.VERSION_SCORE, "n": len(obs), "caps": caps,
             "variantes": {}}
    print("%-28s %7s %7s %6s %7s %8s %6s" %
          ("variante", "medio", "max", "piso", "empate", "rho", "top%d" % args.top))
    print("-" * 78)
    for nome, W, cap in variantes:
        xs, stages, acima = roda(W, cap)
        piso = set(i for i, x in enumerate(xs) if x <= 0.0)
        vivos = [i for i in range(len(xs)) if i not in piso and i not in piso_base]
        rho = spearman([base_s[i] for i in vivos], [xs[i] for i in vivos]) if vivos else None
        ob = sorted(range(len(base_s)), key=lambda i: -base_s[i])[:args.top]
        ov = sorted(range(len(xs)), key=lambda i: -xs[i])[:args.top]
        # cap == 0 e a referencia sem drawdown: ali "acima do teto" nao
        # significa empate, significa que o termo nao contribui. Reportar o
        # numero seria uma coluna enganosa numa ferramenta de decisao.
        emp = "   n/d " if cap == 0.0 else "%4d/%-3d" % (acima, len(xs))
        print("%-28s %7.2f %7.2f %3d/%-3d %8s %8s %3d/%d" % (
            nome, sum(xs) / len(xs), max(xs), len(piso), len(xs),
            emp, ("%.4f" % rho) if rho is not None else "n/d",
            len(set(ob) & set(ov)), args.top))
        saida["variantes"][nome] = {
            "cap": cap, "s_raw_medio": sum(xs) / len(xs), "s_raw_max": max(xs),
            "n_piso": len(piso),
            "n_acima_do_teto": (None if cap == 0.0 else acima), "n": len(xs),
            "rho_vs_base": rho, "top_overlap": len(set(ob) & set(ov)),
            "bandas": dict(Counter(stages)),
        }

    sc.W, sc.W_SUM, sc.DD_PEN_WEIGHT = W_BASE, sum(W_BASE.values()), DD_W

    print()
    print("empate = quantos ficam acima do teto e portanto recebem a mesma")
    print("penalidade. E o custo proprio desta forma: eles empatam NAQUELE")
    print("componente e continuam se diferenciando nos outros sete. Nao e o")
    print("mesmo que empatar em S_RAW = 0, que e perda total de ordenacao.")
    print()
    print("As bandas abaixo NAO sao evidencia sobre migracao de banda: todo")
    print("agente e pontuado de estado zerado, entao SISTEMA <= ~385 por")
    print("construcao e VERIFIED e inalcancavel em qualquer variante.")
    ordem = ["EXPERIMENTAL", "PROMISING", "VERIFIED", "ELITE", "LEGENDARY"]
    print("  %-28s %s" % ("", " ".join("%12s" % s for s in ordem)))
    for nome in saida["variantes"]:
        b = saida["variantes"][nome]["bandas"]
        print("  %-28s %s" % (nome, " ".join("%12d" % b.get(s, 0) for s in ordem)))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(saida, fh, indent=2, ensure_ascii=False)
        print()
        print("gravado: %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sim_steady_state.py - quantos agentes alcancam o limiar do contrato quando a
EMA converge, mantendo CF e SF nos valores medidos agora.

SO LE o banco. Nao escreve nada.

POR QUE ESTA MEDICAO EXISTE

  O re-score de 2026-10-09 zerou a EMA para EMA_INITIAL = 300 e, com uma
  observacao por endereco, a EMA de todos ficou em
  `0,85·300 + 0,15·S_RAW·10`, cujo maximo algebrico e 405. O limiar do
  contrato e 500. Logo zero elegiveis era forcado pela aritmetica, qualquer
  que fosse o desempenho -- nao e um resultado sobre os agentes.

  A pergunta que importa, entao, e quantos alcancam 500 quando a EMA
  convergir. E dai saiu um erro meu que esta medicao corrige: eu contei
  `S_RAW >= 50`, o que equivale a supor CF = SF = 1. Mas

      SISTEMA = EMA · CF · SF,   e   EMA -> S_RAW · 10

  entao a condicao e `S_RAW · CF · SF >= 50`, nao `S_RAW >= 50`. Numa amostra
  real CF·SF = 0,166, e com esse fator o teto de 500 exige
  `CF·SF >= 50/84,57 = 0,59` ate para o melhor S_RAW da populacao. Contar sem
  CF e SF superestima, e nao por pouco.

O QUE E, E O QUE NAO E

  E uma PROJECAO sob duas condicoes declaradas: a EMA converge, e CF e SF
  ficam onde estao hoje. Nao e previsao. CF cresce com o numero de trades
  (CF = min(sqrt(trades/CF_N_STAR), 1)) e SF depende da dispersao das
  pontuacoes, entao os dois se movem com coleta nova. Projecao com condicao
  nomeada e um numero publicavel; previsao disfarcada de projecao e o tipo de
  numero que o trabalho deste dia passou removendo.

  Tambem mede o SINAL, que e menos obvio que o nivel: para quem tem
  S_RAW < EMA_INITIAL/10 = 30, a EMA CAI de 300 em diante. Com S_RAW medio em
  torno de 25, a media do SISTEMA publicado tende a cair, nao a subir.

Uso:
    python3 sim_steady_state.py
    python3 sim_steady_state.py --json /root/yaaf/docs/evidence/steady_state.json
"""
import argparse
import json
import math
import os
import re
import sqlite3
import sys

OBS_PADRAO = "/root/aiagentregistry-observatory"
SCORER_PADRAO = "/root/yaaf/scorer/yaaf_score_v5_formal.py"

LATEST = """
SELECT address, ts, s_raw, sistema, stage, profile, payload FROM (
  SELECT address, ts, s_raw, sistema, stage, profile, payload,
         ROW_NUMBER() OVER (PARTITION BY address ORDER BY ts DESC, id DESC) rn
  FROM yaaf_scores
) WHERE rn = 1
"""


def constante(caminho, nome, conv=str):
    try:
        src = open(caminho, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"^%s\s*=\s*[\"']?([^\"'\s#]+)" % re.escape(nome), src, re.M)
    try:
        return conv(m.group(1)) if m else None
    except (TypeError, ValueError):
        return None


def perfis(api):
    try:
        src = open(api, encoding="utf-8").read()
    except OSError:
        return ()
    m = re.search(r"YAAF_PROFILES\s*=\s*[\(\[]([^\)\]]*)[\)\]]", src)
    return tuple(x.strip().strip("\"'") for x in m.group(1).split(",")
                 if x.strip()) if m else ()


def rodadas_para(alvo, ema0, ema_inf, alpha):
    """n tal que ema0 + (ema_inf-ema0)(1-(1-alpha)^n) >= alvo.

    Devolve None quando ema_inf nao alcanca o alvo: nenhum numero de rodadas
    resolve, e 'infinito' escrito como numero grande seria mentira."""
    if ema_inf < alvo:
        return None
    if ema0 >= alvo:
        return 0
    razao = (ema_inf - alvo) / (ema_inf - ema0)
    if razao <= 0:
        return 1
    return int(math.ceil(math.log(razao) / math.log(1.0 - alpha)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs", default=OBS_PADRAO)
    ap.add_argument("--scorer", default=SCORER_PADRAO)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    db = os.path.join(a.obs, "observatory.db")
    if not os.path.isfile(db):
        print("ABORTADO: nao achei %s" % db)
        return 2

    ema0 = constante(a.scorer, "EMA_INITIAL", float)
    versao = constante(a.scorer, "VERSION_SCORE")
    # O alpha entra na coluna de rodadas. Aceitar qualquer "0.15" solto no
    # fonte casaria com um peso e corromperia essa coluna em silencio, que e
    # pior do que nao ter a coluna. So duas formas sao aceitas, e o programa
    # diz qual usou.
    # ---- o alpha NAO vem de um nome -------------------------------------
    # Esta medicao ja errou aqui: o scorer declara EMA_ALPHA = 0,85, mas 0,85
    # e o DECAIMENTO (o peso da EMA anterior), nao o peso da observacao nova.
    # Lendo o nome, a coluna de rodadas saiu com 1 para todos os 34 -- e um
    # resultado uniforme assim e sintoma, nao achado.
    #
    # O alpha e derivado do proprio payload, que carrega ema_prev, ema_new e
    # s_raw:
    #     ema_new = (1-a)*ema_prev + a*s_raw*10
    #  => a = (ema_new - ema_prev) / (s_raw*10 - ema_prev)
    # As constantes nomeadas ficam como CONFERENCIA, nao como fonte: se
    # divergirem do dado, o dado manda e o programa diz que divergiram.
    src = open(a.scorer, encoding="utf-8").read()
    nomeadas = {}
    for nome in ("EMA_ALPHA", "EMA_SMOOTH", "EMA_DECAY", "EMA_LAMBDA", "EMA_BETA"):
        v = constante(a.scorer, nome, float)
        if v is not None:
            nomeadas[nome] = v

    sol = os.path.join(os.path.dirname(os.path.dirname(a.scorer)),
                       "contracts", "AIAgentRegistry.sol")
    try:
        limiar = int(re.search(r"SCORE_THRESHOLD_ACTIVE\s*=\s*(\d+)",
                               open(sol, encoding="utf-8").read()).group(1))
    except (OSError, AttributeError):
        limiar = None
    yaaf = perfis(os.path.join(a.obs, "scores_api.py"))
    if not yaaf or ema0 is None or limiar is None:
        print("ABORTADO: falta um parametro lido da fonte --")
        print("  EMA_INITIAL=%s  limiar=%s  perfis=%s"
              % (ema0, limiar, list(yaaf)))
        print("  Eu nao vou cravar nenhum deles aqui: valor cravado e livre")
        print("  para divergir do que o codigo usa.")
        return 2

    print("scorer %s   EMA_INITIAL %.1f   limiar do contrato %d"
          % (versao, ema0, limiar))
    if nomeadas:
        print("constantes de EMA no fonte (conferencia, nao fonte): %s"
              % "  ".join("%s=%g" % kv for kv in sorted(nomeadas.items())))
    print("perfis YAAF: %s" % list(yaaf))
    print()

    c = sqlite3.connect(db)
    agora_eleg = inf_eleg = 0
    sobem = descem = 0
    sem_fatores = []
    ags, soma_agora, soma_inf = [], 0.0, 0.0
    for addr, ts, s_raw, sistema, stage, profile, payload in c.execute(LATEST):
        if profile not in yaaf:
            continue
        try:
            p = json.loads(payload) if payload else {}
        except (ValueError, TypeError):
            p = {}
        if not isinstance(p, dict) or "cf" not in p or "sf" not in p:
            sem_fatores.append(addr)
            continue
        sr = p.get("s_raw")
        cf, sf = p.get("cf"), p.get("sf")
        if sr is None or cf is None or sf is None:
            sem_fatores.append(addr)
            continue
        ema_ag = p.get("ema_new")
        if ema_ag is None:
            ema_ag = (1 - alpha) * ema0 + alpha * sr * 10.0
        ema_inf = sr * 10.0
        sis_agora = p.get("sistema")
        if sis_agora is None:
            sis_agora = ema_ag * cf * sf
        sis_inf = ema_inf * cf * sf
        soma_agora += sis_agora
        soma_inf += sis_inf
        if sis_agora >= limiar:
            agora_eleg += 1
        if sis_inf >= limiar:
            inf_eleg += 1
        if ema_inf > ema_ag:
            sobem += 1
        else:
            descem += 1
        ags.append({"address": addr, "s_raw": sr, "cf": cf, "sf": sf,
                    "cf_sf": cf * sf, "sistema_agora": sis_agora,
                    "sistema_inf": sis_inf, "ema_agora": ema_ag,
                    "ema_inf": ema_inf, "ema_prev": p.get("ema_prev"),
                    "stage": stage, "versao": p.get("score_version")})
    c.close()

    n = len(ags)
    if not n:
        print("ABORTADO: nenhum registro YAAF com cf e sf no payload.")
        return 2

    # ---- alpha, derivado -------------------------------------------------
    cand = []
    for x in ags:
        ep, en, inf = x["ema_prev"], x["ema_agora"], x["ema_inf"]
        if ep is None or en is None or abs(inf - ep) < 1.0:
            continue            # denominador pequeno: estimativa sem precisao
        cand.append((en - ep) / (inf - ep))
    if not cand:
        print("ABORTADO: nenhum payload traz ema_prev/ema_new com separacao")
        print("  suficiente para derivar o alpha, e eu nao vou ler o nome:")
        print("  foi exatamente assim que a coluna de rodadas saiu errada.")
        return 2
    cand.sort()
    alpha = cand[len(cand) // 2]
    espalhamento = cand[-1] - cand[0]
    origem_alpha = "derivado de %d payloads (mediana)" % len(cand)

    print("alpha derivado do dado : %.6f   (%s)" % (alpha, origem_alpha))
    print("  espalhamento entre as estimativas: %.2e" % espalhamento)
    if espalhamento > 1e-6:
        print("  ATENCAO: as estimativas nao concordam. A suavizacao pode nao")
        print("  ser uniforme na populacao; a coluna de rodadas vale menos.")
    for nome, v in sorted(nomeadas.items()):
        if abs(v - alpha) < 1e-6:
            rel = "confere"
        elif abs((1.0 - v) - alpha) < 1e-6:
            rel = "e o DECAIMENTO (1 - alpha), apesar do nome"
        else:
            rel = "DIVERGE do dado -- o dado manda"
        print("  %-12s = %-8g %s" % (nome, v, rel))
    print()

    alvo_ema = {}
    for x in ags:
        x["rodadas"] = (rodadas_para(limiar / x["cf_sf"], x["ema_agora"],
                                     x["ema_inf"], alpha)
                        if x["cf_sf"] else None)

    print("registros YAAF com cf e sf no payload : %d" % n)
    if sem_fatores:
        print("registros YAAF SEM cf/sf (nao projetaveis): %d  %s"
              % (len(sem_fatores), [x[:12] for x in sem_fatores[:6]]))
        print("  (sao os produzidos por versao anterior; entram na contagem de")
        print("   registro velho, nao nesta projecao)")
    print()

    print("ELEGIVEIS (SISTEMA >= %d)" % limiar)
    print("  agora, uma observacao sob a EMA zerada : %d" % agora_eleg)
    print("  com a EMA convergida, CF e SF de hoje  : %d" % inf_eleg)
    print()
    print("O ERRO QUE ESTA MEDICAO CORRIGE")
    acima50 = sum(1 for x in ags if x["s_raw"] >= limiar / 10.0)
    print("  contando S_RAW >= %.0f, isto e supondo CF=SF=1 : %d"
          % (limiar / 10.0, acima50))
    print("  contando S_RAW * CF * SF >= %.0f, o correto     : %d"
          % (limiar / 10.0, inf_eleg))
    if acima50 == inf_eleg:
        print("  nesta populacao as duas contagens coincidem -- o que nao")
        print("  absolve a suposicao: ela so nao mordeu aqui.")
    else:
        print("  a suposicao CF=SF=1 %s a contagem em %d agentes"
              % ("inflava" if acima50 > inf_eleg else "deflacionava",
                 abs(acima50 - inf_eleg)))
    print()

    print("O SINAL, por endereco")
    print("  EMA sobe de %.0f (S_RAW*10 > EMA atual) : %d" % (ema0, sobem))
    print("  EMA desce de %.0f                       : %d" % (ema0, descem))
    print("  media do SISTEMA agora      : %.2f" % (soma_agora / n))
    print("  media do SISTEMA convergido : %.2f" % (soma_inf / n))
    print("  -> a media %s" % ("SOBE" if soma_inf > soma_agora else "DESCE"))
    print()

    print("DISTRIBUICAO de CF*SF, o fator que meu primeiro numero ignorou")
    for lo, hi in ((0, .1), (.1, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)):
        k = sum(1 for x in ags if lo <= x["cf_sf"] < hi)
        print("  %.1f a %.1f : %4d  %s" % (lo, hi, k, "#" * int(60.0 * k / n)))
    print()

    alvo = [x for x in ags if x["sistema_inf"] >= limiar]
    alvo.sort(key=lambda x: -x["sistema_inf"])
    if alvo:
        print("OS QUE ALCANCAM, e em quantos eventos de coleta")
        print("  %-14s %7s %6s %6s %9s %9s %s"
              % ("endereco", "s_raw", "cf", "sf", "agora", "convergido", "rodadas"))
        for x in alvo[:15]:
            print("  %-14s %7.2f %6.3f %6.3f %9.2f %9.2f %s"
                  % (x["address"][:12], x["s_raw"], x["cf"], x["sf"],
                     x["sistema_agora"], x["sistema_inf"],
                     x["rodadas"] if x["rodadas"] is not None else "nunca"))
        if len(alvo) > 15:
            print("  ... e %d outros" % (len(alvo) - 15))
    else:
        print("NENHUM agente alcanca %d com a EMA convergida e CF/SF de hoje." % limiar)
        print("  Isso nao e resultado sobre os agentes: e sobre o limiar contra")
        print("  a escala. O maximo projetado e %.2f, de %s."
              % (max(x["sistema_inf"] for x in ags),
                 max(ags, key=lambda x: x["sistema_inf"])["address"][:12]))
        print("  A decisao que isso abre e de especificacao, nao de dados:")
        print("  ou o limiar de %d esta calibrado contra uma escala que nao" % limiar)
        print("  existe mais, ou CF e SF nao deveriam multiplicar um limiar")
        print("  expresso na unidade da EMA.")
    print()
    top = max(ags, key=lambda x: x["sistema_inf"])
    print("teto projetado da populacao: %.2f  (%s, S_RAW %.2f, CF*SF %.3f)"
          % (top["sistema_inf"], top["address"][:12], top["s_raw"], top["cf_sf"]))

    if a.json:
        saida = {"scorer": versao, "ema_initial": ema0, "alpha": alpha,
                 "limiar": limiar, "n": n,
                 "elegiveis_agora": agora_eleg,
                 "elegiveis_convergido": inf_eleg,
                 "contagem_ingenua_s_raw_only": acima50,
                 "ema_sobe": sobem, "ema_desce": descem,
                 "media_sistema_agora": soma_agora / n,
                 "media_sistema_convergido": soma_inf / n,
                 "teto_projetado": top["sistema_inf"],
                 "sem_cf_sf": len(sem_fatores), "alpha_origem": origem_alpha,
                 "alpha_nomeado_no_fonte": nomeadas,
                 "alpha_espalhamento": espalhamento,
                 "condicoes": ("projecao sob EMA convergida mantendo CF e SF "
                               "nos valores medidos nesta rodada; nao e "
                               "previsao, porque CF cresce com trades e SF "
                               "depende da dispersao das pontuacoes"),
                 "agentes": sorted(ags, key=lambda x: -x["sistema_inf"])[:50]}
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(saida, fh, indent=2, sort_keys=True)
        print()
        print("json escrito: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())

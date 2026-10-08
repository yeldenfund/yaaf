#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calibration_d8.py — D8: a calibracao esta medindo habilidade ou maturidade?

NAO re-pontua nada. Le os payloads JA GRAVADOS em producao, onde CF e SF foram
calculados com o estado real do agente. Isso importa: todo script de medicao
desta serie passa `round_history: []`, o que forca SF=0 por construcao; o
SF real so existe no banco.

A pergunta:  sistema = ema x cf x sf.  Se CF=SF=1, sistema = ema.
Logo o contrafactual de calibracao e' simplesmente stage(ema), e o ema_new ja
esta em cada payload. Quantos agentes trocam de estagio e' a medida direta de
quanto da distribuicao de estagios e' calibracao em vez de desempenho.

Rodar de /root/aiagentregistry-observatory.
"""
import json
import os
import sqlite3
import sys
from collections import Counter

# A ORDEM IMPORTA: existe uma ic_test_gmx.py na raiz do repo (scipy, nao
# canonica) e a do protocolo em docs/evidence/. docs/evidence vem PRIMEIRO.
for _p in ("/root/aiagentregistry-observatory/docs/evidence",
           "/root/aiagentregistry-observatory",
           "/root/yaaf/scorer"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ic_test_gmx                        # noqa: E402
if not hasattr(ic_test_gmx, "spearman"):
    sys.exit(f"ABORTADO: {ic_test_gmx.__file__} nao e' o modulo canonico "
             "(sem funcao `spearman`). Esperado docs/evidence/ic_test_gmx.py.")
from ic_test_gmx import spearman           # noqa: E402  mesma implementacao
print(f"spearman importado de: {ic_test_gmx.__file__}")

YAAF_PROFILES = ("directional", "gmx", "scalper")
ORDEM = ["EXPERIMENTAL", "PROMISING", "VERIFIED", "ELITE", "LEGENDARY"]

LATEST = """
SELECT address, sistema, stage, profile, payload FROM (
  SELECT address, sistema, stage, profile, payload,
         ROW_NUMBER() OVER (PARTITION BY address ORDER BY ts DESC, id DESC) AS rn
  FROM yaaf_scores
) WHERE rn = 1
"""


def stage_of(score):
    if score is None:        return None
    if score < 200:          return "EXPERIMENTAL"
    if score < 400:          return "PROMISING"
    if score < 600:          return "VERIFIED"
    if score < 800:          return "ELITE"
    return "LEGENDARY"


def conn():
    try:
        from store import sqlite as db
        return db.conn()
    except Exception:
        return sqlite3.connect(os.getenv("SQLITE_PATH", "observatory.db"), timeout=10)


def q(v, p):
    v = sorted(v)
    if not v: return float("nan")
    i = p * (len(v) - 1); lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def dist(nome, v):
    if not v:
        print(f"  {nome:6} ausente nos payloads"); return
    z = sum(1 for x in v if x <= 1e-12)
    um = sum(1 for x in v if x >= 1 - 1e-12)
    print(f"  {nome:6} n={len(v):4d}  min {min(v):.4f}  p10 {q(v,.10):.4f}  "
          f"med {q(v,.50):.4f}  p90 {q(v,.90):.4f}  max {max(v):.4f}")
    print(f"         ={0:<1}: {z:4d} ({100*z/len(v):5.1f}%)    "
          f"=1 (saturado): {um:4d} ({100*um/len(v):5.1f}%)")


def main():
    c = conn()
    rows = c.execute(LATEST).fetchall()
    ag = []
    sem_cf = 0
    for address, sistema, stage_db, profile, payload in rows:
        if profile not in YAAF_PROFILES:
            continue
        try:
            p = json.loads(payload) if payload else {}
        except Exception:
            p = {}
        if not isinstance(p, dict):
            p = {}
        cf, sf, ema = p.get("cf"), p.get("sf"), p.get("ema_new")
        if cf is None or sf is None or ema is None:
            sem_cf += 1
            continue
        ag.append({"address": address, "sistema": sistema, "stage": stage_db,
                   "cf": float(cf), "sf": float(sf), "ema": float(ema),
                   "s_raw": p.get("s_raw"), "trades": p.get("new_state", {}).get("total_trades")})
    c.close()

    print(f"agentes YAAF com cf/sf/ema no payload: {len(ag)}")
    if sem_cf:
        print(f"  (descartados por payload sem esses campos: {sem_cf})")
    if len(ag) < 10:
        print("amostra insuficiente"); return

    print("\n" + "=" * 72)
    print("DISTRIBUICAO DOS FATORES DE CALIBRACAO (valores reais de producao)")
    print("=" * 72)
    dist("CF", [a["cf"] for a in ag])
    dist("SF", [a["sf"] for a in ag])
    print("  CF = min(sqrt(trades/250),1)  — funcao deterministica da contagem.")
    print("  SF = min(media/45,1)*(1-sigma/25)+  — historico de rodadas.")

    produto = [a["cf"] * a["sf"] for a in ag]
    print()
    dist("CFxSF", produto)
    print(f"  Leitura: CFxSF e' o fator pelo qual a calibracao MULTIPLICA o EMA.")
    print(f"  Mediana {q(produto,.50):.4f} significa que o agente mediano perde "
          f"{100*(1-q(produto,.50)):.1f}% do score por maturidade.")

    print("\n" + "=" * 72)
    print("CONTRAFACTUAL: QUANTOS TROCAM DE ESTAGIO SE CF=SF=1")
    print("=" * 72)
    real, contra = Counter(), Counter()
    sobe, transicoes = 0, Counter()
    for a in ag:
        r = stage_of(a["sistema"]); k = stage_of(a["ema"])
        a["stage_contra"] = k
        real[r] += 1; contra[k] += 1
        if r != k:
            sobe += 1
            transicoes[f"{r} -> {k}"] += 1

    print(f"  {'estagio':<14} {'real':>6} {'CF=SF=1':>9} {'delta':>7}")
    for s in ORDEM:
        print(f"  {s:<14} {real[s]:>6} {contra[s]:>9} {contra[s]-real[s]:>+7}")
    print(f"\n  trocam de estagio: {sobe} de {len(ag)} ({100*sobe/len(ag):.1f}%)")
    for t, n in transicoes.most_common():
        print(f"    {t:<30} {n}")

    exp_real = real["EXPERIMENTAL"]
    exp_sai = sum(n for t, n in transicoes.items() if t.startswith("EXPERIMENTAL ->"))
    if exp_real:
        print(f"\n  >>> dos {exp_real} EXPERIMENTAL, {exp_sai} "
              f"({100*exp_sai/exp_real:.1f}%) sairiam com CF=SF=1")
        if exp_sai / exp_real > 0.5:
            print("  >>> VEREDITO: a maioria dos EXPERIMENTAL esta nesse estagio por")
            print("      CALIBRACAO, nao por desempenho. D8 e' o fator dominante na")
            print("      distribuicao de estagios, e ela nao descreve os agentes.")
        elif exp_sai / exp_real > 0.15:
            print("  >>> VEREDITO: parcela relevante e' calibracao. A distribuicao")
            print("      mistura as duas causas e nao pode ser citada sem a ressalva.")
        else:
            print("  >>> VEREDITO: a calibracao nao e' o que mantem esses agentes em")
            print("      EXPERIMENTAL. Sao os scores. D8 e' real mas nao e' o binding.")

    print("\n" + "=" * 72)
    print("ELEGIBILIDADE")
    print("=" * 72)
    el_r = sum(1 for a in ag if (a["sistema"] or 0) >= 600)
    el_c = sum(1 for a in ag if a["ema"] >= 600)
    print(f"  SISTEMA >= 600 (ELITE+)   real {el_r}   com CF=SF=1 {el_c}")

    print("\n" + "=" * 72)
    print("O QUE GOVERNA O SISTEMA: O SCORE OU A CALIBRACAO?")
    print("=" * 72)
    sis = [a["sistema"] for a in ag if a["sistema"] is not None]
    idx = [i for i, a in enumerate(ag) if a["sistema"] is not None]
    for rot, key in (("EMA (o score)", "ema"), ("CF", "cf"), ("SF", "sf")):
        v = [ag[i][key] for i in idx]
        rho, p, lo, hi = spearman(v, sis)
        pp = f"p={p:.4g}" if p is not None else "p=—"
        print(f"  SISTEMA ~ {rot:<14} rho={rho:+.4f}  {pp}")
    rho_prod = spearman([ag[i]["cf"] * ag[i]["sf"] for i in idx], sis)[0]
    print(f"  SISTEMA ~ CFxSF          rho={rho_prod:+.4f}")
    print("\n  Se SISTEMA~CFxSF rivalizar com SISTEMA~EMA, o ranking publicado")
    print("  esta ordenando maturidade tanto quanto habilidade.")

    out = "docs/evidence/calibration_d8_result.json"
    os.makedirs("docs/evidence", exist_ok=True)
    with open(out, "w") as f:
        json.dump({
            "n": len(ag),
            "cf": {"mediana": q([a["cf"] for a in ag], .50),
                   "saturados": sum(1 for a in ag if a["cf"] >= 1 - 1e-12)},
            "sf": {"mediana": q([a["sf"] for a in ag], .50),
                   "zerados": sum(1 for a in ag if a["sf"] <= 1e-12)},
            "cf_x_sf_mediana": q(produto, .50),
            "estagios_reais": dict(real),
            "estagios_contrafactuais": dict(contra),
            "transicoes": dict(transicoes),
            "trocam_de_estagio": sobe,
            "elite_mais_real": el_r, "elite_mais_contrafactual": el_c,
            "agentes": ag,
        }, f, indent=2, default=str)
    print(f"\n[ok] {out}")


if __name__ == "__main__":
    main()

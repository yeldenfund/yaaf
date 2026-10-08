#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sf_gate.py — por que SF = 0 para 63.9% dos agentes?

SF = min(s_bar/45, 1) * (1 - sigma_s/25)+   sobre o round_history.

Ele zera por duas causas de significado OPOSTO:
  A) s_bar ~ 0      -> historico vazio/zerado: NAO MENSURAVEL AINDA
  B) sigma_s >= 25  -> scores dispersos: MEDIDO COMO INCONSISTENTE

As duas produzem SISTEMA = 0 exato, indistinguiveis na API. (A) nao deveria
sair como zero; deveria sair como nulo. Separar as duas decide se o conserto e'
de apresentacao ou de formula.

Le payloads gravados. Nao re-pontua nada. Rodar de /root/aiagentregistry-observatory.
"""
import json
import os
import sqlite3
import statistics as st
import sys
from collections import Counter

for _p in ("/root/aiagentregistry-observatory/docs/evidence",
           "/root/aiagentregistry-observatory"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ic_test_gmx                                   # noqa: E402
if not hasattr(ic_test_gmx, "spearman"):
    sys.exit(f"ABORTADO: {ic_test_gmx.__file__} nao e' o modulo canonico.")
from ic_test_gmx import spearman                     # noqa: E402

YAAF_PROFILES = ("directional", "gmx", "scalper")
SF_LEVEL_REF, SF_DISP_REF = 45.0, 25.0

LATEST = """
SELECT address, sistema, stage, profile, payload FROM (
  SELECT address, sistema, stage, profile, payload,
         ROW_NUMBER() OVER (PARTITION BY address ORDER BY ts DESC, id DESC) AS rn
  FROM yaaf_scores
) WHERE rn = 1
"""


def conn():
    try:
        from store import sqlite as db
        return db.conn()
    except Exception:
        return sqlite3.connect(os.getenv("SQLITE_PATH", "observatory.db"), timeout=10)


def q(v, p):
    v = sorted(v)
    if not v: return float("nan")
    i = p*(len(v)-1); lo, hi = int(i), min(int(i)+1, len(v)-1)
    return v[lo] + (v[hi]-v[lo])*(i-lo)


def main():
    c = conn(); rows = c.execute(LATEST).fetchall(); c.close()
    ag = []
    for address, sistema, stage, profile, payload in rows:
        if profile not in YAAF_PROFILES:
            continue
        try:
            p = json.loads(payload) if payload else {}
        except Exception:
            continue
        if not isinstance(p, dict) or p.get("sf") is None:
            continue
        h = (p.get("new_state") or {}).get("round_history") or []
        h = [float(x) for x in h if isinstance(x, (int, float))]
        ag.append({"address": address, "sistema": sistema, "sf": float(p["sf"]),
                   "cf": float(p.get("cf") or 0.0), "ema": p.get("ema_new"),
                   "s_raw": p.get("s_raw"), "hist": h,
                   "s_bar": (sum(h)/len(h)) if h else 0.0,
                   "sigma": st.pstdev(h) if len(h) > 1 else 0.0,
                   "n_hist": len(h)})
    print(f"agentes YAAF com sf e payload: {len(ag)}\n")
    if len(ag) < 10:
        print("amostra insuficiente"); return

    print("=" * 72)
    print("TAMANHO DO round_history")
    print("=" * 72)
    nh = [a["n_hist"] for a in ag]
    print(f"  n min/p10/med/p90/max : {min(nh)} / {q(nh,.10):.0f} / "
          f"{q(nh,.50):.0f} / {q(nh,.90):.0f} / {max(nh)}")
    print(f"  historico VAZIO       : {sum(1 for x in nh if x == 0)} "
          f"({100*sum(1 for x in nh if x==0)/len(ag):.1f}%)")
    print(f"  com 1 so entrada      : {sum(1 for x in nh if x == 1)}")
    print(f"  SF_WINDOW do scorer   : 8")

    zer = [a for a in ag if a["sf"] <= 1e-12]
    print("\n" + "=" * 72)
    print(f"CAUSA DO SF = 0   ({len(zer)} agentes)")
    print("=" * 72)
    causa = Counter()
    for a in zer:
        vazio = a["n_hist"] == 0
        nivel = a["s_bar"] <= 1e-9
        disp = a["sigma"] >= SF_DISP_REF
        if vazio:                 causa["A1 historico vazio"] += 1
        elif nivel and disp:      causa["A+B nivel zero E disperso"] += 1
        elif nivel:               causa["A2 nivel zero (s_bar=0)"] += 1
        elif disp:                causa["B dispersao >= 25"] += 1
        else:                     causa["? nao explicado"] += 1
    for k, v in causa.most_common():
        print(f"  {k:<32} {v:4d}  ({100*v/len(zer):5.1f}%)")

    nao_mens = sum(v for k, v in causa.items() if k.startswith("A"))
    incons = causa["B dispersao >= 25"]
    print(f"\n  NAO MENSURAVEL (A) : {nao_mens}  -> SISTEMA deveria ser NULO, nao 0")
    print(f"  INCONSISTENTE  (B) : {incons}  -> SISTEMA 0 e' um veredito legitimo")
    if causa["? nao explicado"]:
        print(f"  [ALERTA] {causa['? nao explicado']} com SF=0 que nenhuma das duas explica")
        for a in zer:
            if a["s_bar"] > 1e-9 and a["sigma"] < SF_DISP_REF:
                print(f"    {a['address'][:14]}… s_bar={a['s_bar']:.4f} "
                      f"sigma={a['sigma']:.4f} n={a['n_hist']} sf={a['sf']}")
                break

    print("\n" + "=" * 72)
    print("O INCENTIVO PERVERSO: operar mais aumenta a dispersao?")
    print("=" * 72)
    com = [a for a in ag if a["n_hist"] > 1]
    if len(com) > 4:
        for rot, k in (("CF ~ sigma_s", "cf"), ("CF ~ SF", "cf")):
            pass
        rho1 = spearman([a["cf"] for a in com], [a["sigma"] for a in com])[0]
        rho2 = spearman([a["cf"] for a in com], [a["sf"] for a in com])[0]
        rho3 = spearman([a["s_bar"] for a in com], [a["sigma"] for a in com])[0]
        print(f"  CF    ~ sigma_s  rho={rho1:+.4f}   (CF cresce com n_trades)")
        print(f"  CF    ~ SF       rho={rho2:+.4f}")
        print(f"  s_bar ~ sigma_s  rho={rho3:+.4f}")
        print(f"  n={len(com)} agentes com historico > 1")
        if rho1 > 0.2 and rho2 < -0.2:
            print("\n  >>> CONFIRMADO: mais trades -> mais dispersao -> SF menor.")
            print("      Operar mais reduz o SISTEMA. Incentivo perverso real.")
        elif rho2 < -0.2:
            print("\n  >>> CF e SF se opoem, mas nao via dispersao. Investigar.")
        else:
            print("\n  >>> NAO confirmado. O CF negativo tem outra origem.")

    print("\n" + "=" * 72)
    print("QUANTO DO RANKING E' PERDIDO NO PORTAO")
    print("=" * 72)
    emp = [a for a in ag if (a["sistema"] or 0) <= 1e-12]
    print(f"  agentes com SISTEMA = 0 : {len(emp)} de {len(ag)} "
          f"({100*len(emp)/len(ag):.1f}%)")
    if emp:
        e = [a["ema"] for a in emp if a["ema"] is not None]
        if e:
            print(f"  entre eles, EMA vai de {min(e):.1f} a {max(e):.1f} "
                  f"(mediana {q(e,.50):.1f})")
            print(f"  -> {len(e)} agentes distinguiveis pelo score aparecem")
            print(f"     indistinguiveis no leaderboard, em ordem arbitraria.")

    out = "docs/evidence/sf_gate_result.json"
    os.makedirs("docs/evidence", exist_ok=True)
    with open(out, "w") as f:
        json.dump({"n": len(ag), "sf_zero": len(zer), "causas": dict(causa),
                   "nao_mensuravel": nao_mens, "inconsistente": incons,
                   "sistema_zero": len(emp),
                   "agentes": [{k: v for k, v in a.items() if k != "hist"}
                               for a in ag]}, f, indent=2, default=str)
    print(f"\n[ok] {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ic_diagnostics.py — qualifica o resultado de ic_test_gmx.py sem alterar o numero.

NAO e' uma segunda medicao. Nao escolhe horizonte, nao mexe em filtro, nao
reporta rho alternativo como resultado. Responde a tres perguntas que decidem
se o rho=0.6577 vale o que parece valer:

  1. A distribuicao de S_RAW e' degenerada? Se os 31 agentes caem numa faixa
     estreita, o Spearman ordena ruido.
  2. Existe caminho de contaminacao por contagem de trades?
     S_RAW -> n_trades -> soma de R e' o mecanismo de inflacao mais plausivel.
  3. Ha agentes clonados? Mesma estrategia em varios enderecos reduz o n
     efetivo, e o n efetivo e' o que determina o intervalo de confianca.

Se (3) encontrar clones, a rodada e' INVALIDA e exige nova versao do protocolo
com regra de deduplicacao declarada antes de medir de novo. Nao se escolhe o
numero melhor entre os dois.

Rodar de /root/aiagentregistry-observatory.
"""
import json
import sys
from itertools import combinations
from pathlib import Path

OBS = Path("/root/aiagentregistry-observatory")
EVID = Path("docs/evidence")
RES = EVID / "ic_test_gmx_result.json"

sys.path.insert(0, str(EVID))
from ic_test_gmx import spearman          # noqa: E402  mesma implementacao, nao outra


def quantil(v, q):
    v = sorted(v)
    i = q * (len(v) - 1)
    lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def load_payloads():
    """Devolve {agent_id: [(arquivo, payload), ...]} — lista, para detectar colisao."""
    por_id = {}
    for f in sorted((OBS / "yaaf_payloads_gmx").glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("trades"), list):
            por_id.setdefault(d.get("agent_id", "?"), []).append((f.name, d))
    return por_id


def main():
    res = json.loads(RES.read_text())
    obs = res["observacoes"]
    corte = float(res["corte_exit_time"])
    n = len(obs)
    print(f"resultado lido: n={n}  corte={res['corte_data']}")
    print(f"scorer={res['scorer_version']}\n")

    # ── 1. distribuicao de S_RAW ────────────────────────────────────────────
    s = [o["sraw_t1"] for o in obs]
    print("1) DISTRIBUICAO DE S_RAW EM T1")
    print(f"   valores distintos : {len(set(s))} de {n}")
    print(f"   min / p25 / mediana / p75 / max :")
    print(f"   {min(s):.4f} / {quantil(s,.25):.4f} / {quantil(s,.50):.4f} / "
          f"{quantil(s,.75):.4f} / {max(s):.4f}")
    amp = max(s) - min(s)
    print(f"   amplitude : {amp:.4f}")
    if len(set(s)) < n * 0.8:
        print("   [ALERTA] muitos empates — os postos estao ordenando pouco")
    if amp < 1.0:
        print("   [ALERTA] amplitude estreita — diferencas podem ser ruido")
    print()

    # ── 2. contaminacao por contagem de trades ─────────────────────────────
    n1 = [o["n_t1"] for o in obs]
    n2 = [o["n_t2"] for o in obs]
    somar = [o["sum_r_t2"] for o in obs]
    print("2) CAMINHO DE CONTAMINACAO POR VOLUME")
    for rotulo, a, b in (("S_RAW(T1) ~ n_t1", s, n1),
                         ("S_RAW(T1) ~ n_t2", s, n2),
                         ("n_t2 ~ soma_R(T2)", n2, somar),
                         ("n_t1 ~ n_t2", n1, n2)):
        rho, p, lo, hi = spearman(a, b)
        pp = f"p={p:.4f}" if p is not None else "p=—"
        print(f"   {rotulo:22} rho={rho:+.4f}  {pp}")
    print("   Leitura: se S_RAW~n_t2 e n_t2~soma_R forem ambos fortes, parte do")
    print("   rho primario e' volume, nao qualidade. O controle direto e' o")
    print("   horizonte secundario (media de R), que nao soma com o n.")
    print(f"   primario  = {res['resultados']['primario_soma_r']['rho']:+.4f}")
    print(f"   secundario= {res['resultados']['secundario_media_r']['rho']:+.4f}")
    print()

    # ── 3. clones ──────────────────────────────────────────────────────────
    print("3) AGENTES CLONADOS (n EFETIVO)")
    por_id = load_payloads()
    colisoes = {k: [f for f, _ in v] for k, v in por_id.items() if len(v) > 1}
    if colisoes:
        print(f"   [ALERTA] agent_id repetido em arquivos distintos: {colisoes}")

    medidos = [o["agent"] for o in obs]
    t1_sets, faltando = {}, []
    for a in medidos:
        v = por_id.get(a)
        if not v:
            faltando.append(a); continue
        _, d = v[0]
        t1_sets[a] = {round(float(t["exit_time"]), 0) for t in d["trades"]
                      if t.get("exit_time") is not None and float(t["exit_time"]) < corte}
    if faltando:
        print(f"   [ALERTA] nao reencontrados no payload: {faltando}")

    pares = []
    for a, b in combinations(sorted(t1_sets), 2):
        A, B = t1_sets[a], t1_sets[b]
        if not A or not B:
            continue
        j = len(A & B) / len(A | B)
        if j > 0.30:
            pares.append((j, a, b, len(A), len(B), len(A & B)))
    pares.sort(reverse=True)

    if not pares:
        print(f"   nenhum par com Jaccard > 0.30 sobre os exit_time de T1.")
        print(f"   n efetivo = {n} (igual ao n reportado)")
    else:
        print(f"   {len(pares)} par(es) suspeito(s):")
        for j, a, b, na, nb, inter in pares[:20]:
            print(f"     J={j:.3f}  {a[:12]}… x {b[:12]}…  |T1|={na}/{nb} inter={inter}")
        print("   [ALERTA] rodada invalida enquanto isso nao for explicado.")
        print("   Se forem clones, o protocolo precisa de regra de deduplicacao")
        print("   declarada ANTES da proxima medicao.")

    out = EVID / "ic_diagnostics_result.json"
    out.write_text(json.dumps({
        "n": n,
        "sraw_distintos": len(set(s)),
        "sraw_min": min(s), "sraw_max": max(s), "sraw_mediana": quantil(s, .50),
        "pares_jaccard_acima_030": [
            {"jaccard": j, "a": a, "b": b, "n_a": na, "n_b": nb, "intersecao": i}
            for j, a, b, na, nb, i in pares],
        "colisoes_agent_id": colisoes,
    }, indent=2, default=str))
    print(f"\n[ok] {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Mede o efeito da selecao do universo sobre o rho canonico.

O universo dos 500 foi gerado por discover_gmx.py: ranking por PnL agregado em
dolares numa janela que termina em 2026-10-06, metade de cima + metade de baixo.
A janela termina dentro de T2, logo o universo foi escolhido usando informacao do
periodo que o horizonte primario mede.

Este script NAO recalcula S_RAW. Le a tabela por agente do resultado e o arquivo
de descoberta, e computa:

  1. rho global          -> guard de reproducao contra o valor publicado
  2. rho dentro do topo  -> sem truncamento do meio do desfecho
  3. rho dentro da base  -> idem
  4. rho(PnL descoberta, horizonte) -> quanto a variavel de selecao se relaciona
     com cada horizonte

Imprime. Nao conclui.

Uso:
  python3 selection_check.py /root/aiagentregistry-observatory/docs/evidence/ic_test_gmx_v2_result.json \
                             /root/aiagentregistry-observatory/wallets_gmx.txt
"""
import json
import re
import sys

import numpy as np
from scipy import stats

RHO_PUBLICADO = 0.2540
RHO_SECUNDARIO = 0.2629
CAND_MEANR = ["mean_r_t2", "media_r_t2", "mean_r"]
TOL = 5e-4          # o valor publicado tem 4 casas

CAND_LISTA = ["observacoes", "agentes", "agents", "per_agent", "resultados", "obs"]
CAND_ADDR = ["agent", "address", "addr", "conta", "account"]
CAND_SRAW = ["s_raw", "sraw", "S_RAW"]
CAND_R = ["sum_r_t2", "fwd_sum_r", "soma_r_t2", "t2_sum_r", "sum_r", "fwd_r", "r_t2"]
CAND_PNL = ["sum_pnl_t2", "fwd_sum_pnl", "soma_pnl_t2", "t2_sum_pnl", "sum_pnl", "pnl_t2"]


def escolher(nomes, candidatos, rotulo, exemplo):
    for c in candidatos:
        if c in nomes:
            return c
    print(f"\nNAO ENCONTREI o campo de {rotulo}.")
    print(f"  candidatos testados: {candidatos}")
    print(f"  campos disponiveis: {sorted(nomes)}")
    print(f"  primeiro registro: {json.dumps(exemplo, default=str)[:400]}")
    print("\nAjuste a lista CAND_* no topo do script com o nome correto e rode de novo.")
    sys.exit(2)


def sp(x, y, rotulo):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 10:
        print(f"  {rotulo:<44} n={n:<4} (menos de 10, nao computado)")
        return None
    r, p = stats.spearmanr(x[ok], y[ok])
    z = np.arctanh(r)
    se = 1.0 / np.sqrt(n - 3)
    lo, hi = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)
    print(f"  {rotulo:<44} n={n:<4} rho={r:+.4f}  p={p:.4f}  IC95 [{lo:+.4f}, {hi:+.4f}]")
    return r


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    res = json.load(open(sys.argv[1], encoding="utf-8"))

    chave = next((k for k in CAND_LISTA if isinstance(res.get(k), list) and res[k]), None)
    if chave is None:
        listas = {k: len(v) for k, v in res.items() if isinstance(v, list)}
        print("NAO ENCONTREI a tabela por agente.")
        print(f"  chaves de topo: {sorted(res)}")
        print(f"  listas no JSON: {listas}")
        return 2
    tab = res[chave]
    nomes = set(tab[0])
    print(f"tabela por agente: '{chave}', {len(tab)} registros")
    print(f"campos: {sorted(nomes)}\n")

    f_addr = escolher(nomes, CAND_ADDR, "endereco", tab[0])
    f_sraw = escolher(nomes, CAND_SRAW, "S_RAW", tab[0])
    f_r = escolher(nomes, CAND_R, "soma de R em T2", tab[0])
    f_pnl = next((c for c in CAND_PNL if c in nomes), None)
    f_mean = next((c for c in CAND_MEANR if c in nomes), None)
    print(f"usando: addr={f_addr}  s_raw={f_sraw}  R_T2={f_r}  "
          f"PnL_T2={f_pnl or '(ausente)'}  mediaR_T2={f_mean or '(ausente)'}")
    for k in ("janela", "corte_data", "corte", "window"):
        if k in res:
            print(f"{k}: {res[k]}")
    print()

    # ---- arquivo de descoberta: a ORDEM das linhas da o grupo ----
    pat = re.compile(r"^(0x[0-9a-fA-F]{40})\s*#\s*pnl=(-?[\d.]+)\s+trades=(\d+)\s+liq=(\d+)")
    desc = []
    for linha in open(sys.argv[2], encoding="utf-8"):
        m = pat.match(linha.strip())
        if m:
            desc.append((m.group(1).lower(), float(m.group(2)), int(m.group(3)), int(m.group(4))))
    print(f"descoberta: {len(desc)} linhas parseadas de {sys.argv[2]}")
    if not desc:
        print("  o formato nao bate com 'addr  # pnl= trades= liq='. Pare e cole 3 linhas do arquivo.")
        return 2

    meio = len(desc) // 2
    grupo = {a: ("topo" if i < meio else "base") for i, (a, *_) in enumerate(desc)}
    dpnl = {a: p for a, p, _, _ in desc}
    dliq = {a: l for a, _, _, l in desc}
    min_topo = min(p for a, p, _, _ in desc[:meio])
    max_base = max(p for a, p, _, _ in desc[meio:])
    print(f"corte por ordem de linha em {meio}: min(PnL topo)={min_topo:,.2f}  max(PnL base)={max_base:,.2f}")
    if min_topo <= max_base:
        print("  ATENCAO: os grupos se sobrepoem em PnL. A ordem das linhas pode nao refletir"
              " top/bottom (dedupe do discover). Os grupos abaixo sao por ordem de linha.")
    print(f"liquidacoes na descoberta: topo {sum(dliq[a] for a,*_ in desc[:meio])}, "
          f"base {sum(dliq[a] for a,*_ in desc[meio:])}")

    # ---- join ----
    med, faltam = [], []
    for o in tab:
        a = str(o[f_addr]).lower()
        if a in grupo:
            med.append((a, float(o[f_sraw]), float(o[f_r]),
                        float(o[f_pnl]) if f_pnl else np.nan,
                        float(o[f_mean]) if f_mean else np.nan))
        else:
            faltam.append(o[f_addr])
    print(f"\njoin: {len(med)} de {len(tab)} medidos casaram com o arquivo de descoberta")
    if faltam:
        print(f"  NAO casaram ({len(faltam)}): {faltam[:5]}")
        print("  o arquivo de descoberta nao e o universo declarado; pare e verifique.")
        return 2

    sraw = [m[1] for m in med]
    rr = [m[2] for m in med]
    pp = [m[3] for m in med]
    mr = [m[4] for m in med]
    gp = [grupo[m[0]] for m in med]
    dp = [dpnl[m[0]] for m in med]

    print("\n=== guard de reproducao ===")
    r_glob = sp(sraw, rr, "S_RAW x soma de R em T2 (global)")
    if r_glob is None or abs(r_glob - RHO_PUBLICADO) > TOL:
        print(f"\n  ABORTADO: o rho global ({r_glob}) nao reproduz o publicado "
              f"({RHO_PUBLICADO:+.4f}) dentro de {TOL}.")
        print("  Campo de horizonte errado, ou a tabela nao e a da corrida canonica.")
        print("  Nenhum numero abaixo seria interpretavel; nada mais foi computado.")
        return 1
    print(f"  reproduz o publicado {RHO_PUBLICADO:+.4f}")
    if f_mean:
        r_sec = sp(sraw, mr, "S_RAW x media de R em T2 (secundario)")
        if r_sec is not None:
            d = abs(r_sec - RHO_SECUNDARIO)
            print(f"  secundario publicado {RHO_SECUNDARIO:+.4f}, diferenca {d:.4f}"
                  f"{'' if d <= TOL else '   <-- DIVERGE, nao abortei porque o guard primario passou'}")

    print("\n=== dentro de cada grupo (sem truncamento do meio do desfecho) ===")
    for g in ("topo", "base"):
        idx = [i for i, x in enumerate(gp) if x == g]
        n_g = len(idx)
        print(f"  grupo {g}: {n_g} agentes medidos")
        sp([sraw[i] for i in idx], [rr[i] for i in idx], f"    S_RAW x soma R  [{g}]")
        if f_mean:
            sp([sraw[i] for i in idx], [mr[i] for i in idx], f"    S_RAW x media R [{g}]")
        if f_pnl:
            sp([sraw[i] for i in idx], [pp[i] for i in idx], f"    S_RAW x soma PnL [{g}]")

    print("\n=== a variavel de selecao contra os horizontes ===")
    sp(dp, rr, "PnL da descoberta x soma de R em T2")
    if f_mean:
        sp(dp, mr, "PnL da descoberta x media de R em T2")
    if f_pnl:
        sp(dp, pp, "PnL da descoberta x soma de PnL em T2")
    sp(dp, sraw, "PnL da descoberta x S_RAW (T1)")

    if f_pnl:
        print("\n=== horizonte terciario, para comparar com o 0.0092 publicado ===")
        sp(sraw, pp, "S_RAW x soma de PnL em T2 (global)")

    print("\nfim. nenhum veredito foi escrito neste script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

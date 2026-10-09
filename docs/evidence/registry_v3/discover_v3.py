#!/usr/bin/env python3
"""
discover_v3.py — descoberta cega ao desfecho, sob IC_PROTOCOL_v3.md.

Diferencas deliberadas em relacao ao discover_gmx.py:

  * until_ts e o INSTANTE DO CORTE, nunca time.time(). A descoberta nao pode ver T2.
  * nenhuma ordenacao. Este script NAO CALCULA PnL em ponto nenhum, de proposito:
    nao da para ordenar pelo que nao se computou.
  * enderecos em EIP-55 via to_checksum_address, nunca minusculizados (D9).
  * a paginacao deduplica. O discover_gmx.py avanca cursor = last_ts e refaz a
    ultima pagina, o que infla contagens; aqui as acoes repetidas sao contadas
    uma vez e o total descartado e reportado.
  * grava a proveniencia do protocolo (blob + commit + data) na saida, e aborta
    se o arquivo do protocolo estiver sujo ou nao commitado.

Subcomandos:
  pool       monta o pool de candidatos ativos antes do corte (nao e o universo)
  registry   normaliza a lista do registry para o formato do universo
  draw       sorteia o suplemento com a seed declarada, se o gatilho disparar

Uso:
  python3 discover_v3.py pool
  python3 discover_v3.py registry --in <arquivo_do_registry>
  python3 discover_v3.py draw --passaram <n>
"""
import argparse
import json
import random
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from eth_utils import to_checksum_address

from collectors.gmx import fetch_trade_actions          # producao, nao reimplementado

# --- declarado no IC_PROTOCOL_v3.md, nao ajustavel aqui ---
CORTE_ISO = "2026-08-20T00:00:00+00:00"
JANELA_DIAS = 180
MIN_ACOES_POOL = 30
SEED = 20260820
GATILHO_REGISTRY = 100
TOTAL_ALVO = 400
PROTO = Path("/root/yaaf/docs/IC_PROTOCOL_v3.md")
SCORER = Path("/root/yaaf/scorer/yaaf_score_v5_formal.py")

CORTE_TS = int(datetime.fromisoformat(CORTE_ISO).timestamp())


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout.strip()


def proveniencia():
    """Blob e commit do protocolo e do scorer. Aborta se o protocolo nao estiver commitado."""
    repo = PROTO.parent.parent
    rel = PROTO.relative_to(repo)
    sujo = git(repo, "status", "--short", "--", str(rel))
    if sujo:
        print(f"ABORTADO: {rel} tem alteracao nao commitada:\n  {sujo}")
        print("  O pre-registro so vale se o texto que governa a corrida estiver commitado.")
        sys.exit(1)
    blob_commitado = git(repo, "rev-parse", f"HEAD:{rel}")
    blob_disco = git(repo, "hash-object", str(PROTO))
    if not blob_commitado or blob_commitado != blob_disco:
        print(f"ABORTADO: blob do protocolo divergente.\n"
              f"  commitado={blob_commitado or '(ausente)'}\n  em disco={blob_disco}")
        sys.exit(1)
    log = git(repo, "log", "-1", "--format=%H %ci", "--", str(rel)).split(maxsplit=1)
    sc_rel = SCORER.relative_to(repo)
    sc_log = git(repo, "log", "-1", "--format=%H %ci", "--", str(sc_rel)).split(maxsplit=1)
    p = {
        "protocolo": str(rel),
        "protocolo_blob": blob_commitado,
        "protocolo_commit": log[0] if log else None,
        "protocolo_commit_data": log[1] if len(log) > 1 else None,
        "scorer": str(sc_rel),
        "scorer_blob": git(repo, "rev-parse", f"HEAD:{sc_rel}") or None,
        "scorer_commit": sc_log[0] if sc_log else None,
        "scorer_commit_data": sc_log[1] if len(sc_log) > 1 else None,
        "corte_iso": CORTE_ISO,
        "corte_ts": CORTE_TS,
        "executado_em": datetime.now(timezone.utc).isoformat(),
    }
    print(f"protocolo  blob {p['protocolo_blob'][:12]}  commit {(p['protocolo_commit'] or '')[:12]}"
          f"  de {p['protocolo_commit_data']}")
    print(f"scorer     blob {(p['scorer_blob'] or '')[:12]}  commit {(p['scorer_commit'] or '')[:12]}"
          f"  de {p['scorer_commit_data']}")
    print(f"corte      {CORTE_ISO}  ts={CORTE_TS}")
    if p["protocolo_commit_data"] and p["protocolo_commit_data"] > p["executado_em"]:
        print("  ATENCAO: o commit do protocolo e posterior a esta execucao.")
    return p


def identidade(a):
    """Identidade de uma trade action, para deduplicar a sobreposicao de paginas."""
    for k in ("id", "tid", "txHash", "tx_hash"):
        if a.get(k):
            return ("id", a[k])
    return ("tupla", a.get("account"), a.get("t"), a.get("market"),
            a.get("dir"), a.get("usd_notional"))


def cmd_pool(args):
    prov = proveniencia()
    since = CORTE_TS - JANELA_DIAS * 86400
    print(f"\njanela do pool: {datetime.fromtimestamp(since, timezone.utc).isoformat()}"
          f" -> {CORTE_ISO}  ({JANELA_DIAS}d)")
    print("este script nao calcula PnL em ponto nenhum, por desenho\n")

    vistos, por_conta = set(), defaultdict(int)
    cursor, paginas, brutos, dups = since, 0, 0, 0
    t0 = time.time()
    while cursor < CORTE_TS:
        try:
            lote = fetch_trade_actions(since_ts=cursor, until_ts=CORTE_TS, limit=200)
        except Exception as e:
            print(f"  erro na pagina {paginas}: {e}")
            print("  ABORTADO: um pool parcial nao e o pool declarado.")
            sys.exit(1)
        if not lote:
            break
        brutos += len(lote)
        for a in lote:
            ident = identidade(a)
            if ident in vistos:
                dups += 1
                continue
            vistos.add(ident)
            conta = a.get("account")
            if conta:
                por_conta[conta] += 1
        ultimo = max(x["t"] for x in lote)
        cursor = cursor + 1 if ultimo == cursor else ultimo
        paginas += 1
        if paginas % 20 == 0:
            print(f"  pagina {paginas}: {len(vistos)} acoes unicas, {dups} repetidas, "
                  f"{len(por_conta)} contas, cursor={cursor}, {time.time()-t0:.0f}s")

    print(f"\n{paginas} paginas, {brutos} acoes lidas, {dups} repetidas descartadas, "
          f"{len(vistos)} unicas, {len(por_conta)} contas distintas")

    pool = []
    for conta, n in por_conta.items():
        if n < MIN_ACOES_POOL:
            continue
        try:
            pool.append((to_checksum_address(conta), n))
        except Exception:
            continue
    pool.sort(key=lambda kv: kv[0])          # ordem por ENDERECO, nunca por desempenho
    print(f"pool com >= {MIN_ACOES_POOL} acoes antes do corte: {len(pool)} contas")

    Path("wallets_v3_pool.txt").write_text("\n".join(a for a, _ in pool) + "\n")
    Path("discover_v3_pool_meta.json").write_text(json.dumps({
        "proveniencia": prov, "janela_inicio_ts": since, "janela_fim_ts": CORTE_TS,
        "paginas": paginas, "acoes_brutas": brutos, "acoes_repetidas": dups,
        "acoes_unicas": len(vistos), "contas_distintas": len(por_conta),
        "min_acoes": MIN_ACOES_POOL, "pool": len(pool),
        "acoes_por_conta": {a: n for a, n in pool},
    }, indent=2))
    print("escrito: wallets_v3_pool.txt, discover_v3_pool_meta.json")
    print("o pool NAO e o universo. O universo primario e o registry, inteiro.")
    return 0


def cmd_registry(args):
    prov = proveniencia()
    bruto = Path(args.inp).read_text()
    achados, ruins = [], 0
    for tok in bruto.replace(",", " ").split():
        tok = tok.strip().strip('"\'[]')
        if len(tok) == 42 and tok.startswith("0x"):
            try:
                achados.append(to_checksum_address(tok))
            except Exception:
                ruins += 1
    unicos = sorted(set(achados))
    print(f"\n{len(achados)} enderecos lidos, {ruins} invalidos, {len(unicos)} unicos")
    if len(achados) != len(unicos):
        print(f"  {len(achados)-len(unicos)} duplicados no arquivo de origem")
    Path("wallets_v3_registry.txt").write_text("\n".join(unicos) + "\n")
    Path("discover_v3_registry_meta.json").write_text(json.dumps({
        "proveniencia": prov, "origem": args.inp, "lidos": len(achados),
        "invalidos": ruins, "unicos": len(unicos),
    }, indent=2))
    print("escrito: wallets_v3_registry.txt (universo primario, inteiro, sem filtro)")
    return 0


def cmd_draw(args):
    prov = proveniencia()
    n = args.passaram
    print(f"\nagentes do registry que passaram o piso de T1 (>=30 trades fechados): {n}")
    if n >= GATILHO_REGISTRY:
        print(f"gatilho declarado: suplemento so se n < {GATILHO_REGISTRY}. "
              f"Nao disparou. Nenhum sorteio.")
        return 0
    pool = [l.strip() for l in Path("wallets_v3_pool.txt").read_text().split() if l.strip()]
    reg = set(l.strip() for l in Path("wallets_v3_registry.txt").read_text().split() if l.strip())
    cands = sorted(set(pool) - reg)
    faltam = TOTAL_ALVO - n
    print(f"gatilho DISPAROU. alvo total {TOTAL_ALVO}, faltam {faltam}.")
    print(f"pool {len(pool)}, menos {len(pool)-len(cands)} que ja estao no registry "
          f"-> {len(cands)} candidatos")
    if faltam > len(cands):
        print(f"  pool insuficiente: {len(cands)} candidatos para {faltam} vagas. "
              f"Sorteando todos; o deficit entra no calculo de poder.")
        faltam = len(cands)
    rng = random.Random(SEED)
    sorteados = sorted(rng.sample(cands, faltam))
    Path("wallets_v3_suplemento.txt").write_text("\n".join(sorteados) + "\n")
    Path("discover_v3_draw_meta.json").write_text(json.dumps({
        "proveniencia": prov, "seed": SEED, "gatilho": GATILHO_REGISTRY,
        "passaram_registry": n, "total_alvo": TOTAL_ALVO,
        "candidatos": len(cands), "sorteados": len(sorteados),
    }, indent=2))
    print(f"escrito: wallets_v3_suplemento.txt, {len(sorteados)} enderecos, seed {SEED}")
    print("o sorteio e deterministico: a mesma seed e o mesmo pool reproduzem a lista.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pool")
    r = sub.add_parser("registry"); r.add_argument("--in", dest="inp", required=True)
    d = sub.add_parser("draw"); d.add_argument("--passaram", type=int, required=True)
    a = ap.parse_args()
    sys.exit({"pool": cmd_pool, "registry": cmd_registry, "draw": cmd_draw}[a.cmd](a))

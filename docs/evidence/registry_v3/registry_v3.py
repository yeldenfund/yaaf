#!/usr/bin/env python3
"""
registry_v3.py — enumera o AIAgentRegistry v2 e monta o universo primario do
IC_PROTOCOL_v3.md.

Nao usa web3. Chamadas eth_call cruas com seletores calculados a partir da fonte
do contrato, e decodificacao do struct Agent pelo layout exato de
contracts/AIAgentRegistry.sol.

Guard de reproducao: o script calcula (status == ACTIVE and score >= 500) a
partir do struct decodificado e compara com o isEligible do proprio contrato.
Se divergirem em qualquer agente, aborta — a divergencia significa que a
decodificacao esta errada, e um universo decodificado errado e pior que nenhum.

Uso:
  python3 registry_v3.py                 # enumera, decodifica, grava
  python3 registry_v3.py --logs          # tambem varre AgentRegistered/AgentSlashed
  python3 registry_v3.py --rpc <url>     # endpoint proprio (ou YAAF_RPC=...)
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run

from eth_utils import to_checksum_address

# Candidatos de RPC, em ordem. O primeiro que responder eth_blockNumber e usado.
# Override: variavel de ambiente YAAF_RPC, ou --rpc.
RPC_CANDIDATOS = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon-rpc.com",
    "https://1rpc.io/matic",
]
RPC = None          # resolvido em escolher_rpc()

# O publicnode responde 403 ao User-Agent do urllib e 200 ao do curl.
# curl funcionou neste mesmo endpoint, entao o UA imita curl de proposito.
HDRS = {"content-type": "application/json", "user-agent": "curl/8.5.0"}

REG = "0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E"
REG_V1 = "0xbC102cDec0DD007E7739ac213b62d5B031B22aF1"

CORTE_ISO = "2026-08-20T00:00:00+00:00"
CORTE_TS = int(datetime.fromisoformat(CORTE_ISO).timestamp())
LIMIAR = 500                      # SCORE_THRESHOLD_ACTIVE
ACTIVE = 2                        # enum AgentStatus { NONE, PENDING, ACTIVE, BANNED }
STATUS = {0: "NONE", 1: "PENDING", 2: "ACTIVE", 3: "BANNED"}
PROTO = Path("/root/yaaf/docs/IC_PROTOCOL_v3.md")

SEL = {
    "totalAgents": "0xc5053712",
    "getAgentList": "0x52669b0b",
    "getAgent": None,             # calculado abaixo
    "isEligible": "0x66e305fd",
    "totalRegistered": "0x927416c0",
    "totalActive": "0x57759600",
    "minStake": "0x375b3c0a",
    "monthlyFee": "0x8cfd3e40",
}
TOPIC_REGISTERED = "0xe09ab36be036eaee66b15d687e055aa6801e0a71143297e821dad0794940e647"
TOPIC_SLASHED = "0xf5e8eca84f7aab4f797fe2cf47918bae8ab442cfdaa90f359968f75929530f2d"


def keccak_sel(sig):
    from eth_utils import keccak
    return "0x" + keccak(text=sig).hex()[:8]


SEL["getAgent"] = keccak_sel("getAgent(address)")


def rpc(method, params, tentativas=3, url=None):
    corpo = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    ult = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url or RPC, data=corpo, headers=HDRS)
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read())
            if "error" in d:
                return None, d["error"].get("message", str(d["error"]))
            return d.get("result"), None
        except Exception as e:
            ult = str(e)
            time.sleep(1.5 * (i + 1))
    return None, ult


def escolher_rpc(preferido=None):
    """Primeiro candidato que responda eth_blockNumber. Aborta se nenhum responder."""
    global RPC
    cands = ([preferido] if preferido else []) + \
            ([os.environ["YAAF_RPC"]] if os.environ.get("YAAF_RPC") else []) + RPC_CANDIDATOS
    for u_ in cands:
        bloco, err = rpc("eth_blockNumber", [], tentativas=1, url=u_)
        if bloco:
            RPC = u_
            print(f"rpc        {u_}  bloco {int(bloco, 16)}")
            return
        print(f"  rpc indisponivel: {u_}  ({err})")
    print("ABORTADO: nenhum RPC respondeu. Isto e falha de acesso, nao afirmacao sobre o contrato.")
    print("  Passe um endpoint com --rpc ou YAAF_RPC= (ha chaves Alchemy em "
          "/root/yaaf/hardhat.config.js).")
    sys.exit(1)


def call(data):
    r, err = rpc("eth_call", [{"to": REG, "data": data}, "latest"])
    if err:
        print(f"ABORTADO: eth_call falhou: {err}")
        sys.exit(1)
    return r


def w(b, i):
    return b[i * 32:(i + 1) * 32]


def u(b):
    return int.from_bytes(b, "big")


def arg_addr(a):
    return a.lower().replace("0x", "").rjust(64, "0")


def arg_uint(n):
    return f"{n:064x}"


def dec_lista(hexdata):
    b = bytes.fromhex(hexdata[2:])
    off = u(w(b, 0))
    n = u(b[off:off + 32])
    return ["0x" + b[off + 32 + i * 32 + 12: off + 32 + (i + 1) * 32].hex() for i in range(n)]


def dec_agent(hexdata):
    """struct Agent, layout exato da fonte. Tupla dinamica: 1a palavra e o offset."""
    b = bytes.fromhex(hexdata[2:])
    t = b[u(w(b, 0)):]
    def texto(o):
        n = u(t[o:o + 32])
        return t[o + 32:o + 32 + n].decode("utf-8", "replace")
    return {
        "addr": "0x" + w(t, 0)[12:].hex(),
        "name": texto(u(w(t, 1))),
        "agent_type": texto(u(w(t, 2))),
        "stake": u(w(t, 3)),
        "score": u(w(t, 4)),
        "status": u(w(t, 5)),
        "registered_at": u(w(t, 6)),
        "approved_at": u(w(t, 7)),
        "last_score_update": u(w(t, 8)),
        "last_fee_collection": u(w(t, 9)),
        "warning_count": u(w(t, 10)),
        "slash_pending": bool(u(w(t, 11))),
    }


def git(*a):
    return run(["git", "-C", str(PROTO.parent.parent), *a],
               capture_output=True, text=True).stdout.strip()


def proveniencia():
    rel = PROTO.relative_to(PROTO.parent.parent)
    if git("status", "--short", "--", str(rel)):
        print(f"ABORTADO: {rel} tem alteracao nao commitada. Pre-registro exige commit.")
        sys.exit(1)
    log = git("log", "-1", "--format=%H %ci", "--", str(rel)).split(maxsplit=1)
    p = {"protocolo_blob": git("rev-parse", f"HEAD:{rel}"),
         "protocolo_commit": log[0] if log else None,
         "protocolo_commit_data": log[1] if len(log) > 1 else None,
         "corte_iso": CORTE_ISO, "corte_ts": CORTE_TS, "registry": REG,
         "executado_em": datetime.now(timezone.utc).isoformat()}
    print(f"protocolo  blob {p['protocolo_blob'][:12]}  commit {(p['protocolo_commit'] or '')[:12]}"
          f"  de {p['protocolo_commit_data']}")
    return p


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def varrer_logs(topic, rotulo):
    r, err = rpc("eth_getLogs", [{"address": REG, "fromBlock": "0x0",
                                  "toBlock": "latest", "topics": [topic]}])
    if r is not None:
        print(f"  {rotulo}: {len(r)} eventos (faixa completa aceita)")
        return r
    print(f"  {rotulo}: faixa completa recusada ({err}); fatiando")
    ultimo, e2 = rpc("eth_blockNumber", [])
    if ultimo is None:
        print(f"  {rotulo}: nao foi possivel obter o bloco atual: {e2}")
        return None
    fim, passo, achados = int(ultimo, 16), 500_000, []
    while fim > 0:
        ini = max(0, fim - passo)
        r, err = rpc("eth_getLogs", [{"address": REG, "fromBlock": hex(ini),
                                      "toBlock": hex(fim), "topics": [topic]}])
        if err:
            print(f"    {hex(ini)}-{hex(fim)}: {err}")
            return achados or None
        achados.extend(r)
        fim = ini - 1
        if ini == 0:
            break
    print(f"  {rotulo}: {len(achados)} eventos (fatiado)")
    return achados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", action="store_true")
    ap.add_argument("--rpc")
    args = ap.parse_args()

    prov = proveniencia()
    escolher_rpc(args.rpc)
    prov["rpc"] = RPC
    cod, err = rpc("eth_getCode", [REG, "latest"])
    if err:
        print(f"ABORTADO: nao foi possivel consultar o endereco: {err}")
        print("  Isto e falha de RPC. NAO significa que o contrato nao existe.")
        return 1
    if not cod or cod == "0x":
        print(f"ABORTADO: o RPC respondeu e nao ha bytecode em {REG}.")
        print("  Agora sim: endereco errado, ou contrato nao implantado nesta rede.")
        return 1
    print(f"contrato   {len(cod)//2 - 1} bytes em {REG}")

    for k in ("totalAgents", "totalRegistered", "totalActive", "minStake", "monthlyFee"):
        v = u(bytes.fromhex(call(SEL[k])[2:]))
        extra = f"  ({v/10**18:g} YLD)" if k in ("minStake", "monthlyFee") else ""
        print(f"  {k:<16} {v}{extra}")
    n = u(bytes.fromhex(call(SEL["totalAgents"])[2:]))
    if n == 0:
        print("\ntotalAgents = 0. O registry nao tem agentes. "
              "O universo primario esta vazio e o gatilho do suplemento dispara.")
        Path("registry_v3_agents.json").write_text(json.dumps(
            {"proveniencia": prov, "total_agents": 0, "agentes": []}, indent=2))
        return 0

    enderecos = []
    passo = 200
    for off in range(0, n, passo):
        enderecos.extend(dec_lista(call(SEL["getAgentList"] + arg_uint(off) + arg_uint(passo))))
    print(f"\nenumerados {len(enderecos)} enderecos de {n} declarados")
    if len(enderecos) != n:
        print("  ABORTADO: a lista nao bate com totalAgents.")
        return 1

    ags, divergencias = [], 0
    for i, a in enumerate(enderecos, 1):
        d = dec_agent(call(SEL["getAgent"] + arg_addr(a)))
        eleg_contrato = u(bytes.fromhex(call(SEL["isEligible"] + arg_addr(a))[2:])) == 1
        eleg_calc = d["status"] == ACTIVE and d["score"] >= LIMIAR
        if eleg_contrato != eleg_calc:
            divergencias += 1
            print(f"  DIVERGENCIA em {a}: contrato={eleg_contrato} calculado={eleg_calc} "
                  f"(status={d['status']} score={d['score']})")
        try:
            d["addr"] = to_checksum_address(d["addr"])
        except Exception:
            pass
        d["status_nome"] = STATUS.get(d["status"], str(d["status"]))
        d["registered_at_iso"] = iso(d["registered_at"])
        d["pre_corte"] = bool(d["registered_at"] and d["registered_at"] < CORTE_TS)
        d["is_eligible_agora"] = eleg_contrato
        ags.append(d)
        if i % 25 == 0:
            print(f"  {i}/{n} lidos")

    if divergencias:
        print(f"\nABORTADO: {divergencias} divergencias entre o isEligible do contrato e o "
              f"calculado do struct. A decodificacao esta errada; nada foi gravado.")
        return 1
    print(f"\nguard de decodificacao: {len(ags)} agentes, 0 divergencias contra isEligible")

    por_status = {}
    for d in ags:
        por_status[d["status_nome"]] = por_status.get(d["status_nome"], 0) + 1
    pre = [d for d in ags if d["pre_corte"]]
    eleg = [d for d in ags if d["is_eligible_agora"]]
    acima = [d for d in ags if d["score"] >= LIMIAR]
    atualizados = [d for d in ags if d["last_score_update"]]

    print(f"\nstatus: {por_status}")
    print(f"registrados antes do corte ({CORTE_ISO}): {len(pre)} de {len(ags)}")
    print(f"score on-chain >= {LIMIAR}: {len(acima)}   isEligible agora: {len(eleg)}")
    print(f"com last_score_update != 0: {len(atualizados)}")
    if atualizados:
        us = sorted(d["last_score_update"] for d in atualizados)
        print(f"  ultima atualizacao de score: {iso(us[-1])}  (mais antiga {iso(us[0])})")
    if pre:
        rs = sorted(d["registered_at"] for d in pre)
        print(f"  registro mais antigo {iso(rs[0])}, mais recente antes do corte {iso(rs[-1])}")

    logs = {}
    if args.logs:
        print("\nlogs:")
        for t, rot in ((TOPIC_REGISTERED, "AgentRegistered"), (TOPIC_SLASHED, "AgentSlashed")):
            r = varrer_logs(t, rot)
            logs[rot] = None if r is None else len(r)
            if rot == "AgentSlashed" and r:
                print(f"    O SLASH DISPAROU {len(r)} vez(es). Ha dado de desfecho; "
                      f"a afirmacao de que e inmensuravel cai.")

    Path("registry_v3_agents.json").write_text(json.dumps(
        {"proveniencia": prov, "total_agents": n, "limiar": LIMIAR,
         "por_status": por_status, "pre_corte": len(pre),
         "score_acima_do_limiar": len(acima), "is_eligible": len(eleg),
         "logs": logs, "agentes": ags}, indent=2))
    Path("wallets_v3_registry.txt").write_text(
        "\n".join(sorted(d["addr"] for d in pre)) + ("\n" if pre else ""))
    print(f"\nescrito: registry_v3_agents.json, wallets_v3_registry.txt ({len(pre)} enderecos)")
    print("o universo primario e o registry inteiro com registered_at < corte, sem filtro de desempenho.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

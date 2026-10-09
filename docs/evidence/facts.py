#!/usr/bin/env python3
"""
facts.py — gera o facts.json: um artefato canonico com todo numero que aparece em
superficie publica, cada um carregando o seu referente.

Regra unica deste script: NAO REDIGITA NUMERO NENHUM.

  * os pesos, o W_SUM, os caps e os parametros de EMA/CF/SF vem de
    `import yaaf_score_v5_formal` — producao;
  * a tabela de bandas e DERIVADA sondando a funcao stage(), nao copiada;
  * o teto algebrico e CALCULADO de W, nao afirmado;
  * o limiar do portao e lido do fonte do contrato, e o do scorer e lido do
    proprio arquivo — os dois ficam no JSON lado a lado, para que a divergencia
    seja um campo e nao uma coisa que alguem precise notar;
  * as listas de perfil vem do scores_api.py por AST, sem importar nem executar;
  * a populacao vem de SQL agrupado por (profile, score_version), porque contagem
    sem referente foi a causa de metade dos erros publicados;
  * as figuras da medicao vem do agregado commitado, embutido verbatim com o seu
    hash — nada de reescrever rho a mao.

Quando uma fonte nao pode ser lida, o campo sai `null` e o motivo entra em
`notes`. Nunca sai um valor inventado.

Uso:
  cd /root/yaaf/scorer && python3 facts.py              # offline, deterministico
  cd /root/yaaf/scorer && python3 facts.py --chain      # confirma na cadeia
  cd /root/yaaf/scorer && python3 facts.py --out /tmp/facts.json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run

REPO = Path("/root/yaaf")
OBS = Path("/root/aiagentregistry-observatory")
SCORER_PY = REPO / "scorer" / "yaaf_score_v5_formal.py"
CONTRACT_SOL = REPO / "contracts" / "AIAgentRegistry.sol"
API_PY = OBS / "scores_api.py"
EVID = REPO / "docs" / "evidence" / "gmx_v2"
REG_JSON = REPO / "docs" / "evidence" / "registry_v3" / "registry_v3_agents.json"
DB = OBS / "observatory.db"
FULL_RESULT = OBS / "docs" / "evidence" / "ic_test_gmx_v2_result.json"
PROTOCOLS = ["IC_PROTOCOL.md", "IC_PROTOCOL_v2.md", "IC_PROTOCOL_v3.md",
             "AMENDMENT_v5.0.2.md", "PLAN.md", "STATE.md"]

REG_ADDR = "0xC6Aef54A0ea6AbFcC9fe61154b9b357E0DDF113E"
RPCS = ["https://polygon-bor-rpc.publicnode.com", "https://polygon-rpc.com"]
HDRS = {"content-type": "application/json", "user-agent": "curl/8.5.0"}
SEL = {"totalAgents": "0xc5053712", "totalActive": "0x57759600",
       "totalRegistered": "0x927416c0", "totalSlashed": "0xa201bbdd",
       "totalBurned": "0xd89135cd", "minStake": "0x375b3c0a",
       "monthlyFee": "0x8cfd3e40"}

notes: list[str] = []
W_LOCAL: dict = {}        # preenchido em main() a partir do scorer importado


def nota(msg):
    notes.append(msg)
    print(f"  nota: {msg}", file=sys.stderr)


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def git(*a, repo=REPO):
    return run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout.strip()


def proveniencia(p: Path):
    """blob em HEAD e commit que introduziu o arquivo. None se nao rastreado."""
    try:
        rel = p.relative_to(REPO)
    except ValueError:
        return {"path": str(p), "tracked": False, "sha256": sha(p)}
    blob = git("rev-parse", f"HEAD:{rel}")
    log = git("log", "-1", "--format=%H %ci", "--", str(rel)).split(maxsplit=1)
    sujo = bool(git("status", "--short", "--", str(rel)))
    return {
        "path": str(rel), "tracked": bool(blob), "blob": blob or None,
        "commit": log[0] if log else None,
        "commit_date": log[1] if len(log) > 1 else None,
        "uncommitted_changes": sujo, "sha256": sha(p),
    }


def copias_do_scorer():
    """Toda copia do scorer no disco, com hash, e quem a importa pelo nome.

    Duas copias identicas hoje nao garantem duas copias identicas amanha: nada
    liga uma a outra. Os scripts que fazem sys.path.insert(0, __file__.parent)
    e importam yaaf_score_v5_formal resolvem para a copia irma, nao para a
    canonica. Este bloco existe para que a divergencia apareca como fato no
    instante em que surgir, em vez de ser descoberta por um numero errado ja
    servido pela API.
    """
    nome = SCORER_PY.name
    canonico = sha(SCORER_PY)
    # A deduplicacao e por caminho, NAO por destino resolvido. Deduplicar por
    # resolve() faria um symlink colapsar no alvo e desaparecer do relatorio,
    # escondendo justamente a distincao que este bloco existe para mostrar:
    # um link nao pode divergir do alvo, um arquivo copiado pode.
    vistos, copias = set(), []
    for raiz in (REPO, OBS):
        if not raiz.is_dir():
            continue
        for p in sorted(raiz.glob(nome)) + sorted(raiz.glob("*/" + nome)):
            ap = Path(os.path.abspath(str(p)))   # sem resolver o link
            if ap in vistos:
                continue
            vistos.add(ap)
            link = p.is_symlink()
            h = sha(p)                           # le o conteudo, seguindo o link
            copias.append({
                "path": str(ap),
                "sha256": h,
                "canonical": ap == Path(os.path.abspath(str(SCORER_PY))),
                "matches_canonical": (h == canonico) if (h and canonico) else None,
                "is_symlink": link,
                "resolves_to": str(p.resolve()) if link else None,
                "dangling": (link and not p.exists()),
            })

    pad = re.compile(r"^\s*(?:from\s+yaaf_score_v5_formal\s+import"
                     r"|import\s+yaaf_score_v5_formal)", re.M)
    importadores = []
    for raiz in (REPO, OBS):
        if not raiz.is_dir():
            continue
        for p in sorted(raiz.glob("*.py")) + sorted(raiz.glob("*/*.py")):
            if p.name == nome:
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not pad.search(txt):
                continue
            irmao = p.parent / nome
            importadores.append({
                "path": str(p),
                "sibling_copy": str(irmao) if irmao.is_file() else None,
                "inserts_own_dir_on_path": "Path(__file__).parent" in txt,
            })

    hashes = {c["sha256"] for c in copias if c["sha256"]}
    reais = [c for c in copias if not c["is_symlink"]]
    return {
        "canonical": str(SCORER_PY),
        "copies": copias,
        "copy_count": len(copias),
        "real_file_count": len(reais),
        "agree": len(hashes) <= 1,
        "note": ("A symlink cannot drift from its target, so copies that are links "
                 "are not a version hazard: real_file_count is the number that can. "
                 "real_file_count > 1 means two independent files, nothing enforcing "
                 "their equality, and a patch applied to the canonical one alone "
                 "leaves every importer whose own directory holds a sibling file on "
                 "the old version, silently. agree=false means the scores being "
                 "served and the scorer being declared are not the same code. A "
                 "dangling link, or a link to an absolute path outside the "
                 "repository, breaks on any clone of it."),
        "importers": importadores,
        "importer_count": len(importadores),
    }


def consts_por_ast(p: Path, nomes):
    """Le constantes de um .py sem importar nem executar."""
    out = {}
    if not p.is_file():
        nota(f"{p} ausente; constantes {sorted(nomes)} nao lidas")
        return out
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception as e:
        nota(f"{p} nao parseou: {e}")
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in nomes:
                    try:
                        out[t.id] = ast.literal_eval(node.value)
                    except Exception:
                        nota(f"{t.id} em {p.name} nao e literal; ignorado")
    for n in nomes - set(out):
        nota(f"{n} nao encontrado em {p.name}")
    return out


def bandas_sondadas(stage_fn):
    """Deriva a tabela de bandas chamando stage(), em vez de copia-la."""
    limites, atual, inicio = [], stage_fn(0), 0
    for v in range(1, 1001):
        nome = stage_fn(v)
        if nome != atual:
            limites.append({"stage": atual, "from": inicio, "to": v - 1})
            atual, inicio = nome, v
    limites.append({"stage": atual, "from": inicio, "to": 1000})
    return limites


def rpc(method, params, url):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers=HDRS)
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    if "error" in d:
        raise RuntimeError(d["error"].get("message", str(d["error"])))
    return d.get("result")


def cadeia():
    for u in RPCS:
        try:
            rpc("eth_blockNumber", [], u)
        except Exception as e:
            nota(f"rpc indisponivel {u}: {e}")
            continue
        out = {"rpc": u, "address": REG_ADDR, "read_at": agora()}
        for k, s in SEL.items():
            try:
                out[k] = int(rpc("eth_call", [{"to": REG_ADDR, "data": s}, "latest"], u), 16)
            except Exception as e:
                out[k] = None
                nota(f"eth_call {k} falhou: {e}")
        return out
    nota("nenhum RPC respondeu; secao on-chain ausente")
    return None


def agora():
    return datetime.now(timezone.utc).isoformat()


def populacao(con):
    """Contagens com referente. Sem referente, contagem publicada mente."""
    q = """
    SELECT profile,
           COALESCE(json_extract(payload,'$.score_version'),'(no version)') AS v,
           COUNT(*) AS rows_n, COUNT(DISTINCT address) AS addrs,
           ROUND(MIN(s_raw),4) AS min_s_raw, ROUND(MAX(s_raw),4) AS max_s_raw,
           MAX(ts) AS latest_ts
    FROM yaaf_scores GROUP BY profile, v ORDER BY rows_n DESC
    """
    por = [dict(zip([c[0] for c in con.execute(q).description], r))
           for r in con.execute(q).fetchall()]
    total_rows = con.execute("SELECT COUNT(*) FROM yaaf_scores").fetchone()[0]
    total_addr = con.execute("SELECT COUNT(DISTINCT address) FROM yaaf_scores").fetchone()[0]
    return {
        "source": "observatory.db / yaaf_scores",
        "rows_total": total_rows,
        "addresses_total": total_addr,
        "by_profile_and_scorer_version": por,
        "caveat": ("profile classifies the agent, score_version identifies the engine "
                   "that produced the row; they are not the same axis and rows exist "
                   "where they disagree."),
    }


def ultimo_por_endereco(con, yaaf_profiles, mm_profiles):
    q = """
    SELECT address, stage, profile,
           COALESCE(json_extract(payload,'$.score_version'),'(no version)') v
    FROM (SELECT address, stage, profile, payload,
                 ROW_NUMBER() OVER (PARTITION BY address ORDER BY ts DESC, id DESC) rn
          FROM yaaf_scores) WHERE rn = 1
    """
    por_engine = {}
    for addr, st, prof, v in con.execute(q).fetchall():
        if prof in (yaaf_profiles or ()):
            eng = "YAAF"
        elif prof in (mm_profiles or ()):
            eng = "MM"
        else:
            eng = "unclassified_profile"
        d = por_engine.setdefault(eng, {"addresses": 0, "by_stage": {},
                                        "by_scorer_version": {}})
        d["addresses"] += 1
        d["by_stage"][st or "(null)"] = d["by_stage"].get(st or "(null)", 0) + 1
        d["by_scorer_version"][v] = d["by_scorer_version"].get(v, 0) + 1
    return {
        "rule": "ROW_NUMBER() PARTITION BY address ORDER BY ts DESC, id DESC",
        "engine_inferred_from": "profile, via the lists read from scores_api.py",
        "by_engine": por_engine,
        "caveat": ("an address scored by both engines yields whichever row is newest; "
                   "engine here is inferred from profile, not from score_version."),
    }


def dispersao_dos_componentes(con, yaaf_profiles):
    """Para cada componente, min/max/distintos na populacao servida.

    Um componente com max == min e INERTE: carrega peso e nao ordena ninguem.
    Foi exatamente isso que ficou meses em pe com Smoothness^2 e Mc, e a unica
    razao de ter sido descoberto e que alguem foi olhar. Aqui passa a ser campo.
    """
    perfis = tuple(yaaf_profiles or ())
    if not perfis:
        nota("listas de perfil nao lidas; dispersao de componentes nao calculada")
        return None
    ph = ",".join("?" * len(perfis))
    q = f"""
    SELECT payload FROM (
      SELECT payload, ROW_NUMBER() OVER (PARTITION BY address ORDER BY ts DESC, id DESC) rn
      FROM yaaf_scores WHERE profile IN ({ph})
    ) WHERE rn = 1
    """
    vals = {}
    n = 0
    for (raw,) in con.execute(q, perfis).fetchall():
        try:
            d = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        n += 1
        for k, v in d.items():
            if (k.startswith("s_") or k in ("cvar_pen", "dd_penalty", "cf", "sf")) \
                    and isinstance(v, (int, float)):
                vals.setdefault(k, []).append(float(v))
    if not n:
        nota("nenhum payload YAAF legivel; dispersao de componentes vazia")
        return None
    out = {}
    for k, xs in sorted(vals.items()):
        lo, hi = min(xs), max(xs)
        out[k] = {"n": len(xs), "min": round(lo, 6), "max": round(hi, 6),
                  "distinct": len(set(round(x, 9) for x in xs)),
                  "inert": hi - lo < 1e-9}
    inertes = [k for k, v in out.items() if v["inert"]]
    return {
        "scored_addresses_examined": n,
        "profiles": list(perfis),
        "components": out,
        "inert_components": inertes,
        "inert_weight": round(sum(W_LOCAL.get(k[2:], 0.0) for k in inertes), 6),
        "note": ("inert means max == min across the served population: the component "
                 "carries weight and ranks nobody. Weight is matched by stripping the "
                 "s_ prefix, so components whose weight key differs are reported with "
                 "weight 0 and should be read from scorer.components."),
    }


def cobertura_da_medicao(con):
    """Quantos dos agentes medidos a API de fato serve. Só contagens, sem endereco."""
    if not FULL_RESULT.is_file():
        nota(f"{FULL_RESULT} ausente; cobertura medido-vs-servido nao calculada")
        return None
    try:
        obs = json.loads(FULL_RESULT.read_text(encoding="utf-8"))["observacoes"]
    except Exception as e:
        nota(f"resultado completo ilegivel: {e}")
        return None
    medidos = {str(o["agent"]).lower() for o in obs}
    db_perfis = {}
    for a, p in con.execute("SELECT DISTINCT lower(address), profile FROM yaaf_scores"):
        db_perfis.setdefault(a, set()).add(p)
    dentro = medidos & set(db_perfis)
    from collections import Counter
    return {
        "measured_by_canonical_run": len(medidos),
        "present_in_served_db": len(dentro),
        "absent_from_served_db": len(medidos - set(db_perfis)),
        "profiles_of_those_present": dict(Counter(p for a in dentro for p in db_perfis[a])),
        "why_this_matters": ("the published correlation describes the measured "
                             "population; the API serves the present one. The two "
                             "are not the same set and both are public."),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", action="store_true", help="confirma os valores na cadeia")
    ap.add_argument("--out", default=str(EVID.parent / "facts.json"))
    args = ap.parse_args()

    sys.path.insert(0, str(SCORER_PY.parent))
    try:
        import yaaf_score_v5_formal as sc
    except Exception as e:
        print(f"ABORTADO: nao consegui importar o scorer: {e}")
        return 1

    # --- scorer: tudo importado, nada redigitado ---
    global W_LOCAL
    W_LOCAL = dict(sc.W)
    teto_algebrico = sum(100.0 * w for w in sc.W.values()) / sc.W_SUM
    src = SCORER_PY.read_text(encoding="utf-8")
    m = re.search(r"is_eligible\s*=\s*sistema\s*>=\s*([\d.]+)", src)
    limiar_scorer = float(m.group(1)) if m else None
    if m is None:
        nota("o literal de is_eligible nao casou o padrao no scorer; campo nulo")

    scorer = {
        "version": sc.VERSION_SCORE,
        "components": dict(sc.W),
        "component_count": len(sc.W),
        "w_sum": sc.W_SUM,
        "algebraic_s_raw_ceiling": round(teto_algebrico, 6),
        "ceiling_note": ("computed as sum(100*w)/W_SUM: every component is scaled to "
                         "[0,100], so this is 100 whenever no component is inert. The "
                         "attainable ceiling is an empirical question: see "
                         "component_dispersion.inert_components and .inert_weight, "
                         "and population...max_s_raw. This field alone does NOT tell "
                         "you whether the amendment was applied — component_count and "
                         "w_sum do."),
        "caps": {k: getattr(sc, k) for k in dir(sc) if k.startswith("CAP_")},
        "penalties": {"CVAR_PEN_SCALE": sc.CVAR_PEN_SCALE, "CVAR_CAP": sc.CVAR_CAP,
                      "DD_PEN_WEIGHT": sc.DD_PEN_WEIGHT},
        "gates": {"MIN_TRADES_SRAW": sc.MIN_TRADES_SRAW,
                  "VOLUME_FLOOR_FRAC": sc.VOLUME_FLOOR_FRAC},
        "sistema": {"EMA_ALPHA": sc.EMA_ALPHA, "EMA_INITIAL": sc.EMA_INITIAL,
                    "CF_N_STAR": sc.CF_N_STAR, "SF_WINDOW": sc.SF_WINDOW,
                    "SF_LEVEL_REF": sc.SF_LEVEL_REF, "SF_DISP_REF": sc.SF_DISP_REF},
        "bands": bandas_sondadas(sc.stage),
        "bands_note": "derived by probing stage() over 0..1000, not transcribed",
        "fee_model": {"FEE_BASE_RATE_USDC": sc.FEE_BASE_RATE_USDC,
                      "formula": "FEE_BASE_RATE_USDC * (1000 - sistema) / 1000"},
        "stake_floors_usdc": dict(sc.STAKE_FLOORS_USDC),
        "is_eligible_threshold_in_scorer": limiar_scorer,
        "provenance": proveniencia(SCORER_PY),
        "copies": copias_do_scorer(),
    }
    _cp = scorer["copies"]
    if not _cp["agree"]:
        nota("as copias do scorer DIVERGEM; veja scorer.copies — o que e servido "
             "nao e o que esta declarado")
    elif _cp["real_file_count"] > 1:
        nota(f"ha {_cp['real_file_count']} arquivos independentes do scorer, iguais "
             "hoje e sem nada que force a igualdade amanha; veja scorer.copies")
    if any(c["dangling"] for c in _cp["copies"]):
        nota("ha symlink do scorer apontando para lugar nenhum; veja scorer.copies")

    # --- contrato: do fonte commitado, e opcionalmente da cadeia ---
    limiar_contrato = None
    contrato = {"address": REG_ADDR, "source": proveniencia(CONTRACT_SOL)}
    if CONTRACT_SOL.is_file():
        sol = CONTRACT_SOL.read_text(encoding="utf-8")
        for nome in ("SCORE_THRESHOLD_ACTIVE", "MAX_SCORE", "INITIAL_SCORE",
                     "WARNING_SLASH_PCT", "SUSPENSION_SLASH_PCT"):
            mm = re.search(rf"constant\s+{nome}\s*=\s*(\d+)", sol)
            contrato[nome] = int(mm.group(1)) if mm else None
            if mm is None:
                nota(f"{nome} nao casou no fonte do contrato")
        limiar_contrato = contrato.get("SCORE_THRESHOLD_ACTIVE")
        me = re.search(r"return\s+a\.status\s*==\s*AgentStatus\.ACTIVE\s*&&\s*"
                       r"a\.score\s*>=\s*SCORE_THRESHOLD_ACTIVE", sol)
        contrato["isEligible_is_a_conjunction"] = bool(me)
    else:
        nota(f"{CONTRACT_SOL} ausente; constantes do contrato nao lidas")
    if args.chain:
        contrato["onchain"] = cadeia()

    portao = {
        "scorer_threshold": limiar_scorer,
        "contract_threshold": limiar_contrato,
        "agree": (limiar_scorer is not None and limiar_contrato is not None
                  and float(limiar_scorer) == float(limiar_contrato)),
        "authority": "the contract. isEligible(address) is what gates stake on-chain.",
        "note": ("the scorer duplicates a predicate the contract already decides; a "
                 "duplicated predicate drifts, and this field exists so the drift is "
                 "data rather than something a reader has to notice."),
    }

    # --- populacao ---
    api_consts = consts_por_ast(API_PY, {"YAAF_PROFILES", "MM_PROFILES"})
    pop, ultimo, cobertura, dispersao = None, None, None, None
    if DB.is_file():
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            pop = populacao(con)
            ultimo = ultimo_por_endereco(con, api_consts.get("YAAF_PROFILES"),
                                         api_consts.get("MM_PROFILES"))
            dispersao = dispersao_dos_componentes(con, api_consts.get("YAAF_PROFILES"))
            cobertura = cobertura_da_medicao(con)
        finally:
            con.close()
    else:
        nota(f"{DB} ausente; populacao nao lida")

    # --- medicao: agregado verbatim, nada reescrito ---
    medicao = {}
    agg = EVID / "ic_test_gmx_v2_result.aggregate.json"
    if agg.is_file():
        try:
            medicao["gmx_v2"] = {
                "aggregate_verbatim": json.loads(agg.read_text(encoding="utf-8")),
                "aggregate_sha256": sha(agg),
                "aggregate_provenance": proveniencia(agg),
                "inputs_manifest_sha256": sha(EVID / "payloads_manifest.sha256"),
                "served_coverage": cobertura,
                "read_before_use": ("IC_PROTOCOL_v2.md carries a dated addendum: the "
                                    "universe was selected on dollar PnL over a window "
                                    "inside the forward period. No figure from this run "
                                    "is a population estimate."),
            }
        except Exception as e:
            nota(f"agregado ilegivel: {e}")
    else:
        nota(f"{agg} ausente; secao de medicao vazia")

    # --- registry ---
    registry = None
    if REG_JSON.is_file():
        try:
            d = json.loads(REG_JSON.read_text(encoding="utf-8"))
            registry = {k: d.get(k) for k in ("total_agents", "limiar", "por_status",
                                              "pre_corte", "score_acima_do_limiar",
                                              "is_eligible", "logs")}
            registry["enumerated_at"] = (d.get("proveniencia") or {}).get("executado_em")
            registry["provenance"] = proveniencia(REG_JSON)
            registry["note"] = "per-agent records are in the committed file, not here"
        except Exception as e:
            nota(f"enumeracao do registry ilegivel: {e}")
    else:
        nota(f"{REG_JSON} ausente; secao de registry vazia")

    docs = {d: proveniencia(REPO / "docs" / d) for d in PROTOCOLS
            if (REPO / "docs" / d).is_file()}
    for d in PROTOCOLS:
        if not (REPO / "docs" / d).is_file():
            nota(f"docs/{d} ausente")

    gerador = proveniencia(Path(__file__).resolve())
    sujos = [x["path"] for x in [scorer["provenance"], gerador, *docs.values()]
             if isinstance(x, dict) and x.get("uncommitted_changes")]

    facts = {
        "schema": "yelden.facts/1",
        "generated_at": agora(),
        "generator": gerador,
        "provenance_clean": not sujos,
        "uncommitted": sujos,
        "scorer": scorer,
        "contract": contrato,
        "gate_threshold": portao,
        "registry": registry,
        "population": pop,
        "latest_per_address": ultimo,
        "component_dispersion": dispersao,
        "measurement": medicao,
        "documents": docs,
        "rules": [
            "Every number here is read or computed from a source, never transcribed.",
            "Every count carries the axis it was grouped by.",
            "A number without a source is absent, not estimated; see notes.",
            "Published surfaces should read this file instead of carrying literals.",
        ],
        "notes": notes,
    }

    out = Path(args.out)
    blob = json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    out.write_text(blob + "\n", encoding="utf-8")
    h = hashlib.sha256((blob + "\n").encode()).hexdigest()
    Path(str(out) + ".sha256").write_text(f"{h}  {out.name}\n", encoding="utf-8")

    print(f"\nescrito: {out}  ({len(blob)} bytes)")
    print(f"sha256:  {h}")
    print(f"scorer {scorer['version']}  {scorer['component_count']} componentes  "
          f"W_SUM {scorer['w_sum']:.4f}  teto {scorer['algebraic_s_raw_ceiling']:.4f}")
    print(f"portao: scorer {portao['scorer_threshold']}  contrato "
          f"{portao['contract_threshold']}  concordam: {portao['agree']}")
    if pop:
        print(f"populacao: {pop['addresses_total']} enderecos, "
              f"{pop['rows_total']} linhas, {len(pop['by_profile_and_scorer_version'])} "
              f"combinacoes de (profile, score_version)")
    if dispersao:
        print(f"componentes inertes: {dispersao['inert_components'] or 'nenhum'}  "
              f"(peso {dispersao['inert_weight']})")
    if cobertura:
        print(f"medicao: {cobertura['measured_by_canonical_run']} medidos, "
              f"{cobertura['present_in_served_db']} servidos, "
              f"{cobertura['absent_from_served_db']} ausentes")
    if sujos:
        print(f"ATENCAO: provenance_clean = false. Nao commitado: {sujos}")
    if notes:
        print(f"{len(notes)} nota(s) no campo notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

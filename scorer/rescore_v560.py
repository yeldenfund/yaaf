#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rescore_v560.py - o re-score deliberado, sob o scorer 5.6.0.

ISTO ESCREVE NO BANCO. Exige --confirm. Com --dry-run nao escreve nada, e e
assim que se descobre o terreno antes de mexer nele: o dry-run imprime o
esquema do yaaf_state, por que rota a coluna `payload` foi lida, e o retrato
do ANTES. Rode o dry-run primeiro, sempre.

O QUE FAZ, nesta ordem

  1. Recusa rodar se o scorer nao for 5.6.0-FORMAL. Re-pontuar sob o codigo
     errado significa re-pontuar duas vezes, e a segunda apaga a primeira.
  2. Le EMA_INITIAL do proprio scorer. Nao ha segunda constante aqui.
  3. Exige que os dois emits existam e aceitem --force. Um emit faltando nao
     e aviso: e metade da populacao re-pontuada e metade nao, que e exatamente
     o estado que este script existe para evitar.
  4. Backup consistente pela API de backup do sqlite3 (nao `cp`: com o banco
     vivo, uma copia byte a byte pode pegar pagina rasgada, e em WAL o `cp`
     do .db sozinho perde o -wal). Verifica integrity_check e as contagens das
     duas tabelas no backup. Imprime o sha256 das duas copias para o registro
     -- eles DIVERGEM por construcao, porque a API de backup reescreve as
     paginas; o que prova a copia e a verificacao logica, nao o hash.
  5. Retrato do ANTES, so agregados: bandas por motor, elegiveis pelo
     contrato, versoes presentes, e quantos payloads carregam is_eligible.
  6. Copia yaaf_state para yaaf_state_pre_<versao> DENTRO do banco. A EMA e a
     round_history de agora sao as entradas que produziram os scores
     publicados; zera-las sem guardar torna um SISTEMA publicado
     irreproduzivel a partir do seu estado.
  7. Zera yaaf_state: ema = EMA_INITIAL, round_history = '[]',
     total_trades = 0. Numa transacao. Declara quais colunas toca e quais
     deixa como estao.
  8. Roda os dois emits com --force. GMX primeiro, HL depois.
  9. Retrato do DEPOIS, a tabela antes/depois, e um veredito de cobertura:
     toda versao servida tem de ser 5.6.0-FORMAL e nenhum payload pode
     carregar is_eligible. Se nao for, o re-score nao cobriu a populacao e o
     script diz isso em voz alta em vez de declarar sucesso.
 10. Escreve RESCORE_<data>.md com tudo acima, para ser commitado.

POR QUE ZERAR

  A EMA: S_RAW de 5.0.0 tinha teto atingivel 88,0208 com 9 componentes e
  W_SUM 0,96; o de 5.6.0 tem teto 100 com 8 componentes e W_SUM 1,0. Nao sao
  a mesma grandeza. Suavizar atraves da fronteira calcula media de numeros
  incomensuraveis. E recalcular o historico sob 5.6.0 e impossivel: ha um
  snapshot de payloads, nao uma serie.

  round_history: pelo mesmo motivo, e porque 379 de 391 janelas estavam
  cheias de um unico valor repetido.

  total_trades: porque o valor armazenado esta errado -- 259 de 309
  enderecos tinham total_trades acima da propria contagem de fills, o que e
  impossivel sem acumulo (v5.2.0, D11).

SE ALGO FALHAR NO MEIO

  yaaf_scores e append-only e yaaf_state e upsert, entao uma execucao parcial
  deixa parte da populacao re-pontuada e parte nao. NAO basta rodar de novo:
  os ja feitos avancariam a EMA uma segunda vez. A recuperacao e restaurar o
  backup e repetir. O script imprime o comando exato, com os sidecars do WAL
  se o banco estiver em WAL.

CODIGOS DE SAIDA, porque eles dizem coisas diferentes

    0  terminou e a cobertura ficou completa
    1  ESCREVEU, e a cobertura ficou incompleta ou a execucao foi parcial --
       leia a mensagem, pode haver restauracao a fazer
    2  recusou antes de escrever: alguma pre-condicao nao bate. O banco esta
       como estava
    3  o banco estava travado por outro escritor. Nada foi escrito; espere e
       repita

Uso:
    python3 rescore_v560.py --dry-run      # so os retratos, nao escreve nada
    python3 rescore_v560.py --confirm
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys

OBS_PADRAO = "/root/aiagentregistry-observatory"
SCORER_PADRAO = "/root/yaaf/scorer/yaaf_score_v5_formal.py"
VERSAO_EXIGIDA = "5.6.0-FORMAL"
BANDAS = ["EXPERIMENTAL", "PROMISING", "VERIFIED", "ELITE", "LEGENDARY"]
ZERAR = ("ema", "round_history", "total_trades")

# scores_api fica vivo durante o re-score e mantem transacoes de leitura.
# Em rollback-journal um leitor bloqueia o escritor, e sem busy_timeout o
# sqlite devolve "database is locked" NA HORA, em vez de esperar -- o reset
# abortaria por um leitor que ia soltar o lock em milissegundos. 30 s.
# A variavel de ambiente existe para o teste poder exercitar o caminho do
# lock sem esperar meio minuto; em producao nao se mexe nela.
BUSY_MS = int(os.environ.get("YAAF_BUSY_MS", "30000"))

# Vira True no instante em que o primeiro COMMIT passa. O tratador de
# erro no fim precisa distinguir "travou antes de tocar em nada" de
# "travou com metade da populacao re-pontuada": a recuperacao e oposta.
ESCREVEU = False


def conecta(db):
    c = sqlite3.connect(db, timeout=BUSY_MS / 1000.0)
    c.execute("PRAGMA busy_timeout = %d" % BUSY_MS)
    return c

# A mesma forma que scores_api.py serve: indices 0..6, com sistema em [3],
# profile em [5] e payload em [6]. Mesma consulta, mesma leitura.
LATEST = """
SELECT address, ts, s_raw, sistema, stage, profile, payload FROM (
  SELECT address, ts, s_raw, sistema, stage, profile, payload,
         ROW_NUMBER() OVER (PARTITION BY address ORDER BY ts DESC, id DESC) rn
  FROM yaaf_scores
) WHERE rn = 1
"""


def sha256(caminho, bloco=1 << 20):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while True:
            b = f.read(bloco)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def constante(caminho, nome, conversor=str):
    """Le uma constante do fonte do scorer. Uma fonte, nao duas."""
    try:
        src = open(caminho, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"^%s\s*=\s*[\"']?([^\"'\s#]+)" % re.escape(nome), src, re.M)
    if not m:
        return None
    try:
        return conversor(m.group(1))
    except (TypeError, ValueError):
        return None


def limiar_do_contrato(sol):
    try:
        with open(sol, encoding="utf-8") as f:
            m = re.search(r"SCORE_THRESHOLD_ACTIVE\s*=\s*(\d+)", f.read())
    except OSError:
        return None
    return int(m.group(1)) if m else None


def perfis_do_api(api):
    """YAAF_PROFILES e MM_PROFILES lidos do scores_api, para nao haver
    segunda lista de perfis neste arquivo."""
    try:
        src = open(api, encoding="utf-8").read()
    except OSError:
        return None, None
    out = []
    for nome in ("YAAF_PROFILES", "MM_PROFILES"):
        m = re.search(nome + r"\s*=\s*[\(\[]([^\)\]]*)[\)\]]", src)
        out.append(tuple(x.strip().strip("\"'") for x in m.group(1).split(",")
                         if x.strip()) if m else None)
    return out[0], out[1]


def colunas(c, tabela):
    try:
        return [r[1] for r in c.execute("PRAGMA table_info(%s)" % tabela)]
    except sqlite3.Error:
        return []


def carrega_payload(valor, raiz):
    """A coluna `payload` do yaaf_scores. scores_api faz load_payload(r[6]),
    o que diz caminho; mas eu nao vi aquela funcao, entao aceito as duas
    formas e DIGO qual funcionou. Um probe que nao distingue 'vazio' de
    'nao consegui ler' reporta sucesso por nao ter lido nada."""
    if valor in (None, ""):
        return {}, "vazio"
    if isinstance(valor, bytes):
        try:
            valor = valor.decode("utf-8")
        except UnicodeDecodeError:
            return {}, "ilegivel"
    s = valor.strip()
    if s[:1] in "{[":
        try:
            d = json.loads(s)
            return (d if isinstance(d, dict) else {}), "json na coluna"
        except ValueError:
            return {}, "ilegivel"
    for cam in (s, os.path.join(raiz, s)):
        if os.path.isfile(cam):
            try:
                with open(cam, encoding="utf-8") as f:
                    d = json.load(f)
                return (d if isinstance(d, dict) else {}), "arquivo em disco"
            except (OSError, ValueError):
                return {}, "ilegivel"
    return {}, "caminho ausente"


def emits_rodando(obs):
    """Os pids de emit cujo cwd e ESTE observatory.

    O guarda existe porque duas escritas simultaneas avancam a EMA duas
    vezes. Mas `pgrep -f emit_yaaf` varre a maquina inteira, e um emit
    rodando em OUTRO diretorio -- a replica sintetica do teste de aceitacao,
    por exemplo -- nao ameaca este banco. Abortar por semelhanca de nome
    seria falha por motivo errado, que e pior do que nenhuma checagem:
    ensina a desconfiar do guarda.

    Comparar /proc/<pid>/cwd com o obs alvo e a pergunta exata. Quando o cwd
    nao da para ler, a duvida vai para o lado do banco se o alvo e a
    producao, e para o lado de prosseguir se nao e.
    """
    try:
        pids = subprocess.run(["pgrep", "-f", "emit_yaaf"],
                              stdout=subprocess.PIPE).stdout.decode().split()
    except OSError:
        return []
    meu = {str(os.getpid()), str(os.getppid())}
    alvo = os.path.realpath(obs)
    producao = alvo == os.path.realpath(OBS_PADRAO)
    perigosos = []
    for pid in pids:
        if pid in meu:
            continue
        try:
            cwd = os.path.realpath(os.readlink("/proc/%s/cwd" % pid))
        except OSError:
            if producao:
                perigosos.append("%s (cwd ilegivel)" % pid)
            continue
        if cwd == alvo:
            perigosos.append(pid)
    return perigosos


def retrato(db, limiar, yaaf, mm, raiz):
    c = conecta(db)
    rows = c.execute(LATEST).fetchall()
    r = {"enderecos": len(rows),
         "linhas": c.execute("SELECT COUNT(*) FROM yaaf_scores").fetchone()[0],
         "rodadas": c.execute(
             "SELECT COUNT(DISTINCT ts) FROM yaaf_scores").fetchone()[0],
         "bandas": {"YAAF": {}, "MM": {}, "unscored": {}},
         "versoes": {}, "elegiveis_contrato": 0, "payloads_com_is_eligible": 0,
         "payloads_yaaf_lidos": 0, "rotas": {},
         "sistema": {"min": None, "max": None, "media": None}}
    sis = []
    for a, ts, s_raw, sistema, stage, profile, payload in rows:
        eng = "YAAF" if profile in yaaf else ("MM" if profile in mm else "unscored")
        b = r["bandas"][eng]
        b[stage or "unknown"] = b.get(stage or "unknown", 0) + 1
        if eng != "YAAF":
            continue
        p, rota = carrega_payload(payload, raiz)
        r["rotas"][rota] = r["rotas"].get(rota, 0) + 1
        if p:
            r["payloads_yaaf_lidos"] += 1
        r["versoes"][p.get("score_version") or "unknown"] = \
            r["versoes"].get(p.get("score_version") or "unknown", 0) + 1
        if "is_eligible" in p:
            r["payloads_com_is_eligible"] += 1
        if limiar is not None and sistema is not None and sistema >= limiar:
            r["elegiveis_contrato"] += 1
        if sistema is not None:
            sis.append(float(sistema))
    if sis:
        r["sistema"] = {"min": min(sis), "max": max(sis),
                        "media": sum(sis) / len(sis)}
    cols = colunas(c, "yaaf_state")
    sel = ["COUNT(*)"]
    sel.append("SUM(total_trades)" if "total_trades" in cols else "NULL")
    sel.append("AVG(ema)" if "ema" in cols else "NULL")
    e = c.execute("SELECT %s FROM yaaf_state" % ", ".join(sel)).fetchone()
    r["yaaf_state"] = {"linhas": e[0], "soma_total_trades": e[1],
                       "ema_media": e[2], "colunas": cols}
    c.close()
    return r


def imprime_retrato(titulo, r):
    print("--- %s" % titulo)
    print("    enderecos %d   linhas %d   rodadas %d"
          % (r["enderecos"], r["linhas"], r["rodadas"]))
    for eng in ("YAAF", "MM", "unscored"):
        if r["bandas"][eng]:
            print("    %-9s %s" % (eng, "  ".join(
                "%s %d" % (b, r["bandas"][eng][b])
                for b in BANDAS + sorted(set(r["bandas"][eng]) - set(BANDAS))
                if r["bandas"][eng].get(b))))
    print("    payload lido por     : %s" % json.dumps(r["rotas"]))
    print("    versoes YAAF         : %s" % json.dumps(r["versoes"]))
    print("    elegiveis (contrato) : %s" % r["elegiveis_contrato"])
    print("    payloads com is_eligible: %s" % r["payloads_com_is_eligible"])
    s = r["sistema"]
    if s["media"] is not None:
        print("    SISTEMA min/med/max  : %.2f / %.2f / %.2f"
              % (s["min"], s["media"], s["max"]))
    e = r["yaaf_state"]
    print("    yaaf_state           : %d linhas, total_trades somado %s, ema media %s"
          % (e["linhas"], e["soma_total_trades"],
             ("%.2f" % e["ema_media"]) if e["ema_media"] is not None else "n/d"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--obs", default=OBS_PADRAO)
    ap.add_argument("--scorer", default=SCORER_PADRAO)
    ap.add_argument("--db", default=None, help="padrao: <obs>/observatory.db")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.confirm and not args.dry_run:
        print("ABORTADO: isto escreve no banco. Use --dry-run para so olhar,")
        print("ou --confirm para executar.")
        return 2

    db = args.db or os.path.join(args.obs, "observatory.db")
    for p in (db, args.scorer):
        if not os.path.isfile(p):
            print("ABORTADO: nao achei %s" % p)
            return 2

    # ---- 1. a versao do scorer ---------------------------------------
    v = constante(args.scorer, "VERSION_SCORE")
    print("scorer : %s  (%s)" % (v, args.scorer))
    if v != VERSAO_EXIGIDA:
        print("ABORTADO: este re-score e para %s. Re-pontuar sob outro codigo"
              % VERSAO_EXIGIDA)
        print("  significa re-pontuar duas vezes, e a segunda apaga a primeira.")
        return 2

    # ---- 2. EMA_INITIAL, do proprio scorer ---------------------------
    ema0 = constante(args.scorer, "EMA_INITIAL", float)
    if ema0 is None:
        print("ABORTADO: nao achei EMA_INITIAL em %s." % args.scorer)
        print("  Eu nao vou cravar 300.0 aqui: seria uma segunda constante,")
        print("  livre para divergir da que o scorer usa.")
        return 2
    print("EMA_INITIAL lido do scorer: %.4f" % ema0)

    sol = os.path.join(os.path.dirname(os.path.dirname(args.scorer)),
                       "contracts", "AIAgentRegistry.sol")
    limiar = limiar_do_contrato(sol)
    print("limiar do contrato: %s  (%s)" % (limiar, sol))

    api = os.path.join(args.obs, "scores_api.py")
    yaaf, mm = perfis_do_api(api)
    if not yaaf or not mm:
        print("ABORTADO: nao consegui ler YAAF_PROFILES/MM_PROFILES de %s." % api)
        print("  Sem eles eu teria de manter uma segunda lista de perfis, que e")
        print("  exatamente o tipo de duplicata que este trabalho vem removendo.")
        return 2
    print("perfis : YAAF %s   MM %s" % (list(yaaf), list(mm)))

    # ---- 3. os dois emits, e o --force -------------------------------
    emits = (("emit_yaaf_gmx.py", "yaaf_payloads_gmx"),
             ("emit_yaaf_final.py", "yaaf_payloads"))
    problemas = []
    for script, pdir in emits:
        cam = os.path.join(args.obs, script)
        if not os.path.isfile(cam):
            problemas.append("%s nao existe" % script)
            continue
        if "--force" not in open(cam, encoding="utf-8").read():
            problemas.append("%s nao menciona --force" % script)
        if not os.path.isdir(os.path.join(args.obs, pdir)):
            problemas.append("%s/ nao existe" % pdir)
    if problemas:
        print()
        for p in problemas:
            print("ABORTADO: %s" % p)
        print("  Rodar so metade dos emits deixa metade da populacao sob 5.6.0 e")
        print("  metade sob o codigo antigo -- o estado que este script existe")
        print("  para evitar. Nada foi tocado.")
        return 2
    print("emits  : os dois presentes e com --force")

    # ---- esquema do yaaf_state ---------------------------------------
    c = conecta(db)
    cols_estado = colunas(c, "yaaf_state")
    modo = c.execute("PRAGMA journal_mode").fetchone()[0]
    c.close()
    print("yaaf_state: %s" % (", ".join(cols_estado) or "(tabela ausente)"))
    print("journal_mode: %s" % modo)
    faltando = [x for x in ZERAR if x not in cols_estado]
    if faltando:
        print("ABORTADO: yaaf_state nao tem %s." % ", ".join(faltando))
        print("  O reset declarado e sobre essas tres colunas. Se o esquema")
        print("  mudou, a declaracao muda antes do codigo.")
        return 2
    intocadas = [x for x in cols_estado if x not in ZERAR and x != "updated_at"]
    print("o reset toca   : %s%s" % (", ".join(ZERAR),
                                     ", updated_at" if "updated_at" in cols_estado else ""))
    print("o reset NAO toca: %s" % (", ".join(intocadas) or "(nada)"))
    print()

    antes = retrato(db, limiar, yaaf, mm, args.obs)
    imprime_retrato("ANTES", antes)
    print()

    if antes["payloads_yaaf_lidos"] == 0 and antes["bandas"]["YAAF"]:
        print("ATENCAO: nenhum payload YAAF pude ser lido (rotas: %s)."
              % json.dumps(antes["rotas"]))
        print("  Entao 'versoes' e 'payloads com is_eligible' acima nao medem")
        print("  nada: eles leriam 'unknown' e 0 tanto antes quanto depois, e o")
        print("  0 pareceria cobertura completa. Sem essa leitura nao ha como")
        print("  verificar que o re-score cobriu a populacao.")
        if args.confirm:
            print("ABORTADO. Rode com --dry-run e me mande as rotas.")
            return 2

    if args.dry_run:
        print("--dry-run: nada foi escrito.")
        return 0

    # ---- outro emit rodando? -----------------------------------------
    achou = emits_rodando(args.obs)
    if achou:
        print("ABORTADO: ja ha emit rodando NESTE observatory (pid %s)."
              % " ".join(achou))
        print("  Duas escritas simultaneas avancam a EMA duas vezes.")
        print("  Espere ele terminar, ou pare o cron, e repita.")
        return 2
    agora = datetime.datetime.now(datetime.timezone.utc)
    if agora.hour == 2 and agora.minute >= 30:
        print("AVISO: o cron das 03:00 UTC esta a %d min. Se ele entrar no meio,"
              % (60 - agora.minute))
        print("  a EMA avanca duas vezes para parte da populacao.")

    # ---- 4. backup consistente ---------------------------------------
    stamp = agora.strftime("%Y%m%d-%H%M%S")
    bak = "%s.pre-rescore-%s" % (db, stamp)
    print("backup consistente (API de backup do sqlite3) -> %s" % bak)
    src = conecta(db)
    dst = conecta(bak)
    with dst:
        src.backup(dst)
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    cont_bak = [dst.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                for t in ("yaaf_scores", "yaaf_state")]
    cont_src = [src.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                for t in ("yaaf_scores", "yaaf_state")]
    dst.close()
    src.close()
    print("    integrity_check  : %s" % ok)
    print("    yaaf_scores      : %d no banco, %d no backup" % (cont_src[0], cont_bak[0]))
    print("    yaaf_state       : %d no banco, %d no backup" % (cont_src[1], cont_bak[1]))
    if ok != "ok" or cont_bak != cont_src:
        print("ABORTADO: o backup nao confere. Nada foi alterado no banco.")
        return 1
    h_db, h_bak = sha256(db), sha256(bak)
    print("    sha256 banco     : %s" % h_db)
    print("    sha256 backup    : %s" % h_bak)
    print("    (divergem por construcao: a API de backup reescreve paginas. O")
    print("     que prova a copia e o integrity_check e as contagens acima.)")
    restaurar = "cp -a %s %s" % (bak, db)
    if str(modo).lower() == "wal":
        restaurar = "rm -f %s-wal %s-shm && %s" % (db, db, restaurar)
    print("    para desfazer tudo: %s" % restaurar)
    print()

    # ---- 6 e 7. guardar e zerar o estado ------------------------------
    tab = "yaaf_state_pre_%s" % VERSAO_EXIGIDA.replace(".", "_").replace("-", "_").lower()
    c = conecta(db)
    sets = ["ema = ?", "round_history = '[]'", "total_trades = 0"]
    if "updated_at" in cols_estado:
        sets.append("updated_at = CURRENT_TIMESTAMP")
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("DROP TABLE IF EXISTS %s" % tab)
        c.execute("CREATE TABLE %s AS SELECT * FROM yaaf_state" % tab)
        guardadas = c.execute("SELECT COUNT(*) FROM %s" % tab).fetchone()[0]
        cur = c.execute("UPDATE yaaf_state SET %s" % ", ".join(sets), (ema0,))
        zeradas = cur.rowcount
        if guardadas != antes["yaaf_state"]["linhas"] or zeradas != guardadas:
            raise RuntimeError(
                "guardadas %d, zeradas %d, esperava %d nas duas"
                % (guardadas, zeradas, antes["yaaf_state"]["linhas"]))
        c.execute("COMMIT")
        global ESCREVEU
        ESCREVEU = True
    except Exception as e:
        c.execute("ROLLBACK")
        c.close()
        print("ABORTADO no reset do estado: %s" % e)
        print("  O banco esta como estava (transacao revertida).")
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            print("  Isso foi um lock, nao um defeito de dados: alguem estava")
            print("  escrevendo. Pare o cron de pontuacao e repita.")
        return 1
    c.close()
    print("estado guardado em %s: %d linhas" % (tab, guardadas))
    print("yaaf_state zerado: %d linhas, ema <- %.4f" % (zeradas, ema0))
    print()

    # ---- 8. os dois emits com --force --------------------------------
    env = dict(os.environ, PYTHONPATH=args.obs)
    logs = []
    for script, pdir in emits:
        log = "/tmp/rescore-%s-%s.log" % (script.replace(".py", ""), stamp)
        logs.append(log)
        print("rodando %s %s --force   (log em %s)" % (script, pdir, log))
        t0 = datetime.datetime.now()
        with open(log, "w") as fh:
            p = subprocess.run([sys.executable, os.path.join(args.obs, script),
                                pdir, "--force"],
                               cwd=args.obs, env=env, stdout=fh,
                               stderr=subprocess.STDOUT)
        dt = (datetime.datetime.now() - t0).total_seconds()
        with open(log) as fh:
            cauda = fh.read().splitlines()
        for l in cauda[-8:]:
            print("    | %s" % l)
        print("    (%.0fs, codigo %d)" % (dt, p.returncode))
        if p.returncode != 0:
            print()
            print("EXECUCAO PARCIAL. Nao rode de novo sem restaurar: os")
            print("enderecos ja feitos avancariam a EMA uma segunda vez.")
            print("  %s" % restaurar)
            return 1
        print()

    # ---- 9. o depois, e o veredito de cobertura ----------------------
    depois = retrato(db, limiar, yaaf, mm, args.obs)
    imprime_retrato("DEPOIS", depois)
    print()

    sobrou_versao = {k: n for k, n in depois["versoes"].items() if k != VERSAO_EXIGIDA}
    cobriu = (not sobrou_versao) and depois["payloads_com_is_eligible"] == 0
    if cobriu:
        print("COBERTURA: toda versao servida e %s e nenhum payload carrega"
              % VERSAO_EXIGIDA)
        print("  is_eligible. O re-score cobriu a populacao servida.")
    else:
        print("COBERTURA INCOMPLETA -- o re-score NAO cobriu a populacao:")
        if sobrou_versao:
            print("  versoes ainda servidas fora de %s: %s"
                  % (VERSAO_EXIGIDA, json.dumps(sobrou_versao)))
        if depois["payloads_com_is_eligible"]:
            print("  payloads ainda carregando is_eligible: %d"
                  % depois["payloads_com_is_eligible"])
        print("  Os enderecos restantes nao foram re-pontuados -- provavelmente")
        print("  nao ha payload para eles, ou ficaram abaixo de MIN_TRADES.")
        print("  NAO rode de novo sem restaurar: quem ja foi avancaria a EMA")
        print("  duas vezes.  %s" % restaurar)

    # ---- 10. o registro ----------------------------------------------
    doc = os.path.join(os.path.dirname(os.path.dirname(args.scorer)),
                       "docs", "RESCORE_%s.md" % stamp[:8])
    linhas = [
        "# Re-score, %s" % agora.isoformat(),
        "",
        "Scorer `%s`. Contract threshold %s. `EMA_INITIAL` %.4f, read from the"
        % (v, limiar, ema0),
        "scorer rather than restated here.",
        "",
        "Coverage: **%s**." % ("complete" if cobriu else "INCOMPLETE"),
        "",
        "## Reversibility",
        "",
        "| | |", "|---|---|",
        "| database backup | `%s` |" % os.path.basename(bak),
        "| backup method | sqlite3 backup API, `integrity_check` = `%s` |" % ok,
        "| rows verified in backup | `yaaf_scores` %d, `yaaf_state` %d |"
        % (cont_bak[0], cont_bak[1]),
        "| sha256 of database before | `%s` |" % h_db,
        "| sha256 of backup file | `%s` |" % h_bak,
        "| pre-reset `yaaf_state` | table `%s`, %d rows |" % (tab, guardadas),
        "| restore command | `%s` |" % restaurar,
        "",
        "The two hashes differ by construction: the backup API rewrites pages,",
        "so the backup is a logical copy, not a byte copy. What proves it is",
        "the integrity check and the row counts, both recorded above. A `cp` of",
        "a live database can capture a torn page, and under WAL it would lose",
        "the `-wal` sidecar entirely.",
        "",
        "## Before and after",
        "",
        "| | before | after |", "|---|---|---|",
        "| addresses | %d | %d |" % (antes["enderecos"], depois["enderecos"]),
        "| score rows | %d | %d |" % (antes["linhas"], depois["linhas"]),
        "| distinct rounds | %d | %d |" % (antes["rodadas"], depois["rodadas"]),
        "| eligible (contract >= %s) | %d | %d |" % (
            limiar, antes["elegiveis_contrato"], depois["elegiveis_contrato"]),
        "| payloads carrying `is_eligible` | %d | %d |" % (
            antes["payloads_com_is_eligible"], depois["payloads_com_is_eligible"]),
        "| scorer versions | `%s` | `%s` |" % (
            json.dumps(antes["versoes"]), json.dumps(depois["versoes"])),
        "| `yaaf_state` summed `total_trades` | %s | %s |" % (
            antes["yaaf_state"]["soma_total_trades"],
            depois["yaaf_state"]["soma_total_trades"]),
    ]
    for k in ("min", "media", "max"):
        a, d = antes["sistema"][k], depois["sistema"][k]
        linhas.append("| SISTEMA %s | %s | %s |" % (
            k, "n/a" if a is None else "%.2f" % a,
            "n/a" if d is None else "%.2f" % d))
    linhas += ["", "### YAAF bands", "",
               "| band | before | after |", "|---|---|---|"]
    for b in BANDAS:
        linhas.append("| %s | %d | %d |" % (
            b, antes["bandas"]["YAAF"].get(b, 0), depois["bandas"]["YAAF"].get(b, 0)))
    linhas += [
        "",
        "## What this run carries",
        "",
        "Four spec changes and one weight change, with effects of opposite",
        "sign: v5.3.0 (D6) raises `psr` for positive-Sharpe agents, v5.2.0",
        "(D11) and the EMA reset lower scores, v5.5.0 caps the drawdown tail,",
        "and v5.6.0 raises the mean level by equalizing the weights. The net",
        "per agent is not deducible from the signs; the table above is the",
        "measurement.",
        "",
        "The band counts produced before this run are historical, not wrong:",
        "they were the output of the specification in force at the time. Every",
        "published count must name the version that produced it.",
        "",
        "## Why the state was zeroed",
        "",
        "The reset touched `ema`, `round_history`, `total_trades`%s. It left"
        % (" and `updated_at`" if "updated_at" in cols_estado else ""),
        "%s untouched." % (", ".join("`%s`" % x for x in intocadas) or "nothing"),
        "",
        "EMA: `S_RAW` under 5.0.0 had an attainable ceiling of 88.0208 over 9",
        "components with `W_SUM` 0.96; under 5.6.0 it is 100 over 8 components",
        "with `W_SUM` 1.0. They are not the same quantity, and smoothing across",
        "that boundary averages incommensurable numbers. Recomputing the history",
        "under 5.6.0 is impossible: there is one snapshot of payloads, not a",
        "series.",
        "",
        "`round_history`: the same reason, and because 379 of 391 windows held a",
        "single repeated value.",
        "",
        "`total_trades`: because the stored value was wrong - 259 of 309",
        "addresses held a `total_trades` above their own fill count, which is",
        "impossible without accumulation (v5.2.0, D11).",
        "",
        "The pre-reset state is in table `%s`, so a published `SISTEMA`" % tab,
        "remains reproducible from the state that produced it.",
        "",
        "## Logs",
        "",
    ] + ["- `%s`" % l for l in logs] + [""]
    try:
        os.makedirs(os.path.dirname(doc), exist_ok=True)
        with open(doc, "w", encoding="utf-8") as fh:
            fh.write("\n".join(linhas))
        print()
        print("registro escrito: %s" % doc)
    except OSError as e:
        print("AVISO: nao consegui escrever %s (%s)" % (doc, e))
        print("\n".join(linhas))

    print()
    print("Agora: systemctl restart scores-api, rodar facts.py, conferir /stats,")
    print("e preencher os campos 'Measured effect' dos SPEC_CHANGE com a tabela")
    print("acima. O backup fica em %s ate voce decidir apagar."
          % os.path.basename(bak))
    return 0 if cobriu else 1


def envelope():
    """main() toca um banco vivo. Um lock nao e defeito de dados e nao pode
    sair como traceback: quem le um traceback nao sabe se o banco foi
    reescrito pela metade. Aqui a diferenca e dita em uma frase, e o codigo
    de saida separa 'nada foi tocado' de 'escreveu e parou no meio'."""
    try:
        return main()
    except sqlite3.Error as e:
        travado = any(x in str(e).lower() for x in ("locked", "busy"))
        print()
        if travado and not ESCREVEU:
            print("ABORTADO: o banco esta travado por outro escritor (%s)." % e)
            print("  NADA foi escrito. Isso nao e defeito de dados: o cron de")
            print("  pontuacao ou um emit esta rodando. Espere ele terminar,")
            print("  ou pare o cron, e repita.")
            return 3
        if travado:
            print("PAROU NO MEIO por lock do banco (%s)." % e)
            print("  O reset de estado JA foi aplicado. Nao rode de novo sem")
            print("  restaurar o backup: quem ja foi avancaria a EMA de novo.")
            return 1
        print("ABORTADO por erro de sqlite: %s" % e)
        print("  %s" % ("o reset JA foi aplicado -- restaure o backup antes de"
                        " repetir." if ESCREVEU else
                        "nada foi escrito."))
        return 1 if ESCREVEU else 2


if __name__ == "__main__":
    sys.exit(envelope())

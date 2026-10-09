#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_rescore_v560.py - teste de aceitacao do rescore_v560.py.

O rescore escreve no banco de producao uma vez e nao da para repetir: uma
segunda passada avanca a EMA de novo. Entao ele nao pode ser testado contra o
banco real. Este teste monta uma replica sintetica com o MESMO esquema e as
MESMAS formas de coluna, e exercita o rescore contra ela.

NAO toca em nada fora do diretorio temporario que cria.

O que cobre, e por que cada caso existe:

  A  payload como caminho em disco     -- scores_api faz load_payload(r[6]),
  B  payload como JSON na coluna          o que diz caminho; eu nao vi aquela
                                          funcao. Se o rescore errar a rota, le
                                          {} em toda linha e passa a reportar
                                          "0 payloads com is_eligible" e
                                          "versao unknown" ANTES e DEPOIS -- o
                                          0 pareceria cobertura completa. Os
                                          dois casos exigem que ele DIGA por
                                          qual rota leu.
  C  sem --confirm nem --dry-run        -- escrita so com pedido explicito.
  D  scorer na versao errada            -- re-pontuar sob outro codigo e
                                          re-pontuar duas vezes.
  E  um emit sem --force                -- metade da populacao sob 5.6.0 e
                                          metade sob o codigo velho.
  F  yaaf_state sem total_trades        -- o reset e declarado sobre tres
                                          colunas; se o esquema mudou, a
                                          declaracao muda antes do codigo.
  G  execucao completa, banco em WAL    -- o comando de restauracao tem de
                                          remover os sidecars -wal/-shm, senao
                                          "restaurar" deixa um banco hibrido.
  H  a restauracao realmente desfaz     -- backup que nao volta nao e backup.
  I  cobertura incompleta -> codigo 1   -- se sobrar versao velha ou payload
                                          com is_eligible, o script tem de
                                          dizer em voz alta, nao declarar
                                          sucesso.
  L  emit rodando em OUTRO diretorio   -- o guarda usa `pgrep -f emit_yaaf`,
  M  emit rodando NESTE diretorio       que varre a maquina toda. Um emit da
                                          replica do teste, ou de outro
                                          observatory, nao ameaca este banco:
                                          abortar por semelhanca de nome e
                                          falhar por motivo errado. O guarda
                                          compara /proc/<pid>/cwd com o obs
                                          alvo; L exige que ele prossiga e M
                                          que ele pare.
  J  banco travado por outro escritor  -- scores_api fica vivo e o cron pode
  K                                       entrar. Sem busy_timeout o sqlite
                                          devolve "locked" na hora, e um lock
                                          de milissegundos abortaria o reset.
                                          O caso trava o banco de verdade e
                                          exige que ele fique intacto (J) e
                                          que a mensagem distinga lock de
                                          defeito de dados (K).

Uso:  python3 test_rescore_v560.py [caminho/do/rescore_v560.py]
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import tempfile

PADRAO = "/root/yaaf/scorer/rescore_v560.py"
EMIT = '''import glob, json, os, sys
force = "--force" in sys.argv
argv = [a for a in sys.argv[1:] if a != "--force"]
pdir = argv[0] if argv else %r
feitos = 0
for i, p in enumerate(sorted(glob.glob(os.path.join("resultados", %r)))):
    if i < %d:
        continue
    d = json.load(open(p))
    d["score_version"] = "5.6.0-FORMAL"
    d.pop("is_eligible", None)
    json.dump(d, open(p, "w"))
    feitos += 1
print("processando %%d payloads de %%s  [force=%%s]" %% (feitos, pdir, force))
print("sem coleta nova desde a ultima pontuacao: 0")
print("scorers: {'5.6.0-FORMAL': %%d}" %% feitos)
'''


def monta(raiz, payload="arquivo", estado_completo=True, versao="5.6.0-FORMAL",
          emit_com_force=True, deixa_velho=0, journal="delete"):
    shutil.rmtree(raiz, ignore_errors=True)
    obs, yaaf = os.path.join(raiz, "obs"), os.path.join(raiz, "yaaf")
    for d in ("yaaf_payloads_gmx", "yaaf_payloads", "resultados"):
        os.makedirs(os.path.join(obs, d), exist_ok=True)
    for d in ("scorer", "contracts", "docs"):
        os.makedirs(os.path.join(yaaf, d), exist_ok=True)

    scorer = os.path.join(yaaf, "scorer", "yaaf_score_v5_formal.py")
    open(scorer, "w").write(
        'VERSION_SCORE = "%s"\nEMA_INITIAL = 300.0\nCAP_DD = 20.0\n' % versao)
    open(os.path.join(yaaf, "contracts", "AIAgentRegistry.sol"), "w").write(
        "uint256 public constant SCORE_THRESHOLD_ACTIVE = 500;\n")
    open(os.path.join(obs, "scores_api.py"), "w").write(
        'YAAF_PROFILES = ("gmx_perp", "hl_perp")\nMM_PROFILES = ("mm",)\n')
    open(os.path.join(obs, "emit_yaaf_gmx.py"), "w").write(
        EMIT % ("yaaf_payloads_gmx", "gmx_*.json", deixa_velho))
    open(os.path.join(obs, "emit_yaaf_final.py"), "w").write(
        (EMIT % ("yaaf_payloads", "hl_*.json", 0)) if emit_com_force
        else "print('este emit nao tem bandeira')\n")

    db = os.path.join(obs, "observatory.db")
    c = sqlite3.connect(db)
    c.execute("PRAGMA journal_mode=%s" % journal)
    c.execute("CREATE TABLE yaaf_scores (id INTEGER PRIMARY KEY, address TEXT,"
              " ts TEXT, s_raw REAL, sistema REAL, stage TEXT, profile TEXT,"
              " payload TEXT)")
    c.execute("CREATE TABLE yaaf_state (address TEXT PRIMARY KEY, ema REAL,"
              " round_history TEXT, %s last_sistema REAL%s)"
              % ("total_trades INTEGER," if estado_completo else "",
                 ", updated_at TEXT" if estado_completo else ""))
    pop = ([("gmx_perp", "gmx", 40, 520.0, "ELITE")] * 6
           + [("gmx_perp", "gmx", 20, 430.0, "VERIFIED")] * 9
           + [("hl_perp", "hl", 12, 310.0, "PROMISING")] * 5
           + [("mm", "mmx", 3, 280.0, "EXPERIMENTAL")] * 2)
    for i, (prof, pref, tt, sis, stage) in enumerate(pop):
        addr = "0x%040d" % i
        res = {"score_version": "5.0.0-FORMAL", "is_eligible": sis >= 400,
               "sistema": sis, "address": addr}
        rel = os.path.join("resultados", "%s_%03d.json" % (pref, i))
        json.dump(res, open(os.path.join(obs, rel), "w"))
        col = rel if payload == "arquivo" else json.dumps(res)
        for ts in ("2026-10-07 03:00:00", "2026-10-08 03:00:00"):
            c.execute("INSERT INTO yaaf_scores (address, ts, s_raw, sistema,"
                      " stage, profile, payload) VALUES (?,?,?,?,?,?,?)",
                      (addr, ts, sis / 10.0, sis, stage, prof, col))
        vals = ([addr, 480.0 + i, json.dumps([47.0] * 8)]
                + ([tt] if estado_completo else []) + [sis]
                + (["2026-10-08 03:00:00"] if estado_completo else []))
        c.execute("INSERT INTO yaaf_state VALUES (%s)"
                  % ",".join("?" * len(vals)), vals)
    c.commit()
    c.close()
    return obs, scorer


def roda(script, obs, scorer, *flags, **kw):
    env = dict(os.environ)
    env.update(kw.get("env") or {})
    p = subprocess.run([sys.executable, script, "--obs", obs,
                        "--scorer", scorer] + list(flags),
                       cwd=obs, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def main():
    # abspath ANTES de qualquer cwd=obs: roda() troca de diretorio, e um
    # caminho relativo passado na linha de comando deixaria de existir la.
    script = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else PADRAO)
    if not os.path.isfile(script):
        print("ABORTADO: nao achei %s" % script)
        return 2
    base = tempfile.mkdtemp(prefix="test_rescore_")
    print("script  : %s" % script)
    print("replica : %s" % base)
    print()
    falhas = []

    def checa(nome, ok, det=""):
        print("  %-54s %s" % (nome, "ok" if ok else "FALHOU"))
        if det:
            print("      %s" % det)
        if not ok:
            falhas.append(nome)

    raiz = os.path.join(base, "w")

    print("1) o rescore DIZ por qual rota leu a coluna payload")
    for letra, modo, esperado in (("A", "arquivo", "arquivo em disco"),
                                  ("B", "json", "json na coluna")):
        obs, sc = monta(raiz, payload=modo)
        cod, out = roda(script, obs, sc, "--dry-run")
        checa("%s payload=%s: rota nomeada, codigo 0" % (letra, modo),
              cod == 0 and esperado in out and '"5.0.0-FORMAL": 20' in out
              and "payloads com is_eligible: 20" in out,
              [l.strip() for l in out.splitlines() if "payload lido por" in l]
              or ["sem linha de rota; codigo %d" % cod])

    print()
    print("2) as pre-condicoes abortam antes de escrever")
    casos = [
        ("C sem --confirm nem --dry-run", {}, (), 2, "isto escreve no banco"),
        ("D scorer na versao errada", {"versao": "5.5.0-FORMAL"}, ("--confirm",),
         2, "este re-score e para 5.6.0-FORMAL"),
        ("E um emit sem --force", {"emit_com_force": False}, ("--confirm",),
         2, "nao menciona --force"),
        ("F yaaf_state sem total_trades", {"estado_completo": False},
         ("--dry-run",), 2, "nao tem total_trades"),
    ]
    for nome, kw, flags, esp, agulha in casos:
        obs, sc = monta(raiz, **kw)
        cod, out = roda(script, obs, sc, *flags)
        intacto = sqlite3.connect(os.path.join(obs, "observatory.db")).execute(
            "SELECT AVG(ema) FROM yaaf_state").fetchone()[0]
        checa(nome, cod == esp and agulha in out and abs(intacto - 490.5) < 1e-9,
              "codigo %d, banco intacto (ema media %.1f)" % (cod, intacto))

    print()
    print("3) execucao completa, banco em WAL")
    obs, sc = monta(raiz, journal="wal")
    cod, out = roda(script, obs, sc, "--confirm")
    db = os.path.join(obs, "observatory.db")
    if cod != 0:
        # Um teste que levanta excecao em vez de relatar diz menos do que um
        # que imprime o que aconteceu. Se o rescore nao chegou ao fim, as
        # consultas abaixo quebram sem explicar nada: mostre a saida.
        checa("G execucao completa", False, "codigo %d" % cod)
        print()
        print(out)
        return 1
    c = sqlite3.connect(db)
    ema, tt = c.execute("SELECT AVG(ema), SUM(total_trades) FROM yaaf_state").fetchone()
    guarda = c.execute("SELECT COUNT(*) FROM yaaf_state_pre_5_6_0_formal").fetchone()[0]
    ema_guarda = c.execute(
        "SELECT AVG(ema) FROM yaaf_state_pre_5_6_0_formal").fetchone()[0]
    c.close()
    checa("G codigo 0 e cobertura declarada completa",
          cod == 0 and "COBERTURA: toda versao servida" in out,
          "codigo %d" % cod)
    checa("G o estado foi zerado com EMA_INITIAL do scorer",
          abs(ema - 300.0) < 1e-9 and tt == 0,
          "ema media %.4f, total_trades somado %s" % (ema, tt))
    checa("G o estado anterior ficou guardado no banco",
          guarda == 22 and abs(ema_guarda - 490.5) < 1e-9,
          "%d linhas, ema media %.1f" % (guarda, ema_guarda))
    checa("G o restore em WAL remove os sidecars",
          "rm -f" in out and "-wal" in out and "-shm" in out,
          [l.strip() for l in out.splitlines() if "desfazer tudo" in l]
          or ["sem linha de restauracao"])
    checa("G o registro RESCORE_*.md foi escrito",
          bool([f for f in os.listdir(os.path.join(raiz, "yaaf", "docs"))
                if f.startswith("RESCORE_")]),
          "docs: %s" % os.listdir(os.path.join(raiz, "yaaf", "docs")))

    print()
    print("4) a restauracao desfaz de fato")
    bak = [f for f in os.listdir(obs) if ".pre-rescore-" in f]
    if len(bak) == 1:
        for sc_ in ("%s-wal" % db, "%s-shm" % db):
            if os.path.exists(sc_):
                os.remove(sc_)
        shutil.copy2(os.path.join(obs, bak[0]), db)
        c = sqlite3.connect(db)
        ema2, tt2 = c.execute(
            "SELECT AVG(ema), SUM(total_trades) FROM yaaf_state").fetchone()
        sobrou = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE"
                           " 'yaaf_state_pre%'").fetchone()[0]
        c.close()
        checa("H o backup devolve ema e total_trades originais",
              abs(ema2 - 490.5) < 1e-9 and tt2 == 486,
              "ema media %.1f, total_trades somado %s" % (ema2, tt2))
        checa("H o backup antecede a tabela de guarda", sobrou == 0,
              "tabelas yaaf_state_pre* no banco restaurado: %d" % sobrou)
    else:
        checa("H existe exatamente um backup", False, "achei %s" % bak)

    print()
    print("5) cobertura incompleta nao se declara sucesso")
    obs, sc = monta(raiz, deixa_velho=4)
    cod, out = roda(script, obs, sc, "--confirm")
    checa("I codigo 1 e o numero que sobrou, nomeado",
          cod == 1 and "COBERTURA INCOMPLETA" in out
          and '"5.0.0-FORMAL": 4' in out
          and "is_eligible: 4" in out,
          "codigo %d" % cod)
    doc = [f for f in os.listdir(os.path.join(raiz, "yaaf", "docs"))
           if f.startswith("RESCORE_")]
    texto = open(os.path.join(raiz, "yaaf", "docs", doc[0])).read() if doc else ""
    checa("I o registro escrito diz INCOMPLETE",
          "Coverage: **INCOMPLETE**" in texto,
          [l for l in texto.splitlines() if "Coverage" in l] or ["sem registro"])

    print()
    print("6) o guarda de emit olha o cwd, nao o nome do processo")
    # O dorminhoco mora FORA de raiz: monta() faz rmtree(raiz) e apagaria o
    # proprio arquivo, e entao o Popen morreria na hora -- o caso passaria ou
    # falharia sem nunca ter exercitado o guarda.
    dorminhoco = os.path.join(base, "emit_yaaf_dorminhoco.py")
    open(dorminhoco, "w").write("import time; time.sleep(60)\n")

    def com_emit_em(cwd, obs, sc, *flags):
        """Roda o rescore com um emit vivo em `cwd`. Confere a premissa antes
        de julgar: um Popen que morreu nao e um emit rodando, e um caso que
        nao estabeleceu a propria premissa nao mede nada."""
        pr = subprocess.Popen([sys.executable, dorminhoco], cwd=cwd,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                if pr.poll() is not None:
                    return None, "o emit falso morreu (codigo %s)" % pr.poll()
                try:
                    vivo = os.path.realpath(os.readlink("/proc/%d/cwd" % pr.pid))
                except OSError:
                    time.sleep(0.02)
                    continue
                if vivo == os.path.realpath(cwd):
                    break
                time.sleep(0.02)
            else:
                return None, "nao confirmei o cwd do emit falso"
            return roda(script, obs, sc, *flags), None
        finally:
            pr.kill()
            pr.wait()

    obs, sc = monta(raiz)
    res, erro = com_emit_em(base, obs, sc, "--confirm")
    checa("L emit em outro diretorio nao bloqueia",
          erro is None and res[0] == 0 and "ja ha emit rodando" not in res[1],
          erro or "codigo %d" % res[0])

    obs, sc = monta(raiz)
    res, erro = com_emit_em(obs, obs, sc, "--confirm")
    c = sqlite3.connect(os.path.join(obs, "observatory.db"))
    ema4 = c.execute("SELECT AVG(ema) FROM yaaf_state").fetchone()[0]
    c.close()
    checa("M emit neste diretorio bloqueia, sem escrever",
          erro is None and res[0] == 2
          and "ja ha emit rodando NESTE observatory" in res[1]
          and abs(ema4 - 490.5) < 1e-9,
          erro or "codigo %d, ema media %.1f" % (res[0], ema4))

    print()
    print("7) um lock nao e confundido com defeito de dados")
    obs, sc = monta(raiz)
    db = os.path.join(obs, "observatory.db")
    preso = sqlite3.connect(db)
    preso.execute("BEGIN EXCLUSIVE")
    preso.execute("UPDATE yaaf_state SET last_sistema = last_sistema")
    cod, out = roda(script, obs, sc, "--confirm", env={"YAAF_BUSY_MS": "800"})
    preso.execute("ROLLBACK")
    preso.close()
    c = sqlite3.connect(db)
    ema3 = c.execute("SELECT AVG(ema) FROM yaaf_state").fetchone()[0]
    guarda3 = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE"
                        " 'yaaf_state_pre%'").fetchone()[0]
    c.close()
    checa("J com o banco travado, codigo 3 e banco intacto",
          cod == 3 and abs(ema3 - 490.5) < 1e-9 and guarda3 == 0,
          "codigo %d (3 = travado, nada escrito), ema media %.1f, "
          "tabelas de guarda %d" % (cod, ema3, guarda3))
    checa("K diz que e lock, sem traceback",
          "travado por outro escritor" in out and "NADA foi escrito" in out
          and "Traceback" not in out,
          [l.strip() for l in out.splitlines()
           if "ABORTADO" in l or "Traceback" in l] or ["sem a linha"])

    shutil.rmtree(base, ignore_errors=True)
    print()
    if falhas:
        print("=== %d FALHA(S) ===" % len(falhas))
        for f in falhas:
            print("  - %s" % f)
        return 1
    print("=== tudo passou: o rescore se comporta nos 13 casos ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

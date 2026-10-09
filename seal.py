#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seal.py — sela os insumos de uma medicao e verifica o selo depois.

Produz dois arquivos:

  MANIFEST-sha256.txt   uma linha por insumo: "<sha256>  <caminho relativo>",
                        ordenadas pelos bytes do caminho. SO isso. Nenhum
                        comentario, nenhuma data, nenhum cabecalho — e por isso
                        que o arquivo e reproduzivel byte a byte por um
                        estranho que tenha os mesmos insumos.

  MANIFEST-root.txt     a raiz (sha256 do manifesto) mais a contagem de
                        arquivos e o total de bytes. Metadados ficam AQUI,
                        fora do calculo da raiz, para nao contaminar a
                        reprodutibilidade.

O manifesto nao revela conteudo: o hash de um payload diz que aquele conteudo
existia naquela data, nao o que havia dentro dele. Publica-se a digital e
guarda-se o corpo — que e o que permite selar payloads com endereco, S_RAW e
PnL futuro sem expor nenhum dos tres.

Os insumos e o selo nao precisam morar no mesmo lugar. --base diz onde estao
os insumos (e a que os caminhos do manifesto sao relativos); --out diz onde
escrever o selo. Isso existe porque o selo nao revela nada e portanto pode ser
commitado num repositorio publico, enquanto os insumos ficam no privado.

Uso:
  selar:      python3 seal.py --base /root/obs  yaaf_payloads_gmx
              python3 seal.py --base /root/obs  yaaf_payloads_gmx wallets.json
              ... --out /root/yaaf/docs/evidence/gmx_v2   selo noutro lugar
              ... --expect-files 500        falha se a contagem nao bater
  verificar:  python3 seal.py --base /root/obs --verify
              python3 seal.py --base /root/obs --verify --out /root/yaaf/docs/evidence/gmx_v2
"""
import argparse
import hashlib
import io
import os
import sys

NOME_MANIFESTO = "MANIFEST-sha256.txt"
NOME_RAIZ      = "MANIFEST-root.txt"
CHUNK          = 1 << 20
VERSAO         = "seal.py/1"


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    total = 0
    with open(caminho, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
            total += len(b)
    return h.hexdigest(), total


SELO_ABS = set()   # caminhos absolutos do manifesto e da raiz desta execucao


def por_que_ignorar(abs_p, rel):
    """None se o arquivo e selavel; caso contrario, a razao.

    Selar e verificar PRECISAM usar este mesmo teste. Se verificar usasse
    um teste mais largo, um arquivo que selar recusou apareceria como
    'novo' na verificacao e um selo intacto seria dado como quebrado.
    """
    if rel.startswith(".."):
        return "fora de --base"
    if os.path.abspath(abs_p) in SELO_ABS:
        return "e o proprio selo"
    if os.path.islink(abs_p):
        return "link simbolico (nao seguido)"
    if not os.path.isfile(abs_p):
        return "nao e arquivo comum"
    return None


def recolher(base, alvos, excluir):
    """Devolve (entradas, ignorados, por_alvo). entradas = [(relpath, abspath)].

    por_alvo mapeia cada alvo pedido para quantos arquivos rendeu, ou None se
    o alvo nao existe. Um alvo com nome errado nao pode selar em silencio: o
    selo sairia valido cobrindo menos do que foi pedido, que e justamente a
    falha que este arquivo existe para impedir.
    """
    entradas, ignorados, por_alvo = [], [], {}

    def considerar(abs_p):
        rel = os.path.relpath(abs_p, base).replace(os.sep, "/")
        razao = por_que_ignorar(abs_p, rel)
        if razao == "e o proprio selo":
            return                              # sem ruido
        if razao:
            ignorados.append((rel, razao))
            return
        entradas.append((rel, abs_p))

    for alvo in alvos:
        antes = len(entradas)
        abs_alvo = alvo if os.path.isabs(alvo) else os.path.join(base, alvo)
        abs_alvo = os.path.abspath(abs_alvo)
        if os.path.isdir(abs_alvo):
            for raiz, dirs, arquivos in os.walk(abs_alvo, followlinks=False):
                dirs.sort()
                for nome in sorted(arquivos):
                    considerar(os.path.join(raiz, nome))
            por_alvo[alvo] = len(entradas) - antes
        elif os.path.exists(abs_alvo):
            considerar(abs_alvo)
            por_alvo[alvo] = len(entradas) - antes
        else:
            por_alvo[alvo] = None

    # ordem canonica: bytes do caminho relativo, independente de locale
    entradas.sort(key=lambda e: e[0].encode("utf-8"))
    return entradas, ignorados, por_alvo


def escrever_texto(caminho, texto):
    # newline='\n' explicito: um \r\n mudaria a raiz
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def ler_manifesto(caminho):
    linhas = io.open(caminho, encoding="utf-8", newline="\n").read().split("\n")
    fora = {}
    for i, ln in enumerate(linhas, 1):
        if not ln:
            continue
        if "  " not in ln:
            raise ValueError("linha %d do manifesto nao tem o separador de dois espacos" % i)
        h, rel = ln.split("  ", 1)
        if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
            raise ValueError("linha %d do manifesto nao tem um sha256" % i)
        if rel in fora:
            raise ValueError("caminho repetido no manifesto: %s" % rel)
        fora[rel] = h
    return fora


def selar(args):
    base = os.path.abspath(args.base)
    if not os.path.isdir(base):
        print("ABORTADO: --base nao e um diretorio: %s" % base)
        return 2
    if not args.alvos:
        print("ABORTADO: nenhum alvo. Diga o que selar.")
        return 2

    saida = os.path.abspath(args.out) if args.out else base
    if not os.path.isdir(saida):
        print("ABORTADO: --out nao e um diretorio: %s" % saida)
        return 2
    p_man = os.path.join(saida, NOME_MANIFESTO)
    p_raiz = os.path.join(saida, NOME_RAIZ)
    if os.path.exists(p_man) and not args.force:
        print("ABORTADO: %s ja existe." % NOME_MANIFESTO)
        print("  Um selo existente nao se sobrescreve por acidente: isso apagaria")
        print("  a amarra que ele e. Para conferir, use --verify.")
        print("  Para selar de novo de proposito, use --force.")
        return 2

    SELO_ABS.clear()
    SELO_ABS.update({os.path.abspath(p_man), os.path.abspath(p_raiz)})
    entradas, ignorados, por_alvo = recolher(base, args.alvos, {NOME_MANIFESTO, NOME_RAIZ})

    ausentes = [a for a, n in por_alvo.items() if n is None]
    vazios   = [a for a, n in por_alvo.items() if n == 0]
    if ausentes or vazios:
        print("ABORTADO: ha alvo que nao rendeu insumo nenhum.")
        for a in ausentes:
            print("    nao existe : %s" % a)
        for a in vazios:
            print("    vazio      : %s" % a)
        print("  Um selo que cobre menos do que foi pedido sai valido e engana.")
        print("  Confira o nome do alvo e --base antes de selar.")
        return 1

    if not entradas:
        print("ABORTADO: nenhum arquivo encontrado nos alvos.")
        print("  Um manifesto vazio com raiz valida e pior que nenhum manifesto:")
        print("  parece um selo e nao sela nada.")
        for rel, por in ignorados:
            print("    ignorado: %-50s %s" % (rel, por))
        return 1

    if args.expect_files is not None and len(entradas) != args.expect_files:
        print("ABORTADO: esperava %d arquivos, encontrei %d." %
              (args.expect_files, len(entradas)))
        print("  A contagem faz parte do inventario. Resolva a diferenca antes de selar.")
        return 1

    linhas, total_bytes = [], 0
    for rel, abs_p in entradas:
        h, n = sha256_arquivo(abs_p)
        linhas.append("%s  %s" % (h, rel))
        total_bytes += n

    corpo = "\n".join(linhas) + "\n"
    escrever_texto(p_man, corpo)
    raiz = hashlib.sha256(corpo.encode("utf-8")).hexdigest()

    escrever_texto(p_raiz,
        "root    %s\n"
        "files   %d\n"
        "bytes   %d\n"
        "tool    %s\n"
        "base    %s\n"
        "targets %s\n"
        % (raiz, len(entradas), total_bytes, VERSAO,
           os.path.basename(base), " ".join(args.alvos)))

    print("=== selado ===")
    for a in args.alvos:
        print("  alvo     : %-40s %d arquivo(s)" % (a, por_alvo[a]))
    print("  arquivos : %d" % len(entradas))
    print("  bytes    : %d" % total_bytes)
    print("  manifesto: %s" % p_man)
    print("  raiz     : %s" % raiz)
    for rel, por in ignorados:
        print("  ignorado : %-50s %s" % (rel, por))
    print()
    if saida != base:
        print("  O selo foi escrito fora da base. Para verificar, repita o mesmo --out.")
        print()
    print("  Commite os dois arquivos no MESMO commit do resultado da medicao.")
    print("  A raiz sem data de commit nao prova nada: e o commit datado que")
    print("  mostra que os insumos foram fixados antes de ver o resultado.")
    return 0


def verificar(args):
    base = os.path.abspath(args.base)
    saida = os.path.abspath(args.out) if args.out else base
    p_man = os.path.join(saida, NOME_MANIFESTO)
    p_raiz = os.path.join(saida, NOME_RAIZ)
    if not os.path.exists(p_man):
        print("ABORTADO: nao ha %s em %s" % (NOME_MANIFESTO, saida))
        if saida == base:
            print("  Se o selo foi escrito com --out, repita o mesmo --out aqui.")
        return 2

    corpo = io.open(p_man, "rb").read()
    raiz_calc = hashlib.sha256(corpo).hexdigest()

    raiz_decl = None
    files_decl = bytes_decl = None
    if os.path.exists(p_raiz):
        for ln in io.open(p_raiz, encoding="utf-8").read().splitlines():
            p = ln.split()
            if len(p) == 2 and p[0] == "root":
                raiz_decl = p[1]
            elif len(p) == 2 and p[0] == "files":
                files_decl = int(p[1])
            elif len(p) == 2 and p[0] == "bytes":
                bytes_decl = int(p[1])

    print("=== raiz ===")
    print("  calculada : %s" % raiz_calc)
    if raiz_decl is None:
        print("  declarada : (sem %s)" % NOME_RAIZ)
    elif raiz_decl == raiz_calc:
        print("  declarada : igual")
    else:
        print("  declarada : %s" % raiz_decl)
        print("  O manifesto foi alterado depois de selado. Pare aqui.")
        return 1

    try:
        esperado = ler_manifesto(p_man)
    except ValueError as e:
        print("ABORTADO: manifesto malformado: %s" % e)
        return 1

    if files_decl is not None and files_decl != len(esperado):
        print("  ATENCAO: %s diz %d arquivos, o manifesto tem %d (truncado?)"
              % (NOME_RAIZ, files_decl, len(esperado)))

    iguais, mudados, faltando, total_bytes = 0, [], [], 0
    for rel in sorted(esperado, key=lambda r: r.encode("utf-8")):
        abs_p = os.path.join(base, rel)
        if not os.path.isfile(abs_p):
            faltando.append(rel)
            continue
        h, n = sha256_arquivo(abs_p)
        total_bytes += n
        if h == esperado[rel]:
            iguais += 1
        else:
            mudados.append(rel)

    # arquivos novos dentro dos diretorios que o manifesto cobre
    dirs_cobertos = sorted({os.path.dirname(r) for r in esperado if os.path.dirname(r)})
    SELO_ABS.clear()
    SELO_ABS.update({os.path.abspath(p_man), os.path.abspath(p_raiz)})
    novos, ignorados = [], []
    for d in dirs_cobertos:
        abs_d = os.path.join(base, d)
        if not os.path.isdir(abs_d):
            continue
        for raiz_w, _dirs, arquivos in os.walk(abs_d, followlinks=False):
            for nome in arquivos:
                abs_p = os.path.join(raiz_w, nome)
                rel = os.path.relpath(abs_p, base).replace(os.sep, "/")
                if rel in esperado:
                    continue
                razao = por_que_ignorar(abs_p, rel)
                if razao == "e o proprio selo":
                    continue
                if razao:
                    ignorados.append((rel, razao))   # selar tambem o recusaria
                else:
                    novos.append(rel)

    print("=== insumos ===")
    print("  no manifesto : %d" % len(esperado))
    print("  identicos    : %d" % iguais)
    print("  alterados    : %d" % len(mudados))
    print("  ausentes     : %d" % len(faltando))
    print("  novos        : %d  (nao estavam no selo)" % len(novos))
    if ignorados:
        print("  ignorados    : %d  (selar tambem nao os selaria)" % len(ignorados))
    if bytes_decl is not None and not faltando and not mudados:
        print("  bytes        : %d (declarado %d)%s" %
              (total_bytes, bytes_decl, "" if total_bytes == bytes_decl else "  <-- difere"))
    for rel in mudados[:20]:
        print("    alterado: %s" % rel)
    for rel in faltando[:20]:
        print("    ausente : %s" % rel)
    for rel in sorted(novos)[:20]:
        print("    novo    : %s" % rel)
    for rel, por in sorted(ignorados)[:20]:
        print("    ignorado: %-50s %s" % (rel, por))
    if max(len(mudados), len(faltando), len(novos)) > 20:
        print("    (lista truncada em 20 por categoria)")

    if mudados or faltando or novos:
        print()
        print("  O selo NAO confere. A medicao que aponta para esta raiz nao pode")
        print("  ser apresentada como reproduzida com estes insumos.")
        return 1

    print()
    print("  Confere. Os insumos sao os mesmos que produziram a raiz acima.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Sela e verifica os insumos de uma medicao.")
    ap.add_argument("alvos", nargs="*", help="diretorios ou arquivos, relativos a --base")
    ap.add_argument("--base", required=True, help="diretorio raiz; os caminhos do manifesto sao relativos a ele")
    ap.add_argument("--verify", action="store_true", help="verifica um selo existente")
    ap.add_argument("--force", action="store_true", help="re-sela sobre um manifesto existente")
    ap.add_argument("--out", default=None, metavar="DIR",
                    help="onde escrever/ler o selo (padrao: --base). Os caminhos do "
                         "manifesto continuam relativos a --base.")
    ap.add_argument("--expect-files", type=int, default=None, help="falha se a contagem nao bater")
    args = ap.parse_args()
    return verificar(args) if args.verify else selar(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
patch_v510.py — remove o Axioma de Volume do portao de avaliabilidade.

NAO e correcao de defeito. E a retirada deliberada de uma regra declarada na
especificacao formal, decidida depois de medir o que ela fazia:

  165 dos 363 agentes servidos tinham s_raw = 0 por reprovar o portao, e o campo
  volume_ok confundia duas causas — piso de trades e axioma de volume. Entre os
  reprovados havia um agente com 72.545 trades acumulados, excluido porque o PnL
  medio absoluto dele nao passava de onze dolares: initial_balance=11000.0 e
  default fixo na assinatura e VOLUME_FLOOR_FRAC=0.001 o converte num piso em
  dolar, igual para todo agente, numa estrutura que se declara scale-free. O
  axioma nao excluia agentes ruins; excluia agentes pequenos.

Por isso a versao vai para 5.1.0-FORMAL e nao 5.0.3: muda quem esta na
populacao, nao a escala do score.

O que fica:
  * volume_axiom_ok e VOLUME_FLOOR_FRAC permanecem no modulo, rotulados como NAO
    aplicados. Apagar a implementacao de uma regra que esta na especificacao
    tornaria a especificacao inverificavel.
  * initial_balance permanece na assinatura, sem uso. O ic_test_gmx_v2.py, que e
    evidencia commitada e produziu o rho = 0.2540, passa esse argumento; remove-lo
    quebraria o script canonico.

O que muda de nome:
  * volume_ok sai do retorno. Depois desta mudanca ele valeria exatamente
    n_trades >= MIN_TRADES_SRAW, e um campo chamado volume_ok sem checagem de
    volume mente pelo nome. Entram assessable (bool) e gate (None | "min_trades").
    Nada fora do scorer lia volume_ok — verificado por grep antes de remover.

Uso:
  cd /root/yaaf/scorer && python3 patch_v510.py && python3 test_saturation.py
"""
import sys
from pathlib import Path

ALVO = Path("yaaf_score_v5_formal.py")
feitas, ja, faltou = [], [], []


def sub(rot, a, b):
    global s
    if a in s:
        s = s.replace(a, b, 1); feitas.append(rot)
    elif b in s:
        ja.append(rot)
    else:
        faltou.append(rot)


if not ALVO.exists():
    print("ABORTADO: rode de dentro de /root/yaaf/scorer")
    sys.exit(1)
s = ALVO.read_text(encoding="utf-8")
original = s

sub("versao 5.1.0",
    'VERSION_SCORE = "5.0.2-FORMAL"',
    'VERSION_SCORE = "5.1.0-FORMAL"')

sub("rotulo em volume_axiom_ok",
    '''def volume_axiom_ok(trades, initial_balance, floor_frac=VOLUME_FLOOR_FRAC):
    if not trades or initial_balance <= 0:''',
    '''def volume_axiom_ok(trades, initial_balance, floor_frac=VOLUME_FLOOR_FRAC):
    """NAO APLICADO desde a v5.1.0. Mantido para que a regra da especificacao
    continue verificavel, nao porque o portao a use.

    O criterio e um piso em dolar: media(|pnl|) >= initial_balance * floor_frac,
    com initial_balance fixo em 11000.0 para todo agente. Media de PnL absoluto
    acima de onze dolares. Isso exclui agentes pequenos, nao agentes ruins —
    media de 363 agentes servidos, 165 reprovados no portao, entre eles um com
    72.545 trades acumulados. Ver docs/SPEC_CHANGE_v5.1.0.md.
    """
    if not trades or initial_balance <= 0:''')

sub("portao: so o piso de trades",
    '''    n_trades = int(metrics.get("trades", 0))
    if n_trades < MIN_TRADES_SRAW:
        vol_ok = False
    else:
        vol_ok = True
        if trades is not None:
            vol_ok = volume_axiom_ok(trades, initial_balance)''',
    '''    # v5.1.0: o portao de avaliabilidade e o piso de trades, e so ele. O Axioma
    # de Volume saiu — ver docs/SPEC_CHANGE_v5.1.0.md. O parametro initial_balance
    # permanece na assinatura, sem uso, porque o ic_test_gmx_v2.py o passa e aquele
    # script e evidencia commitada.
    n_trades = int(metrics.get("trades", 0))
    assessable = n_trades >= MIN_TRADES_SRAW
    gate = None if assessable else "min_trades"''')

sub("condicao do core",
    '    if n_trades >= MIN_TRADES_SRAW and vol_ok:',
    '    if assessable:')

sub("campos devolvidos",
    '        "volume_ok": vol_ok, "s_raw": s_raw, "ema_prev": ema_prev, "ema_new": ema_new,',
    '        "assessable": assessable, "gate": gate,\n'
    '        "s_raw": s_raw, "ema_prev": ema_prev, "ema_new": ema_new,')

if s == original:
    print("nada mudou.")
else:
    bak = ALVO.with_suffix(".py.pre-v510")
    if not bak.exists():
        bak.write_text(original, encoding="utf-8")
        print(f"backup: {bak}")
    ALVO.write_text(s, encoding="utf-8")

print("aplicadas:", feitas or "nenhuma")
if ja:
    print("ja estavam:", ja)
if faltou:
    print("NAO CASARAM:", faltou)
    print("  Restaure o backup e me mande as linhas correspondentes.")
    sys.exit(2)
sys.exit(0)

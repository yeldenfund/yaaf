#!/usr/bin/env python3
"""
patch_v502.py — aplica a Emenda v5.0.2 (D1 + D2 + D3) e o D10 ao
yaaf_score_v5_formal.py.

  D1  remove o componente 9, Smoothness^2 (w=0.08). Nenhuma formula disponivel e
      simultaneamente scale-free, sign-aware, n-estavel e independente do fator de
      retorno neste horizonte. Medido: zero em 151 dos 152 agentes.
  D2  funde avg_r e expectancy num componente de peso 0.16, cap 1.5. Correlacao
      medida entre os dois: +1.0000.
  D3  remove o componente 11, Mc (w=0.07). Constante 50 para todo agente.
  D10 poe piso zero na penalidade de CVaR. min(cvar/2, 1) nao tem limite inferior
      e compute_cvar devolve negativo quando os 5% piores trades sao lucrativos:
      a penalidade virava bonus sem teto. Medido: +30.0000 pontos com cvar_95=-4.
      NAO esta na Emenda v5.0.2; encontrado pelo test_saturation.py.

W_SUM e sum(W.values()), entao passa de 0.96 a 0.81 sozinho. Teto: 100.0000 exato.

FORA deste patch, de proposito:
  D5  renomear dsr -> psr. O scores_api.py filtra pela chave literal "dsr"; renomear
      aqui faria o filtro deixar de casar e o PSR voltaria a ser servido. Exige
      mudanca coordenada nos dois arquivos.
  D6  n_obs = n_trades em vez de n_daily. Muda o score de todo agente e vai com D5.
  is_eligible = sistema >= 400 (linha 274). O contrato usa 500. A correcao nao e
      trocar o numero: e parar de duplicar um predicado que o contrato ja decide.

Uso:
  cd /root/yaaf/scorer && python3 patch_v502.py && python3 test_saturation.py
"""
import sys
from pathlib import Path

ALVO = Path("yaaf_score_v5_formal.py")
feitas, faltou, ja = [], [], []


def sub(rot, a, b):
    global s
    if a in s:
        s = s.replace(a, b, 1); feitas.append(rot)
    elif b in s:
        ja.append(rot)
    else:
        faltou.append(rot)


if not ALVO.exists():
    print(f"ABORTADO: {ALVO} nao esta aqui. Rode de dentro de /root/yaaf/scorer.")
    sys.exit(1)
s = ALVO.read_text(encoding="utf-8")
original = s

sub("versao",
    'VERSION_SCORE = "5.0.0-FORMAL"',
    'VERSION_SCORE = "5.0.2-FORMAL"')

sub("D1+D2+D3: tabela de pesos",
    '''W = {
    "sharpe_dsr": 0.14, "sortino": 0.07, "winrate": 0.08, "pf": 0.10,
    "avg_r": 0.07, "expectancy": 0.09, "vol": 0.05, "stability": 0.09,
    "smoothness": 0.08, "pf_pct": 0.12, "mc": 0.07,
}''',
    '''W = {
    "sharpe_dsr": 0.14, "sortino": 0.07, "winrate": 0.08, "pf": 0.10,
    "avg_r": 0.16, "vol": 0.05, "stability": 0.09, "pf_pct": 0.12,
}''')

sub("comentario do W_SUM",
    '''# A tabela do spec soma 0.96, nao 1.00 como o texto normativo afirma.
# A soma ponderada e dividida por W_SUM para que S_RAW use a faixa [0,100]
# declarada, preservando a importancia relativa calibrada. Ver Emenda v5.0.1.
W_SUM = sum(W.values())''',
    '''# Emenda v5.0.2, D1 + D2 + D3. A tabela do spec somava 0.96 com 0.15 de peso
# inerte: Smoothness^2 era zero em 151 dos 152 agentes medidos e Mc era a
# constante 50 para todos, o que punha o teto atingivel de S_RAW em 88.0208.
# Removidos os dois e fundidos avg_r e expectancy (correlacao medida +1.0000)
# num componente de peso 0.16, sobram 8 componentes somando 0.81, todos capazes
# de chegar a 100 — e o teto passa a ser exatamente 100.0000.
# A divisao por W_SUM preserva a importancia relativa calibrada.
W_SUM = sum(W.values())''')

sub("D2+D1+D3: leitura das metricas",
    '''    avg_r     = finite(metrics.get("avg_r"))
    exp_r     = finite(metrics.get("expectancy_r"))
    vol_r     = finite(metrics.get("vol_r"))
    stability = clamp(finite(metrics.get("stability"), 0.5), 0.0, 1.0)
    smoothness= clamp(finite(metrics.get("smoothness")), 0.0, 1.0)
    max_dd    = max(finite(metrics.get("max_dd_pct")), 0.0)
    pf_pct    = clamp(finite(metrics.get("pf_pct"), 50.0), 0.0, 100.0)
    s_mc_val  = clamp(finite(metrics.get("s_mc"), 50.0), 0.0, 100.0)
    mc_beta   = finite(metrics.get("mc_beta"), 0.0)''',
    '''    avg_r     = finite(metrics.get("avg_r"))
    vol_r     = finite(metrics.get("vol_r"))
    stability = clamp(finite(metrics.get("stability"), 0.5), 0.0, 1.0)
    max_dd    = max(finite(metrics.get("max_dd_pct")), 0.0)
    pf_pct    = clamp(finite(metrics.get("pf_pct"), 50.0), 0.0, 100.0)''')

sub("D2+D1+D3: componentes",
    '''    s_avg_r      = clamp(avg_r / CAP_AVG_R, 0.0, 1.0) * 100.0
    s_expectancy = clamp(max(exp_r, 0.0) / CAP_EXPECT, 0.0, 1.0) * 100.0
    s_vol        = clamp(1.0 - vol_r / CAP_VOL_R, 0.0, 1.0) * 100.0
    s_stability  = (stability ** 2) * 100.0
    s_smoothness = (smoothness ** 2) * 100.0
    s_pf_pct     = pf_pct
    s_mc         = s_mc_val''',
    '''    # D2: avg_r e expectancy eram a mesma variavel com caps diferentes
    # (rho = +1.0000). Fundidos no cap 1.5, porque 0.6 saturava num R medio que
    # agentes competentes excedem de rotina — cego exatamente no topo da faixa.
    s_avg_r      = clamp(avg_r / CAP_AVG_R, 0.0, 1.0) * 100.0
    s_vol        = clamp(1.0 - vol_r / CAP_VOL_R, 0.0, 1.0) * 100.0
    s_stability  = (stability ** 2) * 100.0
    s_pf_pct     = pf_pct''')

sub("D10: piso na penalidade de CVaR",
    '    cvar_pen = min(cvar_95 / CVAR_CAP, 1.0) * CVAR_PEN_SCALE',
    '''    # D10: min(...) nao tem limite inferior e compute_cvar devolve valor negativo
    # quando os 5% piores trades sao lucrativos, entao a penalidade virava bonus
    # sem teto. Medido: +30.0000 pontos com cvar_95 = -4. O dd_pen ja tinha piso.
    cvar_pen = clamp(cvar_95 / CVAR_CAP, 0.0, 1.0) * CVAR_PEN_SCALE''')

sub("D1+D2+D3: soma do core",
    '''        core = (
            s_sharpe_dsr * W["sharpe_dsr"] + s_sortino * W["sortino"]
            + s_winrate * W["winrate"] + s_pf * W["pf"]
            + s_avg_r * W["avg_r"] + s_expectancy * W["expectancy"]
            + s_vol * W["vol"] + s_stability * W["stability"]
            + s_smoothness * W["smoothness"] + s_pf_pct * W["pf_pct"]
            + s_mc * W["mc"]
        ) / W_SUM''',
    '''        core = (
            s_sharpe_dsr * W["sharpe_dsr"] + s_sortino * W["sortino"]
            + s_winrate * W["winrate"] + s_pf * W["pf"]
            + s_avg_r * W["avg_r"] + s_vol * W["vol"]
            + s_stability * W["stability"] + s_pf_pct * W["pf_pct"]
        ) / W_SUM''')

sub("D1+D2+D3: campos devolvidos",
    '''        "s_sharpe": s_sharpe_dsr, "s_sortino": s_sortino, "s_winrate": s_winrate,
        "s_pf": s_pf, "s_avg_r": s_avg_r, "s_expectancy": s_expectancy,
        "s_vol": s_vol, "s_stability": s_stability, "s_smoothness": s_smoothness,
        "s_pf_pct": s_pf_pct, "s_mc": s_mc, "mc_beta": mc_beta, "dsr": dsr,''',
    '''        "s_sharpe": s_sharpe_dsr, "s_sortino": s_sortino, "s_winrate": s_winrate,
        "s_pf": s_pf, "s_avg_r": s_avg_r,
        "s_vol": s_vol, "s_stability": s_stability,
        "s_pf_pct": s_pf_pct, "dsr": dsr,''')

if s == original:
    print("nada mudou.")
else:
    bak = ALVO.with_suffix(".py.pre-v502")
    if not bak.exists():
        bak.write_text(original, encoding="utf-8")
        print(f"backup: {bak}")
    ALVO.write_text(s, encoding="utf-8")

print("aplicadas:", feitas or "nenhuma")
if ja:
    print("ja estavam:", ja)
if faltou:
    print("NAO CASARAM:", faltou)
    print("  O arquivo divergiu do que este patch espera. Nao confie no resultado;")
    print("  restaure o backup e me mande as linhas correspondentes.")
    sys.exit(2)
sys.exit(0)

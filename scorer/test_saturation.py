#!/usr/bin/env python3
"""
test_saturation.py — teste de aceitacao da Emenda v5.0.2 (D1 + D2 + D3).

Importa producao. Nao reimplementa nada.

Tres testes, e so o primeiro discrimina:

  A. ATINGIVEL — satura os componentes vivos e mantem smoothness em 0 e s_mc em 50,
     que e o que eles valem para todo agente real. Antes do patch isto da 88.0208;
     depois, 100.0000. E o unico teste que distingue os dois estados do scorer.

  B. ALGEBRICO — forca os onze (ou oito) componentes a 100. Da 100.0000 antes E
     depois, porque o teto algebrico de core = sum(s*w)/W_SUM ja e 100. Serve para
     conferir o clamp e a normalizacao, nao para aceitar o patch.

  C. CVAR NEGATIVO — mostra que min(cvar/2, 1)*15 nao tem limite inferior, entao
     um CVaR negativo vira bonus. Nao esta na Emenda.

Uso:
  cd /root/yaaf/scorer && python3 test_saturation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from yaaf_score_v5_formal import W, W_SUM, VERSION_SCORE, yelden_score  # producao

ESPERADO_PRE = 88.0208
ESPERADO_POS = 100.0000
TOL = 5e-4


def metricas(smoothness, s_mc, cvar_95=0.0, fator=1.0):
    """Componentes saturados (fator=1) ou parciais. smoothness e s_mc explicitos."""
    return {
        "trades": 1000,
        "sharpe_r":      2.5 * fator + (0.5 if fator == 1.0 else 0.0),
        "sortino_r":     8.0 * fator + (2.0 if fator == 1.0 else 0.0),
        "win_rate":      1.0 * fator,
        "profit_factor": 1.0 + 1.5 * fator,
        "avg_r":         1.5 * fator,
        "expectancy_r":  0.6 * fator,
        "vol_r":         2.0 * (1.0 - fator),
        "stability":     1.0 * fator,
        "smoothness":    smoothness,
        "pf_pct":        100.0 * fator,
        "s_mc":          s_mc,
        "max_dd_pct":    0.0,
        "skew":          0.0,
        "kurt":          3.0,
        "n_daily":       1000,
        "cvar_95":       cvar_95,
    }


ESTADO = {"ema": 1000.0, "total_trades": 250, "round_history": [100.0] * 8}


def rodar(m):
    # trades=None de proposito: evita o recalculo de cvar/skew das linhas 207-218
    # e satisfaz o axioma de volume sem fabricar trades sinteticos.
    return yelden_score(m, dict(ESTADO), trades=None, initial_balance=11000.0)


def peso_vivo():
    inertes = {"smoothness", "mc"}
    return sum(v for k, v in W.items() if k not in inertes)


def main():
    print(f"scorer {VERSION_SCORE}   {len(W)} componentes   W_SUM = {W_SUM:.4f}")
    print(f"pesos: {W}")
    vivo = peso_vivo()
    print(f"peso fora de smoothness e mc: {vivo:.4f}  ({100*vivo/W_SUM:.1f}% de W_SUM)\n")

    # ---------- A ----------
    a = rodar(metricas(smoothness=0.0, s_mc=50.0))
    sa = a["s_raw"]
    tem_smooth = "smoothness" in W
    tem_mc = "mc" in W
    prev = ((100.0 * vivo) + (0.0 if tem_smooth else 0.0) + (50.0 * W.get("mc", 0.0))) / W_SUM
    print("A. ATINGIVEL  (smoothness=0, s_mc=50, resto saturado)")
    print(f"   previsto pela aritmetica dos pesos: {prev:.4f}")
    print(f"   S_RAW devolvido pelo scorer:        {sa:.4f}")
    print(f"   SISTEMA {a['sistema']:.2f}   fee {a['monthly_fee_usdc']:.3f}   "
          f"stage {a['stage']}   is_eligible {a['is_eligible']}")

    if abs(sa - ESPERADO_PRE) <= TOL:
        estado = "PRE-EMENDA"
        print(f"   -> reproduz {ESPERADO_PRE:.4f}. D1 e D3 NAO aplicados.")
    elif abs(sa - ESPERADO_POS) <= TOL:
        estado = "POS-EMENDA"
        print(f"   -> {ESPERADO_POS:.4f} exato. D1+D2+D3 aplicados.")
    else:
        estado = "INESPERADO"
        print(f"   -> nem {ESPERADO_PRE:.4f} nem {ESPERADO_POS:.4f}. "
              f"O scorer esta num estado que nenhum dos dois descreve.")

    # ---------- B ----------
    b = rodar(metricas(smoothness=1.0, s_mc=100.0))
    print("\nB. ALGEBRICO  (todos os componentes a 100)")
    print(f"   S_RAW {b['s_raw']:.4f}   SISTEMA {b['sistema']:.2f}   "
          f"fee {b['monthly_fee_usdc']:.3f}")
    print(f"   {'ok' if abs(b['s_raw'] - 100.0) <= TOL else 'FALHOU'}: "
          f"o teto algebrico e 100 nos dois estados; este teste nao discrimina.")

    # ---------- C ----------
    c0 = rodar(metricas(smoothness=0.0, s_mc=50.0, cvar_95=0.0, fator=0.5))
    c1 = rodar(metricas(smoothness=0.0, s_mc=50.0, cvar_95=-4.0, fator=0.5))
    print("\nC. CVAR NEGATIVO  (mesmas metricas, cvar_95 = 0 vs -4)")
    print(f"   cvar_95 = 0.0   S_RAW {c0['s_raw']:7.4f}   cvar_pen {c0['cvar_pen']:+.4f}")
    print(f"   cvar_95 = -4.0  S_RAW {c1['s_raw']:7.4f}   cvar_pen {c1['cvar_pen']:+.4f}")
    d = c1["s_raw"] - c0["s_raw"]
    print(f"   diferenca: {d:+.4f} pontos")
    if d > TOL:
        print("   -> a penalidade de CVaR virou bonus. min(cvar/2, 1) nao tem piso;")
        print("      deveria ser clamp(cvar/2, 0, 1). Nao esta na Emenda v5.0.2.")
    else:
        print("   -> sem efeito: o CVaR esta com piso, ou o clamp final absorveu.")

    # ---------- D ----------
    print("\nD. PORTAO  (30 trades, PnL medio 2 dolares)")
    md = metricas(smoothness=0.0, s_mc=50.0, fator=0.5)
    md["trades"] = 30
    trades_pequenos = [{"pnl": 2.0, "r_multiple": 0.25,
                        "exit_time": f"2026-08-{(i % 28) + 1:02d}T12:00:00+00:00"}
                       for i in range(30)]
    d = yelden_score(md, dict(ESTADO), trades=trades_pequenos, initial_balance=11000.0)
    print(f"   S_RAW {d['s_raw']:.4f}   assessable={d.get('assessable', '(campo ausente)')}"
          f"   gate={d.get('gate', '(campo ausente)')}"
          f"   volume_ok={d.get('volume_ok', '(removido)')}")
    if d["s_raw"] > TOL:
        print("   -> avaliado. O Axioma de Volume nao esta barrando (v5.1.0).")
    else:
        print("   -> S_RAW zero. O Axioma de Volume ainda barra: media(|pnl|)=2.0 contra")
        print("      o piso de 11.0 (initial_balance 11000 x VOLUME_FLOOR_FRAC 0.001).")

    print(f"\nestado do scorer: {estado}")
    return 0 if estado == "POS-EMENDA" else (1 if estado == "PRE-EMENDA" else 2)


if __name__ == "__main__":
    sys.exit(main())

"""
Compara o scorer em producao (v5.5, 9 componentes) com o YAAF v5 corrigido
(11 componentes + 2 penalidades) sobre os mesmos dados.
"""
import math
import random
import sys

sys.path.insert(0, "/home/claude/yaaf")
import yaaf_v5


# ════════════════════════════════════════════════════════════════════════════
# Reimplementacao exata do v5.5 em producao (yelden_scorer_api.py)
# ════════════════════════════════════════════════════════════════════════════

def calc_sharpe_old(profits):
    if len(profits) < 3:
        return 0.0
    n = len(profits)
    mean = sum(profits) / n
    var = sum((p - mean) ** 2 for p in profits) / (n - 1)
    std = math.sqrt(var) if var > 0 else 0.001
    return round((mean / std) * math.sqrt(252), 4)


def calc_max_dd_old(profits, bal=10000):
    balance = peak = bal
    max_dd = 0.0
    for p in profits:
        balance += p
        if balance > peak:
            peak = balance
        if peak > 0:
            dd = (peak - balance) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 4)


def sraw_v55(profits, initial_bal=10000.0, monthly_values=None):
    """Formula do codigo em producao, verbatim."""
    n = len(profits)
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    win_rate = round(len(wins) / n * 100, 2)
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.001
    profit_factor = round(sum(wins) / abs(sum(losses)), 3) if losses else 99.0
    avg_r = round(avg_win / avg_loss, 3) if avg_loss else 0
    wr = win_rate / 100
    expectancy = round(wr * avg_r - (1 - wr), 4)
    sharpe = calc_sharpe_old(profits)

    mean_p = sum(profits) / n
    std_p = math.sqrt(sum((p - mean_p) ** 2 for p in profits) / max(n - 1, 1))
    if std_p > 0:
        skewness = sum(((p - mean_p) / std_p) ** 3 for p in profits) / n
        kurtosis = sum(((p - mean_p) / std_p) ** 4 for p in profits) / n
    else:
        skewness, kurtosis = 0.0, 3.0

    if n > 2 and std_p > 0:
        sr_var = (1 - skewness * sharpe + (kurtosis - 1) / 4 * sharpe ** 2) / max(n - 1, 1)
        z = sharpe / math.sqrt(max(sr_var, 1e-9))
        t_val = 1 / (1 + 0.2316419 * abs(z))
        poly = t_val * (0.319381530 + t_val * (-0.356563782 + t_val * (1.781477937
               + t_val * (-1.821255978 + t_val * 1.330274429))))
        dsr_raw = 1 - (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z ** 2) * poly
        if z < 0:
            dsr_raw = 1 - dsr_raw
        dsr = round(min(max(dsr_raw, 0.0), 1.0) * 100, 3)
    else:
        dsr = 50.0
    dsr_factor = min(dsr / 95.0, 1.0)

    loss_profits = [p for p in profits if p < 0]
    if len(loss_profits) >= 2:
        var_down = sum(p ** 2 for p in loss_profits) / len(loss_profits)
        sortino = round((mean_p / (math.sqrt(var_down) + 1e-9)) * math.sqrt(252), 4)
    else:
        sortino = 0.0

    max_dd = calc_max_dd_old(profits, initial_bal)
    roi = sum(profits) / initial_bal * 100 if initial_bal > 0 else 0
    calmar = round(roi / max_dd, 3) if max_dd > 0 else 0

    if monthly_values and len(monthly_values) >= 2 and initial_bal > 0:
        ms = [mv / (initial_bal * 0.01 + 1e-9) for mv in monthly_values]
        ms_mean = sum(ms) / len(ms)
        ms_std = (sum((s - ms_mean) ** 2 for s in ms) / len(ms)) ** 0.5
        stability2 = round(max(1.0 - ms_std, 0.0) ** 2 * 100, 2)
    else:
        stability2 = 50.0

    c1 = min(sharpe / 2.5, 1.0) * 100 * dsr_factor
    c2 = min(sortino / 8.0, 1.0) * 100 * min(len(loss_profits) / 20, 1.0)
    c3 = win_rate
    c4 = min((profit_factor - 1.0) / 1.5, 1.0) * 100
    c5 = min(avg_r / 1.2, 1.0) * 100
    c6 = min(expectancy / 0.5, 1.0) * 100
    c7 = max(1.0 - (max_dd / 100) / 1.0, 0) * 100
    c8 = stability2
    c9 = min(calmar / 3.0, 1.0) ** 2 * 100
    dd_penalty = max_dd * 0.25

    s_raw = (c1 * 0.18 + c2 * 0.08 + c3 * 0.12 + c4 * 0.15 + c5 * 0.08
             + c6 * 0.10 + c7 * 0.07 + c8 * 0.12 + c9 * 0.12 - dd_penalty)
    s_raw = round(max(0, min(s_raw, 100)), 2)

    cf = round(min((n / 200) ** 0.5, 1.0), 3)
    ema = 300 * 0.85 + s_raw * 10 * 0.15      # <- um unico passo, cold start 300
    sistema = round(ema * cf)

    if   sistema >= 800: stage = "LEGENDARY"
    elif sistema >= 600: stage = "ELITE"
    elif sistema >= 400: stage = "VERIFIED"
    elif sistema >= 200: stage = "PROMISING"
    else:                stage = "EXPERIMENTAL"

    return {"s_raw": s_raw, "ema": round(ema, 2), "cf": cf,
            "sistema": sistema, "stage": stage, "sharpe": round(sharpe, 2),
            "max_dd": round(max_dd, 2), "trades": n}


# ════════════════════════════════════════════════════════════════════════════
# Geradores de historico sintetico
# ════════════════════════════════════════════════════════════════════════════

def gen(n, win_rate, avg_win, avg_loss, seed, autocorr=0.0, vol=0.25):
    """Historico de trades com win rate e payoff controlados."""
    rng = random.Random(seed)
    out, prev = [], 0.0
    for _ in range(n):
        p_win = win_rate + autocorr * (1 if prev > 0 else -1) * 0.15
        p_win = max(0.02, min(p_win, 0.98))
        if rng.random() < p_win:
            v = abs(rng.gauss(avg_win, avg_win * vol))
        else:
            v = -abs(rng.gauss(avg_loss, avg_loss * vol))
        out.append(round(v, 2))
        prev = v
    return out


def as_trades(profits):
    months = ["2026-0" + str(i) for i in range(1, 10)]
    out = [{"type": "DEAL_TYPE_BALANCE", "profit": 10000.0}]
    for i, p in enumerate(profits):
        out.append({"type": "DEAL_TYPE_BUY", "profit": p,
                    "closeTime": months[i * len(months) // max(len(profits), 1)] + "-15"})
    return out


# ════════════════════════════════════════════════════════════════════════════
CASES = [
    ("Excelente — 250 trades, WR 60%, payoff 1.6", gen(250, 0.60, 160, 100, 1)),
    ("Bom — 120 trades, WR 56%, payoff 1.4",       gen(120, 0.56, 140, 100, 2)),
    ("Medio — 83 trades, WR 58.5%, payoff 1.2",    gen(83,  0.585, 120, 100, 3)),
    ("Fraco — 60 trades, WR 48%, payoff 1.05",     gen(60,  0.48, 105, 100, 4)),
    ("Martingale — autocorrelacao alta",           gen(100, 0.70, 60, 200, 5, autocorr=0.9)),
    ("Sem skill — WR 50%, payoff 1.0",             gen(100, 0.50, 100, 100, 6)),
]

print("=" * 108)
print(f"{'Caso':<44} {'v5.5 S_RAW':>10} {'v5 S_RAW':>9} {'v5.5 SIST':>10} {'v5 SIST':>8} {'v5.5 stage':>13} {'v5 stage':>13}")
print("=" * 108)

rows = []
for name, profits in CASES:
    trades = as_trades(profits)
    monthly = {}
    for t in trades:
        if t["type"] == "DEAL_TYPE_BUY":
            monthly[t["closeTime"][:7]] = monthly.get(t["closeTime"][:7], 0) + t["profit"]
    mv = list(monthly.values())

    old = sraw_v55(profits, 10000.0, mv)
    new, err = yaaf_v5.calculate_sraw(trades)
    rows.append((name, old, new))
    print(f"{name:<44} {old['s_raw']:>10.2f} {new['s_raw']:>9.2f} "
          f"{old['sistema']:>10} {new['sistema']:>8} {old['stage']:>13} {new['stage']:>13}")

print("=" * 108)
print()
print("TETO DO SISTEMA")
print("-" * 108)
perfect = [100.0] * 300
o = sraw_v55(perfect, 10000.0, [1000] * 8)
nn, _ = yaaf_v5.calculate_sraw(as_trades(perfect))
print(f"  Agente sem nenhuma perda, 300 trades:")
print(f"    v5.5 -> S_RAW {o['s_raw']:.2f}  EMA {o['ema']:.1f}  SISTEMA {o['sistema']}  ({o['stage']})")
print(f"    v5   -> S_RAW {nn['s_raw']:.2f}  EMA {nn['ema']:.1f}  SISTEMA {nn['sistema']}  ({nn['stage']})")
print(f"    isEligible() exige SISTEMA >= 400")
print()

print("COMPONENTES NOVOS (caso 'Medio — 83 trades')")
print("-" * 108)
m, _ = yaaf_v5.calculate_sraw(as_trades(CASES[2][1]))
print(f"  Pf Percentile (c10, peso 0.12) : {m['pf_percentile']:>7.2f}   % de 1000 carteiras aleatorias batidas")
print(f"  Mc Independence (c11, peso 0.07): {m['mc']:>7.2f}   (1-|rho1|)^2 x 100")
print(f"  Penalidade CVaR                 : {m['cvar_penalty']:>7.2f}   min(CVaR/2,1) x 15")
print(f"  Penalidade Max DD               : {m['dd_penalty']:>7.2f}")
print()
mart, _ = yaaf_v5.calculate_sraw(as_trades(CASES[4][1]))
print(f"  Mc no caso martingale           : {mart['mc']:>7.2f}   (deteta a dependencia serial)")
print()

print("DETERMINISMO (mesmo input -> mesmo score)")
print("-" * 108)
a, _ = yaaf_v5.calculate_sraw(as_trades(CASES[2][1]))
b, _ = yaaf_v5.calculate_sraw(as_trades(CASES[2][1]))
print(f"  duas execucoes: S_RAW {a['s_raw']} / {b['s_raw']}   SISTEMA {a['sistema']} / {b['sistema']}   "
      f"{'OK' if a == b else 'DIVERGENTE'}")
print()

print("PESOS")
print("-" * 108)
print(f"  soma dos pesos do whitepaper : {m['weight_sum']}")
print(f"  normalizacao aplicada        : {m['normalized']}")
nn2, _ = yaaf_v5.calculate_sraw(as_trades(CASES[2][1]), normalize=False)
print(f"  S_RAW com normalize=True  : {m['s_raw']:.2f}   SISTEMA {m['sistema']}")
print(f"  S_RAW com normalize=False : {nn2['s_raw']:.2f}   SISTEMA {nn2['sistema']}")

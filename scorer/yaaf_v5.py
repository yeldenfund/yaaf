"""
YAAF v5 — S_RAW de 11 componentes + 2 penalidades, conforme Whitepaper v16 secção 3.1/3.2.

Substitui calculate_sraw() do yelden_scorer_api.py v5.5, que implementava apenas
9 componentes (o comentário interno dizia "v4.1").

O que muda em relação ao v5.5 em produção:

  [NOVO]  c10 Pf Percentile  (peso 0.12) — teste de permutação contra 1000 carteiras aleatórias
  [NOVO]  c11 Mc Independence (peso 0.07) — autocorrelação lag-1 dos trades
  [NOVO]  penalidade CVaR — min(CVaR/2, 1) x 15
  [FIX]   pesos conforme whitepaper (ver WEIGHTS / NORMALIZE abaixo)
  [FIX]   CF = sqrt(n/250), era sqrt(n/200)
  [NOVO]  SF — fator de segurança, ausente no código (SISTEMA era só EMA x CF)
  [FIX]   EMA iterado sobre janelas, era um único passo a partir da constante 300
          (esse bug limitava o SISTEMA a ~405 e tornava ELITE/LEGENDARY e
           isEligible() >= 400 praticamente inalcançáveis)

Determinismo: o Pf Percentile usa RNG semeado a partir dos próprios trades, para
que o mesmo input produza sempre o mesmo score — requisito de um score auditável
que vai para on-chain.
"""

import hashlib
import math
import random

# ─── Pesos do Whitepaper v16, secção 3.1 ────────────────────────────────────
WEIGHTS = {
    "sharpe_dsr":   0.14,
    "sortino_cf":   0.07,
    "win_rate":     0.08,
    "profit_factor":0.10,
    "avg_r":        0.07,
    "expectancy":   0.09,
    "inv_vol":      0.05,
    "stability2":   0.09,
    "smoothness2":  0.08,
    "pf_percentile":0.12,
    "mc":           0.07,
}
# Nota: estes pesos somam 0.96, não 1.00 como o whitepaper afirma no texto.
# NORMALIZE=True divide pelo somatório, preservando a importância relativa
# exata e tornando S_RAW genuinamente limitado a [0, 100].
NORMALIZE = True

# Fee model — Whitepaper v16, seccao 5.1: monthly_fee = base_rate x (1000-SISTEMA)/1000
# Documentado no whitepaper e AUSENTE do scorer v5.5. Implementado aqui.
FEE_BASE_RATE_USDC = 10.0

# Pisos de stake por banda. O v5.5 denominava em YLD (stake_floors + s_min_yld),
# o que contradiz "No native token" do whitepaper — a seccao 4.1 diz que o stake
# e' colateral em USDC. Os valores sao os mesmos do v5.5, apenas redenominados;
# o whitepaper nao especifica pisos, entao estes precisam de confirmacao.
STAKE_FLOORS_USDC = {
    "EXPERIMENTAL": 50, "PROMISING": 200, "VERIFIED": 500,
    "ELITE": 1000, "LEGENDARY": 2000,
}
SAFETY = {
    "EXPERIMENTAL": 2.0, "PROMISING": 1.75, "VERIFIED": 1.50,
    "ELITE": 1.25, "LEGENDARY": 1.0,
}

MIN_TRADES = 5
N_WINDOWS = 8          # janelas para EMA e SF (whitepaper: "last 8 S_RAW")
N_PERMUTATIONS = 1000  # whitepaper: "% of 1,000 random portfolios beaten"
CVAR_TAIL = 0.05       # cauda de 5%

TRADE_TYPES = {"DEAL_TYPE_BUY", "DEAL_TYPE_SELL"}


# ════════════════════════════════════════════════════════════════════════════
# Métricas base
# ════════════════════════════════════════════════════════════════════════════

def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs, ddof=1):
    n = len(xs)
    if n <= ddof:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - ddof))


def calc_sharpe(profits):
    if len(profits) < 3:
        return 0.0
    s = _std(profits)
    if s <= 0:
        return 0.0
    return (_mean(profits) / s) * math.sqrt(252)


def calc_max_dd(profits, bal=10000.0):
    balance = peak = bal
    max_dd = 0.0
    for p in profits:
        balance += p
        peak = max(peak, balance)
        if peak > 0:
            max_dd = max(max_dd, (peak - balance) / peak * 100)
    return max_dd


def calc_dsr(profits, sharpe):
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014), em %."""
    n = len(profits)
    s = _std(profits)
    if n <= 2 or s <= 0:
        return 50.0
    m = _mean(profits)
    skew = sum(((p - m) / s) ** 3 for p in profits) / n
    kurt = sum(((p - m) / s) ** 4 for p in profits) / n
    sr_var = (1 - skew * sharpe + (kurt - 1) / 4 * sharpe ** 2) / max(n - 1, 1)
    z = sharpe / math.sqrt(max(sr_var, 1e-9))
    # aproximação de Abramowitz-Stegun para a normal acumulada
    t = 1 / (1 + 0.2316419 * abs(z))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937
           + t * (-1.821255978 + t * 1.330274429))))
    cdf = 1 - (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z ** 2) * poly
    if z < 0:
        cdf = 1 - cdf
    return min(max(cdf, 0.0), 1.0) * 100


# ════════════════════════════════════════════════════════════════════════════
# Componentes novos (ausentes no v5.5)
# ════════════════════════════════════════════════════════════════════════════

def calc_pf_percentile(profits, n_perm=N_PERMUTATIONS, seed=None):
    """
    c10 — "% of 1,000 random portfolios beaten".

    Modelo nulo: um operador SEM skill que usa exatamente o mesmo dimensionamento
    de posição. Mantemos as magnitudes |P&L| e atribuímos sinais aleatórios com
    p=0.5, gerando 1000 carteiras de referência. O percentil do Profit Factor
    real contra essa distribuição mede se o padrão de ganhos/perdas bate o
    cara-ou-coroa com as mesmas apostas.

    (Embaralhar a ordem dos trades não serviria: o PF é invariante a permutação,
     pois é soma de ganhos sobre soma de perdas.)
    """
    mags = [abs(p) for p in profits if p != 0]
    if len(mags) < MIN_TRADES:
        return 50.0

    def pf(vals):
        w = sum(v for v in vals if v > 0)
        l = abs(sum(v for v in vals if v < 0))
        if l == 0:
            return 99.0
        return w / l

    actual = pf(profits)
    rng = random.Random(seed)
    beaten = 0
    for _ in range(n_perm):
        sim = [m if rng.random() < 0.5 else -m for m in mags]
        if actual > pf(sim):
            beaten += 1
    return beaten / n_perm * 100


def calc_mc_independence(profits):
    """
    c11 — Mc (Independence): (1 - |beta|)^2 x 100.

    beta lido como a autocorrelação de lag-1 da série de P&L por trade. Mede se
    os resultados são serialmente independentes; autocorrelação alta indica
    dependência de regime ou martingale/grid disfarçado.
    """
    n = len(profits)
    if n < 3:
        return 50.0
    m = _mean(profits)
    den = sum((p - m) ** 2 for p in profits)
    if den <= 0:
        return 50.0
    num = sum((profits[i] - m) * (profits[i + 1] - m) for i in range(n - 1))
    rho1 = max(min(num / den, 1.0), -1.0)
    return (1 - abs(rho1)) ** 2 * 100


def calc_cvar_penalty(profits):
    """
    Penalidade CVaR — min(CVaR/2, 1) x 15.

    CVaR = média da cauda de 5% pior, normalizada pelo GANHO MÉDIO. Lê-se:
    "quanto do ganho típico o pior 5% destrói". CVaR = 2 significa que cada
    evento de cauda apaga dois ganhos médios, e satura a penalidade em 15.

    Normalizar pela PERDA média (primeira tentativa) não funcionou: para
    qualquer distribuição de P&L aproximadamente simétrica, a cauda de 5% fica
    sempre entre 1.5x e 2.2x a perda média, então a penalidade virava um
    desconto constante de ~10.5 pontos em todos os agentes, em vez de
    discriminar. Contra o ganho médio a razão varia de verdade entre agentes.
    """
    n = len(profits)
    if n < MIN_TRADES:
        return 0.0
    wins = [p for p in profits if p > 0]
    unit = _mean(wins) if wins else 0.0
    if unit <= 0:
        return 15.0          # sem ganho nenhum: penalidade máxima
    r = sorted(p / unit for p in profits)
    k = max(1, int(math.ceil(n * CVAR_TAIL)))
    cvar = -_mean(r[:k])          # positivo quando a cauda é de perdas
    if cvar <= 0:
        return 0.0
    return min(cvar / 2, 1.0) * 15


# ════════════════════════════════════════════════════════════════════════════
# S_RAW
# ════════════════════════════════════════════════════════════════════════════

def compute_sraw(profits, initial_bal=10000.0, monthly_values=None, seed=None,
                 normalize=NORMALIZE):
    """Devolve (s_raw, dict de componentes). profits = lista de P&L por trade."""
    n = len(profits)
    if n < MIN_TRADES:
        return None, None

    wins   = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    win_rate = len(wins) / n
    avg_win  = _mean(wins) if wins else 0.0
    avg_loss = abs(_mean(losses)) if losses else 0.001
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else 99.0
    avg_r = (avg_win / avg_loss) if avg_loss else 0.0
    expectancy = win_rate * avg_r - (1 - win_rate)

    sharpe = calc_sharpe(profits)
    dsr = calc_dsr(profits, sharpe)
    dsr_factor = min(dsr / 95.0, 1.0)

    if len(losses) >= 2:
        var_down = sum(p ** 2 for p in losses) / len(losses)
        sortino = (_mean(profits) / (math.sqrt(var_down) + 1e-9)) * math.sqrt(252)
    else:
        sortino = 0.0

    max_dd = calc_max_dd(profits, initial_bal)
    roi = sum(profits) / initial_bal * 100 if initial_bal > 0 else 0.0
    calmar = (roi / max_dd) if max_dd > 0 else 0.0

    # Stability² — dispersão do Sharpe mensal
    if monthly_values and len(monthly_values) >= 2:
        ms = [mv / (initial_bal * 0.01 + 1e-9) for mv in monthly_values]
        stability2 = (1 / (1 + _std(ms, ddof=0))) ** 2 * 100
    else:
        stability2 = 50.0

    # ── 11 componentes ──
    c = {
        "sharpe_dsr":    min(sharpe / 2.5, 1.0) * 100 * dsr_factor,
        "sortino_cf":    min(sortino / 8.0, 1.0) * 100 * min(len(losses) / 20, 1.0),
        "win_rate":      win_rate * 100,
        "profit_factor": min((profit_factor - 1.0) / 1.5, 1.0) * 100,
        "avg_r":         min(avg_r / 1.5, 1.0) * 100,
        "expectancy":    min(max(expectancy, 0) / 0.6, 1.0) * 100,
        "inv_vol":       max(1 - (max_dd / 100) / 2, 0) * 100,
        "stability2":    stability2,
        "smoothness2":   min(calmar / 4.0, 1.0) ** 2 * 100,
        "pf_percentile": calc_pf_percentile(profits, seed=seed),
        "mc":            calc_mc_independence(profits),
    }
    for k in c:
        c[k] = max(0.0, min(c[k], 100.0))

    wsum = sum(WEIGHTS.values())
    scale = (1.0 / wsum) if normalize else 1.0
    positive = sum(c[k] * WEIGHTS[k] * scale for k in WEIGHTS)

    cvar_pen = calc_cvar_penalty(profits)
    dd_pen = max_dd * 0.25

    s_raw = max(0.0, min(positive - cvar_pen - dd_pen, 100.0))

    diag = dict(c)
    diag.update({
        "_positive_before_penalties": round(positive, 2),
        "_cvar_penalty": round(cvar_pen, 2),
        "_dd_penalty": round(dd_pen, 2),
        "_weight_sum": round(wsum, 4),
        "_normalized": normalize,
        "sharpe": sharpe, "sortino": sortino, "dsr": dsr,
        "max_dd": max_dd, "calmar": calmar, "profit_factor": profit_factor,
        "win_rate": win_rate * 100, "avg_r": avg_r, "expectancy": expectancy,
    })
    return round(s_raw, 2), diag


# ════════════════════════════════════════════════════════════════════════════
# SISTEMA = EMA x CF x SF
# ════════════════════════════════════════════════════════════════════════════

def compute_sistema(profits, initial_bal=10000.0, monthly_values=None, seed=None,
                    normalize=NORMALIZE):
    """
    SISTEMA(t) = EMA(t) x CF(t) x SF(t), em [0, 1000].

    O v5.5 fazia `ema = 300*0.85 + s_raw*10*0.15` — um único passo a partir de
    uma constante, o que travava o EMA em no máximo 405 e, por consequência, o
    SISTEMA. Aqui o EMA é iterado sobre janelas sequenciais do histórico, como a
    recorrência do whitepaper pede, e converge para S_RAW x 10.

    SF precisa dos "últimos 8 S_RAW". Como /score-preview é stateless, as 8
    janelas sequenciais do próprio histórico servem de série temporal.
    """
    n = len(profits)
    if n < MIN_TRADES:
        return None, None

    s_raw, diag = compute_sraw(profits, initial_bal, monthly_values, seed, normalize)
    if s_raw is None:
        return None, None

    # Série de S_RAW por rodada de scoring.
    #
    # ATENÇÃO à leitura de "last 8 S_RAW" do whitepaper: são as 8 últimas
    # RODADAS, e cada rodada pontua o histórico ACUMULADO até ali. Usar 8 fatias
    # disjuntas seria errado — cada fatia teria n/8 trades (~15 num histórico de
    # 120), o S_RAW dessas fatias é ruído, sigma passa de 25 e o SF colapsa para
    # zero mesmo em agentes bons. Janelas cumulativas reproduzem o que as
    # rodadas reais teriam produzido à medida que o agente acumulou trades, e aí
    # a dispersão mede instabilidade de trajetória, que é o que o SF quer punir.
    # O aquecimento (primeiros trades) e' descartado: com poucos trades o S_RAW
    # e' ruido, e esse ruido dominava o sigma do SF, punindo qualquer agente que
    # tivesse comecado pequeno -- inclusive os que melhoraram de forma monotona.
    per_window = []
    if n >= MIN_TRADES * 2:
        warmup = n // 2 if n >= MIN_TRADES * 4 else 0
        span = n - warmup
        for i in range(1, N_WINDOWS + 1):
            cut = max(MIN_TRADES, warmup + round(span * i / N_WINDOWS))
            if cut > n:
                break
            sw, _ = compute_sraw(profits[:cut], initial_bal, None, seed, normalize)
            if sw is not None:
                per_window.append(sw)
    if not per_window:
        per_window = [s_raw]
    per_window = per_window[-N_WINDOWS:]

    # EMA iterado (whitepaper: EMA(t) = 0.85*EMA(t-1) + 0.15*S_RAW*10)
    ema = per_window[0] * 10
    for sw in per_window[1:]:
        ema = 0.85 * ema + 0.15 * sw * 10
    ema = 0.85 * ema + 0.15 * s_raw * 10
    ema = max(0.0, min(ema, 1000.0))

    # CF — confiança, cheia em 250 trades (whitepaper), era 200 no código
    cf = min(math.sqrt(n / 250), 1.0)

    # SF — min(mean(last 8 S_RAW)/45, 1) * (1 - sigma_s/25)
    sf = min(_mean(per_window) / 45, 1.0) * (1 - _std(per_window, ddof=0) / 25)
    sf = max(0.0, min(sf, 1.0))

    sistema = round(ema * cf * sf)

    if   sistema >= 800: stage = "LEGENDARY"
    elif sistema >= 600: stage = "ELITE"
    elif sistema >= 400: stage = "VERIFIED"
    elif sistema >= 200: stage = "PROMISING"
    else:                stage = "EXPERIMENTAL"

    diag.update({
        "s_raw": s_raw, "ema": round(ema, 2), "cf": round(cf, 4),
        "sf": round(sf, 4), "sistema": sistema, "stage": stage,
        "per_window_sraw": [round(x, 2) for x in per_window],
        "trades": n,
    })
    return sistema, diag


# ════════════════════════════════════════════════════════════════════════════
# Entrada compatível com o scorer em produção
# ════════════════════════════════════════════════════════════════════════════

def calculate_sraw(trades_list, bal=10000.0, normalize=NORMALIZE):
    """Drop-in para a função homónima do yelden_scorer_api.py."""
    closed = [t for t in trades_list
              if t.get("type") in TRADE_TYPES and t.get("profit") is not None]
    if len(closed) < MIN_TRADES:
        return None, f"Apenas {len(closed)} trades reais"

    profits = [float(t["profit"]) for t in closed]

    bal_trades = [t for t in trades_list if t.get("type") == "DEAL_TYPE_BALANCE"]
    initial_bal = sum(float(t["profit"]) for t in bal_trades) if bal_trades else bal
    if initial_bal <= 0:
        initial_bal = bal

    monthly = {}
    for t in closed:
        ts = t.get("closeTime") or t.get("openTime") or ""
        key = ts[:7] if len(ts) >= 7 else "unknown"
        monthly[key] = monthly.get(key, 0) + float(t["profit"])
    monthly_values = [v for k, v in monthly.items() if k != "unknown"]

    # semente determinística: mesmo histórico -> mesmo score, sempre
    seed = int(hashlib.sha256(
        ",".join(f"{p:.8f}" for p in profits).encode()
    ).hexdigest()[:16], 16)

    sistema, d = compute_sistema(profits, initial_bal, monthly_values, seed, normalize)
    if sistema is None:
        return None, "dados insuficientes"

    # Volume Axiom — gate duro, mantido do v5.5
    avg_abs = _mean([abs(p) for p in profits])
    volume_ok = avg_abs >= initial_bal * 0.001
    if not volume_ok:
        d["s_raw"] = 0.0
        d["sistema"] = 0
        d["stage"] = "EXPERIMENTAL"
        sistema = 0

    monthly_return = (_mean(monthly_values) / initial_bal * 100) if monthly_values and initial_bal > 0 else 0.0

    wr = d["win_rate"] / 100
    kelly_f = (wr - (1 - wr) / d["avg_r"]) if d["avg_r"] > 0 else 0.0
    kelly_scale = 0.25 if len(profits) < 50 else (0.33 if len(profits) < 100 else 0.50)
    kelly_alloc = round(max(kelly_f, 0) * kelly_scale * d["cf"] * 100000)

    # Fee mensal — whitepaper 5.1. SISTEMA 1000 -> 0 USDC (excelencia e' gratis)
    monthly_fee = round(FEE_BASE_RATE_USDC * (1000 - d["sistema"]) / 1000, 2)

    # Stake minimo em USDC
    stage_now = d["stage"]
    mdd_factor = 0.40 - 0.25 * (d["s_raw"] / 100)
    s_min_usdc = round(max(STAKE_FLOORS_USDC[stage_now],
                           kelly_alloc * mdd_factor * SAFETY[stage_now]))

    # isEligible() — whitepaper 4.4: SISTEMA >= 400 e tier high/medium
    is_eligible = d["sistema"] >= 400

    return {
        "s_raw":          d["s_raw"],
        "sistema":        d["sistema"],
        "ema":            d["ema"],
        "cf":             d["cf"],
        "sf":             d["sf"],
        "stage":          d["stage"],
        "trades":         d["trades"],
        "win_rate":       round(d["win_rate"], 2),
        "profit_factor":  round(d["profit_factor"], 3),
        "sharpe":         round(d["sharpe"], 2),
        "sortino":        round(d["sortino"], 2),
        "max_dd":         round(d["max_dd"], 2),
        "calmar":         round(d["calmar"], 2),
        "avg_r":          round(d["avg_r"], 3),
        "expectancy":     round(d["expectancy"], 4),
        "dsr":            round(d["dsr"], 3),
        "pf_percentile":  round(d["pf_percentile"], 2),
        "mc":             round(d["mc"], 2),
        "cvar_penalty":   d["_cvar_penalty"],
        "dd_penalty":     d["_dd_penalty"],
        "stability2":     round(d["stability2"], 2),
        "monthly_return": round(monthly_return, 2),
        "total_profit":   round(sum(profits), 2),
        "kelly_f":        round(kelly_f, 4),
        "kelly_alloc":    kelly_alloc,
        "initial_bal":    round(initial_bal, 2),
        "roi":            round(sum(profits) / initial_bal * 100, 2),
        "volume_flag":    "OK" if volume_ok else "FLAGGED",
        "monthly_fee_usdc": monthly_fee,
        "s_min_usdc":     s_min_usdc,
        "is_eligible":    is_eligible,
        "components":     {k: round(d[k], 2) for k in WEIGHTS},
        "weights":        dict(WEIGHTS),
        "weight_sum":     d["_weight_sum"],
        "normalized":     d["_normalized"],
    }, None

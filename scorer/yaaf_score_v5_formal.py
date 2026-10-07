#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YAAF S_RAW v5.0 + SISTEMA v2.0 — Formal Scoring Engine
=======================================================
Normative implementation of the specification:
  YAAF_SRAW_v5_SISTEMA_v2_Formal_Spec.pdf
"""
from __future__ import annotations
import hashlib
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

VERSION_SCORE = "5.0.0-FORMAL"

W = {
    "sharpe_dsr": 0.14, "sortino": 0.07, "winrate": 0.08, "pf": 0.10,
    "avg_r": 0.07, "expectancy": 0.09, "vol": 0.05, "stability": 0.09,
    "smoothness": 0.08, "pf_pct": 0.12, "mc": 0.07,
}
# A tabela do spec soma 0.96, nao 1.00 como o texto normativo afirma.
# A soma ponderada e dividida por W_SUM para que S_RAW use a faixa [0,100]
# declarada, preservando a importancia relativa calibrada. Ver Emenda v5.0.1.
W_SUM = sum(W.values())

CAP_SHARPE   = 2.5
CAP_SORTINO  = 8.0
CAP_PF       = 2.5
CAP_AVG_R    = 1.5
CAP_EXPECT   = 0.6
CAP_VOL_R    = 2.0
CAP_CALMAR   = 4.0

# Fee model — Whitepaper v16, secção 5.1
FEE_BASE_RATE_USDC = 10.0
STAKE_FLOORS_USDC = {
    "EXPERIMENTAL": 50, "PROMISING": 200, "VERIFIED": 500,
    "ELITE": 1000, "LEGENDARY": 2000,
}

CVAR_PEN_SCALE = 15.0
CVAR_CAP       = 2.0
DD_PEN_WEIGHT  = 0.20

EMA_ALPHA      = 0.85
EMA_INITIAL    = 300.0
CF_N_STAR      = 250
SF_WINDOW      = 8
SF_LEVEL_REF   = 45.0
SF_DISP_REF    = 25.0

MIN_TRADES_SRAW = 30
VOLUME_FLOOR_FRAC = 0.001

PF_PCT_N_SIM = 1000
PF_PCT_CLIP  = 50.0


def finite(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def stage(score):
    if score < 200:  return "EXPERIMENTAL"
    if score < 400:  return "PROMISING"
    if score < 600:  return "VERIFIED"
    if score < 800:  return "ELITE"
    return "LEGENDARY"


def volume_axiom_ok(trades, initial_balance, floor_frac=VOLUME_FLOOR_FRAC):
    if not trades or initial_balance <= 0:
        return False
    abs_pnls = [abs(finite(t.get("pnl", 0.0))) for t in trades]
    if not abs_pnls:
        return False
    return float(np.mean(abs_pnls)) >= initial_balance * floor_frac


def compute_dsr(sharpe, n_obs, skew=0.0, kurt=3.0, n_trials=1):
    sr = finite(sharpe)
    T = max(int(n_obs), 2)
    skew = finite(skew)
    kurt = max(finite(kurt, 3.0), 1.0)
    inner = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    inner = max(inner, 1e-12)
    sigma_sr0 = math.sqrt(inner / (T - 1))
    if sigma_sr0 < 1e-12:
        return 1.0 if sr > 0 else 0.0
    z = sr / sigma_sr0
    if n_trials > 1:
        z = z - math.sqrt(2.0 * math.log(max(n_trials, 1)))
    dsr = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return clamp(dsr, 0.0, 1.0)


def compute_cvar(r_multiples, alpha=0.95):
    r = np.asarray([finite(x) for x in r_multiples], dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 5:
        return 0.0
    losses = -r
    var = float(np.quantile(losses, alpha))
    tail = losses[losses >= var]
    if len(tail) == 0:
        return max(var, 0.0)
    return float(np.mean(tail))


def compute_pf_percentil(trades, n_sim=PF_PCT_N_SIM, seed=42):
    if not trades or len(trades) < 3:
        return 0.0
    r_arr = np.array([finite(t.get("r_multiple", 0.0)) for t in trades], dtype=float)
    r_arr = r_arr[np.isfinite(r_arr)]
    if len(r_arr) < 3:
        return 0.0
    m = float(np.mean(r_arr))
    s = float(np.std(r_arr, ddof=0))
    if s < 1e-12:
        return 100.0 if m > 0 else 0.0
    real_sharpe = m / s * math.sqrt(252)
    if abs(real_sharpe) > PF_PCT_CLIP:
        return 0.0 if real_sharpe < 0 else 100.0
    rng = np.random.default_rng(seed)
    rand_r = rng.normal(0.0, s, (n_sim, len(r_arr)))
    rand_means = rand_r.mean(axis=1)
    rand_stds = rand_r.std(axis=1, ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rand_sharpes = np.where(rand_stds > 1e-12, rand_means / rand_stds * math.sqrt(252), 0.0)
    pf_pct = float(np.mean(rand_sharpes < real_sharpe) * 100.0)
    return clamp(pf_pct, 0.0, 100.0)


def compute_market_correlation(trades, df_market):
    if not trades or df_market is None or len(df_market) < 10:
        return 0.0, 50.0
    try:
        import pandas as pd
        d = pd.DataFrame(trades)
        d["date"] = pd.to_datetime(d["exit_time"]).dt.date
        daily_r = d.groupby("date")["r_multiple"].sum()
        daily_r = daily_r[np.isfinite(daily_r)]
        if len(daily_r) < 5:
            return 0.0, 100.0
        mkt = df_market.copy()
        mkt["date"] = pd.to_datetime(mkt["datetime"]).dt.date
        mkt = mkt.groupby("date")["close"].last()
        mkt_ret = mkt.pct_change().dropna()
        common = daily_r.index.intersection(mkt_ret.index)
        if len(common) < 5:
            return 0.0, 100.0
        r_aligned = daily_r.reindex(common).values.astype(float)
        mkt_aligned = mkt_ret.reindex(common).values.astype(float)
        mask = np.isfinite(r_aligned) & np.isfinite(mkt_aligned)
        if mask.sum() < 5:
            return 0.0, 100.0
        corr = float(np.corrcoef(r_aligned[mask], mkt_aligned[mask])[0, 1])
        if not np.isfinite(corr):
            corr = 0.0
        corr = clamp(corr, -1.0, 1.0)
        s_mc = (1.0 - abs(corr)) ** 2 * 100.0
        return corr, clamp(s_mc, 0.0, 100.0)
    except Exception:
        return 0.0, 50.0


def yelden_score(metrics, state, trades=None, initial_balance=11000.0, n_trials=1):
    n_trades = int(metrics.get("trades", 0))
    if n_trades < MIN_TRADES_SRAW:
        vol_ok = False
    else:
        vol_ok = True
        if trades is not None:
            vol_ok = volume_axiom_ok(trades, initial_balance)

    sharpe    = finite(metrics.get("sharpe_r"))
    sortino   = finite(metrics.get("sortino_r"))
    win_rate  = finite(metrics.get("win_rate"))
    pf        = finite(metrics.get("profit_factor"))
    avg_r     = finite(metrics.get("avg_r"))
    exp_r     = finite(metrics.get("expectancy_r"))
    vol_r     = finite(metrics.get("vol_r"))
    stability = clamp(finite(metrics.get("stability"), 0.5), 0.0, 1.0)
    smoothness= clamp(finite(metrics.get("smoothness")), 0.0, 1.0)
    max_dd    = max(finite(metrics.get("max_dd_pct")), 0.0)
    pf_pct    = clamp(finite(metrics.get("pf_pct"), 50.0), 0.0, 100.0)
    s_mc_val  = clamp(finite(metrics.get("s_mc"), 50.0), 0.0, 100.0)
    mc_beta   = finite(metrics.get("mc_beta"), 0.0)

    skew = finite(metrics.get("skew"), 0.0)
    kurt = finite(metrics.get("kurt"), 3.0)
    n_daily = int(metrics.get("n_daily", max(n_trades, 2)))
    cvar_95 = finite(metrics.get("cvar_95"), 0.0)

    if trades is not None and (cvar_95 <= 0 or abs(skew) < 1e-12):
        r_arr = [finite(t.get("r_multiple", 0.0)) for t in trades]
        if len(r_arr) >= 5:
            r_np = np.asarray(r_arr, dtype=float)
            r_np = r_np[np.isfinite(r_np)]
            if len(r_np) >= 5:
                if abs(skew) < 1e-12:
                    skew = float(np.mean(((r_np - r_np.mean()) / (r_np.std() + 1e-12)) ** 3))
                if abs(kurt - 3.0) < 1e-12:
                    kurt = float(np.mean(((r_np - r_np.mean()) / (r_np.std() + 1e-12)) ** 4))
                if cvar_95 <= 0:
                    cvar_95 = compute_cvar(r_np, alpha=0.95)

    dsr = compute_dsr(sharpe, n_obs=n_daily, skew=skew, kurt=kurt, n_trials=n_trials)

    s_sharpe_dsr = clamp(max(sharpe, 0.0) / CAP_SHARPE, 0.0, 1.0) * 100.0 * dsr
    s_sortino    = clamp(max(sortino, 0.0) / CAP_SORTINO, 0.0, 1.0) * 100.0
    s_winrate    = clamp(win_rate, 0.0, 1.0) * 100.0
    s_pf         = clamp(max(pf - 1.0, 0.0) / (CAP_PF - 1.0), 0.0, 1.0) * 100.0
    s_avg_r      = clamp(avg_r / CAP_AVG_R, 0.0, 1.0) * 100.0
    s_expectancy = clamp(max(exp_r, 0.0) / CAP_EXPECT, 0.0, 1.0) * 100.0
    s_vol        = clamp(1.0 - vol_r / CAP_VOL_R, 0.0, 1.0) * 100.0
    s_stability  = (stability ** 2) * 100.0
    s_smoothness = (smoothness ** 2) * 100.0
    s_pf_pct     = pf_pct
    s_mc         = s_mc_val

    cvar_pen = min(cvar_95 / CVAR_CAP, 1.0) * CVAR_PEN_SCALE
    dd_pen   = max_dd * DD_PEN_WEIGHT

    if n_trades >= MIN_TRADES_SRAW and vol_ok:
        core = (
            s_sharpe_dsr * W["sharpe_dsr"] + s_sortino * W["sortino"]
            + s_winrate * W["winrate"] + s_pf * W["pf"]
            + s_avg_r * W["avg_r"] + s_expectancy * W["expectancy"]
            + s_vol * W["vol"] + s_stability * W["stability"]
            + s_smoothness * W["smoothness"] + s_pf_pct * W["pf_pct"]
            + s_mc * W["mc"]
        ) / W_SUM
        s_raw = clamp(core - cvar_pen - dd_pen, 0.0, 100.0)
    else:
        s_raw = 0.0

    ema_prev = finite(state.get("ema"), EMA_INITIAL)
    ema_new  = clamp(ema_prev * EMA_ALPHA + (s_raw * 10.0) * (1.0 - EMA_ALPHA), 0.0, 1000.0)

    cum_trades = int(state.get("total_trades", 0)) + n_trades
    cf = min(math.sqrt(max(cum_trades, 0) / CF_N_STAR), 1.0)

    history = list(state.get("round_history", []))
    history.append(float(s_raw))
    window = history[-SF_WINDOW:]
    if window:
        s_bar = float(np.mean(window))
        s_std = float(np.std(window, ddof=0)) if len(window) > 1 else 0.0
        level = min(s_bar / SF_LEVEL_REF, 1.0)
        disp  = max(1.0 - s_std / SF_DISP_REF, 0.0)
        sf = clamp(level * disp, 0.0, 1.0)
    else:
        sf = clamp(s_raw / SF_LEVEL_REF, 0.0, 1.0)

    sistema = clamp(ema_new * cf * sf, 0.0, 1000.0)

    # Fee model — Whitepaper v16
    monthly_fee = round(FEE_BASE_RATE_USDC * (1000 - sistema) / 1000, 2)
    stage_name = stage(sistema)
    s_min_usdc = STAKE_FLOORS_USDC.get(stage_name, 50)
    is_eligible = sistema >= 400

    return {
        "monthly_fee_usdc": monthly_fee,
        "s_min_usdc": s_min_usdc,
        "is_eligible": is_eligible,
        "s_sharpe": s_sharpe_dsr, "s_sortino": s_sortino, "s_winrate": s_winrate,
        "s_pf": s_pf, "s_avg_r": s_avg_r, "s_expectancy": s_expectancy,
        "s_vol": s_vol, "s_stability": s_stability, "s_smoothness": s_smoothness,
        "s_pf_pct": s_pf_pct, "s_mc": s_mc, "mc_beta": mc_beta, "dsr": dsr,
        "cvar_95": cvar_95, "cvar_pen": cvar_pen, "dd_penalty": dd_pen,
        "volume_ok": vol_ok, "s_raw": s_raw, "ema_prev": ema_prev, "ema_new": ema_new,
        "cf": cf, "sf": sf, "sistema": sistema, "stage": stage_name,
        "score_version": VERSION_SCORE,
        "new_state": {
            "ema": ema_new, "round_history": window,
            "total_trades": cum_trades, "last_s_raw": s_raw, "last_sistema": sistema,
        },
    }


def enrich_metrics_from_trades(metrics, trades):
    out = dict(metrics)
    if not trades or len(trades) < 5:
        return out
    r_arr = np.array([finite(t.get("r_multiple", 0.0)) for t in trades], dtype=float)
    r_arr = r_arr[np.isfinite(r_arr)]
    if len(r_arr) < 5:
        return out
    std = float(r_arr.std()) + 1e-12
    centered = (r_arr - r_arr.mean()) / std
    out["skew"] = float(np.mean(centered ** 3))
    out["kurt"] = float(np.mean(centered ** 4))
    out["cvar_95"] = compute_cvar(r_arr, alpha=0.95)
    try:
        import pandas as pd
        dates = pd.to_datetime([t["exit_time"] for t in trades if "exit_time" in t]).date
        out["n_daily"] = max(len(set(dates)), 2)
    except Exception:
        out["n_daily"] = max(len(r_arr), 2)
    out["pf_pct"] = compute_pf_percentil(trades)
    return out

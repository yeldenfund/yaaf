#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ic_test_gmx.py — medicao de IC do YAAF v5.0 no GMX V2.

Implementa docs/IC_PROTOCOL.md v1. Nao modificar sem emitir nova versao do
protocolo: o numero so tem procedencia enquanto o script corresponder ao
documento congelado.

Principio de desenho: este script NAO reimplementa a construcao de metricas.
Ele importa `compute_yaf_metrics` do proprio coletor de producao
(feed_yaaf_gmx.py) e `enrich_metrics_from_trades` do scorer. Assim o IC mede
o mesmo caminho de codigo que produz os scores publicados, por construcao e
nao por coincidencia.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OBS_DIR = Path("/root/aiagentregistry-observatory")
SCORER_DIR = Path("/root/yaaf/scorer")
for p in (str(OBS_DIR), str(SCORER_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from feed_yaaf_gmx import compute_yaf_metrics            # noqa: E402
from yaaf_score_v5_formal import (                        # noqa: E402
    yelden_score, enrich_metrics_from_trades, VERSION_SCORE,
)

PAYLOAD_DIR = OBS_DIR / "yaaf_payloads_gmx"
OUT_PATH = Path("docs/evidence/ic_test_gmx_result.json")

MIN_TRADES_T1 = 30          # spec formal §2.2 — nao ajustavel
MIN_TRADES_T2 = 10
INITIAL_BALANCE = 11000.0   # identico ao emit_yaaf_gmx.py


# ── estatistica, sem dependencia de scipy ───────────────────────────────────

def _ranks(v):
    """Postos com media em caso de empate."""
    n = len(v)
    order = sorted(range(n), key=lambda i: v[i])
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[order[j + 1]] == v[order[i]]:
            j += 1
        media = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = media
        i = j + 1
    return r


def _pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0.0


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def spearman(x, y):
    """Devolve (rho, p, ic95_lo, ic95_hi) usando a transformada de Fisher.

    p e intervalo vem do mesmo metodo (Fisher), de modo que sao mutuamente
    consistentes — reportar p de um teste e IC de outro produz combinacoes
    que podem parecer contraditorias na fronteira.
    """
    n = len(x)
    rho = _pearson(_ranks(x), _ranks(y))
    if n < 4 or abs(rho) >= 1.0:
        return rho, None, None, None
    z = math.atanh(rho)
    se = 1.0 / math.sqrt(n - 3)
    p = 2.0 * (1.0 - _phi(abs(z) / se))
    return rho, p, math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)


# ── carga ───────────────────────────────────────────────────────────────────

def load_payloads():
    out = []
    for f in sorted(PAYLOAD_DIR.glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("trades"), list):
            out.append(d)
    return out


def sraw_from(trades):
    """S_RAW pelo caminho de producao: compute_yaf_metrics -> enrich -> score."""
    metrics = compute_yaf_metrics(trades)
    if not metrics.get("trades"):
        return None
    metrics = enrich_metrics_from_trades(metrics, trades)
    state = {"ema": 300.0, "round_history": [], "total_trades": 0}
    try:
        res = yelden_score(metrics=metrics, state=state, trades=trades,
                           initial_balance=INITIAL_BALANCE)
    except Exception:
        return None
    return res.get("s_raw") if res else None


def main():
    payloads = load_payloads()
    print(f"payloads carregados: {len(payloads)}")

    todos_ts = [t["exit_time"] for p in payloads for t in p["trades"]
                if t.get("exit_time") is not None]
    if not todos_ts:
        print("nenhum exit_time encontrado"); return
    corte = float(np.median(todos_ts))
    corte_data = datetime.fromtimestamp(corte, tz=timezone.utc)
    print(f"mediana GLOBAL de exit_time: {corte_data.isoformat()}")

    obs, descartes = [], {"sem_trades": 0, "t1_curto": 0, "t2_curto": 0, "sraw_nulo": 0}
    for p in payloads:
        trades = [t for t in p["trades"] if t.get("exit_time") is not None]
        if not trades:
            descartes["sem_trades"] += 1; continue
        t1 = [t for t in trades if t["exit_time"] < corte]
        t2 = [t for t in trades if t["exit_time"] >= corte]
        if len(t1) < MIN_TRADES_T1:
            descartes["t1_curto"] += 1; continue
        if len(t2) < MIN_TRADES_T2:
            descartes["t2_curto"] += 1; continue
        s = sraw_from(t1)
        if s is None:
            descartes["sraw_nulo"] += 1; continue
        rs = [float(t.get("r_multiple", 0.0)) for t in t2]
        rs = [v for v in rs if math.isfinite(v)]
        pn = [float(t.get("pnl", 0.0)) for t in t2]
        pn = [v for v in pn if math.isfinite(v)]
        obs.append({
            "agent": p.get("agent_id", "?"),
            "n_t1": len(t1), "n_t2": len(t2),
            "sraw_t1": float(s),
            "sum_r_t2": float(sum(rs)),
            "mean_r_t2": float(sum(rs) / len(rs)) if rs else 0.0,
            "sum_pnl_t2": float(sum(pn)),
        })

    n = len(obs)
    print(f"descartes: {descartes}")
    print(f"agentes com T1 e T2 validos: {n}")
    if n < 10:
        print("amostra pequena demais para reportar"); return

    s = [o["sraw_t1"] for o in obs]
    alvos = [("primario_soma_r", [o["sum_r_t2"] for o in obs]),
             ("secundario_media_r", [o["mean_r_t2"] for o in obs]),
             ("terciario_pnl_abs", [o["sum_pnl_t2"] for o in obs])]

    resultados = {}
    for nome, alvo in alvos:
        rho, p, lo, hi = spearman(s, alvo)
        resultados[nome] = {"rho": rho, "p": p, "ic95_lo": lo, "ic95_hi": hi, "n": n}
        ic = f"[{lo:.4f}, {hi:.4f}]" if lo is not None else "—"
        pp = f"{p:.4f}" if p is not None else "—"
        print(f"  {nome:22} rho={rho:+.4f}  p={pp}  IC95% {ic}  n={n}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "protocolo": "IC_PROTOCOL.md v1",
        "scorer": str(SCORER_DIR / "yaaf_score_v5_formal.py"),
        "scorer_version": VERSION_SCORE,
        "metricas_de": str(OBS_DIR / "feed_yaaf_gmx.py") + "::compute_yaf_metrics",
        "initial_balance": INITIAL_BALANCE,
        "rodado_em": datetime.now(timezone.utc).isoformat(),
        "corte_exit_time": corte,
        "corte_data": corte_data.isoformat(),
        "min_trades_t1": MIN_TRADES_T1,
        "min_trades_t2": MIN_TRADES_T2,
        "descartes": descartes,
        "resultados": resultados,
        "observacoes": obs,
    }, indent=2, default=str))
    print(f"\n[ok] {OUT_PATH}")


if __name__ == "__main__":
    main()

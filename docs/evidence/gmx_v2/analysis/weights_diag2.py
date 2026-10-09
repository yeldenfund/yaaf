import json, sys
import numpy as np
from scipy import stats
W0 = {"s_sharpe": .14, "s_sortino": .07, "s_winrate": .08, "s_pf": .10,
      "s_avg_r": .07, "s_expectancy": .09, "s_vol": .05, "s_stability": .09,
      "s_smoothness": .08, "s_pf_pct": .12, "s_mc": .07}
W1 = {"s_sharpe": .14, "s_sortino": .07, "s_winrate": .08, "s_pf": .10,
      "s_avg_r": .16, "s_vol": .05, "s_stability": .09, "s_pf_pct": .12}
obs = json.load(open(sys.argv[1], encoding="utf-8"))["observacoes"]
col = lambda c: np.array([float(o[c]) for o in obs])
pen = col("cvar_pen") + col("dd_penalty")
S = col("s_raw")

def raw(W, mean=False):
    M = np.column_stack([col(c) for c in W]); w = np.array(list(W.values()))
    core = M.mean(axis=1) if mean else M @ w / w.sum()
    return np.clip(core - pen, 0, 100)

R = raw(W0)
live = S > 0                       # S_RAW publicado e predito de T1, nao e desfecho
zerados = (S == 0) & (R > 1)
err = np.abs(R - S)[live].max()
print(f"n={len(obs)}  S_RAW>0: {live.sum()}  zerados pelo else: {zerados.sum()}")
print(f"guard (so S_RAW>0): max erro = {err:.6f}")
if err > 1e-3:
    print("ABORTADO: nao reproduz nem nos agentes vivos."); sys.exit(1)

# o ramo else vale igual para qualquer vetor de pesos: aplica-se o mesmo zero
mask = ~zerados
A = np.where(mask, raw(W1), 0.0)
B = np.where(mask, raw(W1, mean=True), 0.0)
k = len(obs) // 4
print(f"\nTodos os 152 (zerados mantidos em 0 nos dois):")
print(f"  rho(Emenda, igual)         = {stats.spearmanr(A, B)[0]:+.4f}")
print(f"  quartil superior em comum  = {len(set(np.argsort(-A)[:k]) & set(np.argsort(-B)[:k]))}/{k}")
print(f"Somente os {mask.sum()} nao zerados:")
print(f"  rho(Emenda, igual)         = {stats.spearmanr(A[mask], B[mask])[0]:+.4f}")
print("\nlimiar em S_RAW (indicador; S_RAW 50 <-> SISTEMA 500 so com EMA convergida):")
for lim in (40, 50, 60):
    a, b = A >= lim, B >= lim
    print(f"  >= {lim}: Emenda {a.sum():>3}  igual {b.sum():>3}  divergem em {(a != b).sum():>3}")
print("\nressalva: usa s_* gravados (cap atual de avg_r), nao o cap 1.5 da Emenda, sem D7.")

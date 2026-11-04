"""Deterministic formula search for loop v3: greedy forward selection (OMP).

Terms are f(v) * T_k with v a named scalar input (I1, I2, features) and f from a fixed
family per input: v, v^2, tanh and Gaussian windows at the 20/50/80 % train quantiles,
and products of each non-invariant input with I1 and I2. Fitted by least squares on the
training flows only, over the 6 independent anisotropy components. Same construction as
scratch/control2_features.py, so loop v3 and the controls differ only in their inputs.
"""
from __future__ import annotations

import numpy as np
import sympy as sp

IU = [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]
W6 = np.array([1, 1, 1, np.sqrt(2), np.sqrt(2), np.sqrt(2)])


def fmt(x: float) -> str:
    return f"({x:.4g})" if x < 0 else f"{x:.4g}"


def dictionary(V: dict[str, np.ndarray], names: list[str]) -> list[tuple[str, object, str]]:
    """(text, f(D), input name) per scalar term, windows placed on the train data ``V``."""
    feats = [("1", lambda D: np.ones(len(D["I1"])), "")]
    for v in names:
        x = V[v]
        feats.append((v, lambda D, v=v: D[v], v))
        feats.append((f"{v}**2", lambda D, v=v: D[v] ** 2, v))
        spread = float(np.quantile(x, 0.9) - np.quantile(x, 0.1)) or 1e-3
        for c in np.quantile(x, [0.2, 0.5, 0.8]):
            s_t, s_g = 2.0 / spread, 4.0 / spread ** 2
            feats.append((f"tanh({fmt(s_t)}*({v} - {fmt(c)}))",
                          lambda D, v=v, c=c, s=s_t: np.tanh(s * (D[v] - c)), v))
            feats.append((f"exp({fmt(-s_g)}*({v} - {fmt(c)})**2)",
                          lambda D, v=v, c=c, s=s_g: np.exp(-s * (D[v] - c) ** 2), v))
    for v in names:
        if v not in ("I1", "I2"):
            for inv in ("I1", "I2"):
                feats.append((f"{inv}*{v}", lambda D, v=v, inv=inv: D[inv] * D[v], v))
    return feats


def design(feats, D, T):
    Tv = np.stack([T[:, :, i, j] for i, j in IU], axis=2) * W6
    F = np.stack([f(D) for _, f, _ in feats], 1)
    return np.einsum("nj,nkc->ncjk", F, Tv).reshape(len(T) * 6, len(feats) * 3), F


def vec(y):
    return (np.stack([y[:, i, j] for i, j in IU], 1) * W6).reshape(-1)


def formula(feats, sel, coef) -> str:
    by_k: dict[int, list[str]] = {}
    for (j, k), c in zip(sel, coef):
        by_k.setdefault(k, []).append(fmt(c) if feats[j][0] == "1" else f"{fmt(c)}*{feats[j][0]}")
    return " + ".join(f"({' + '.join(t)})*T{k + 1}" for k, t in sorted(by_k.items()))


def node_count(text: str, names: list[str]) -> int:
    syms = {n: sp.Symbol(n) for n in ("I1", "I2", "T1", "T2", "T3", *names)}
    expr = sp.sympify(text, locals={**syms, "tanh": sp.tanh, "exp": sp.exp}, evaluate=False)
    return sum(1 for _ in sp.preorder_traversal(expr))


def predict(F, T, sel, coef):
    out = np.zeros((len(T), 3, 3))
    for (j, k), c in zip(sel, coef):
        out += c * F[:, j, None, None] * T[:, k]
    return out


def ratio(p, y) -> float:
    return float(np.mean((p - y) ** 2) / np.mean(y ** 2))


def search(names, train, max_nodes: int, max_terms: int = 40) -> dict:
    """Largest OMP formula within ``max_nodes``; train = (D, T, y)."""
    D, T, y = train
    feats = dictionary(D, names)
    X, F = design(feats, D, T)
    r = vec(y)
    norms = np.linalg.norm(X, axis=0) + 1e-30
    sel_cols, resid, best = [], r.copy(), None
    for _ in range(max_terms):
        score = np.abs(X.T @ resid) / norms
        score[sel_cols] = -1
        trial = sel_cols + [int(np.argmax(score))]
        coef, *_ = np.linalg.lstsq(X[:, trial], r, rcond=None)
        sel = [(c // 3, c % 3) for c in trial]
        text = formula(feats, sel, coef)
        n = node_count(text, names)
        if n > max_nodes:
            break
        sel_cols, resid = trial, r - X[:, trial] @ coef
        best = {"feats": feats, "sel": sel, "coef": coef, "formula": text, "nodes": n,
                "uses": [feats[j][2] for j, _ in sel]}
    return best


def score(model: dict, cases: dict) -> dict[str, float]:
    """Ratio per case; cases = {case_id: (D, T, y)}."""
    out = {}
    for c, (D, T, y) in cases.items():
        F = np.stack([f(D) for _, f, _ in model["feats"]], 1)
        out[c] = ratio(predict(F, T, model["sel"], model["coef"]), y)
    return out

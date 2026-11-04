"""Control 2 (exploratory, frozen, no API): deterministic search with and without standard features.

Same greedy forward selection (OMP) as scratch/medium_formulas.py on the main branch, but the
dictionary is built the same way for every input variable, so the two arms differ only in inputs:
  arm "invariants": I1, I2
  arm "standard":   I1, I2 + the 10 standard features of flowforge.data.features
Fit on the data-v3 train split only (3000 points per case, seed 0); curved_step scored like the
repo scorer (4000 points, seed 0); held-out redteam cases reported too. Node counts are SymPy
preorder counts, as in the DSL parser. Output: runs/arms/control2-features-2026-11-03.json.
"""
import json
from pathlib import Path

import numpy as np
import sympy as sp

from flowforge.data.features import STANDARD, load_features
from flowforge.data.frozen_fields import load_frozen_fields, redteam_case_ids, train_case_ids
from flowforge.physics.tensors import is_realizable

IU = [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]
W6 = np.array([1, 1, 1, np.sqrt(2), np.sqrt(2), np.sqrt(2)])
BUDGETS = (25, 40, 60, 100)


def load(cases, n):
    inv, basis, y, brans = load_frozen_fields(cases, max_points_per_case=n, seed=0, return_b_rans=True)
    f = load_features(cases, max_points_per_case=n, seed=0)
    V = {"I1": inv["I1"], "I2": inv["I2"], **f}
    T = np.stack([basis[f"T{k}"] for k in (1, 2, 3)], 1)
    y, brans = np.asarray(y, float), np.asarray(brans, float)
    m = (np.isfinite(T).reshape(len(T), -1).all(1) & np.isfinite(y).reshape(len(y), -1).all(1)
         & np.all([np.isfinite(v) for v in V.values()], axis=0))
    return {k: v[m] for k, v in V.items()}, T[m], y[m], brans[m]


def fmt(x):
    return f"({x:.4g})" if x < 0 else f"{x:.4g}"


def dictionary(V, names):
    """(text, values) per scalar feature: v, v^2, tanh and Gaussian windows, products with I1, I2."""
    feats = [("1", lambda D: np.ones(len(D["I1"])))]
    for v in names:
        x = V[v]
        feats.append((v, lambda D, v=v: D[v]))
        feats.append((f"{v}**2", lambda D, v=v: D[v] ** 2))
        spread = float(np.quantile(x, 0.9) - np.quantile(x, 0.1)) or 1e-3
        for c in np.quantile(x, [0.2, 0.5, 0.8]):
            s_t, s_g = 2.0 / spread, 4.0 / spread ** 2
            feats.append((f"tanh({fmt(s_t)}*({v} - {fmt(c)}))", lambda D, v=v, c=c, s=s_t: np.tanh(s * (D[v] - c))))
            feats.append((f"exp({fmt(-s_g)}*({v} - {fmt(c)})**2)", lambda D, v=v, c=c, s=s_g: np.exp(-s * (D[v] - c) ** 2)))
    for v in names:
        if v not in ("I1", "I2"):
            for inv in ("I1", "I2"):
                feats.append((f"{inv}*{v}", lambda D, v=v, inv=inv: D[inv] * D[v]))
    return feats


def design(feats, D, T):
    Tv = np.stack([T[:, :, i, j] for i, j in IU], axis=2) * W6  # (N, 3, 6)
    F = np.stack([f(D) for _, f in feats], 1)
    return np.einsum("nj,nkc->ncjk", F, Tv).reshape(len(T) * 6, len(feats) * 3), F


def vec(y):
    return (np.stack([y[:, i, j] for i, j in IU], 1) * W6).reshape(-1)


def nodes(feats, sel, coef):
    by_k = {}
    for (j, k), c in zip(sel, coef):
        by_k.setdefault(k, []).append(fmt(c) if feats[j][0] == "1" else f"{fmt(c)}*{feats[j][0]}")
    text = " + ".join(f"({' + '.join(t)})*T{k + 1}" for k, t in sorted(by_k.items()))
    syms = {n: sp.Symbol(n) for n in ("I1", "I2", "T1", "T2", "T3", *STANDARD)}
    expr = sp.sympify(text, locals={**syms, "tanh": sp.tanh, "exp": sp.exp}, evaluate=False)
    return sum(1 for _ in sp.preorder_traversal(expr)), text


def pred_tensor(F, T, sel, coef):
    out = np.zeros((len(T), 3, 3))
    for (j, k), c in zip(sel, coef):
        out += c * F[:, j, None, None] * T[:, k]
    return out


def ratio(p, y):
    return float(np.mean((p - y) ** 2) / np.mean(y ** 2))


def run_arm(names, train, heldout, max_terms=40):
    Dt, Tt, yt, bt = train
    feats = dictionary(Dt, names)
    Xt, Ft = design(feats, Dt, Tt)
    rt = vec(yt)
    norms = np.linalg.norm(Xt, axis=0) + 1e-30
    held = {c: (design(feats, D, T)[1], T, y, b) for c, (D, T, y, b) in heldout.items()}
    sel_cols, curve, resid = [], [], rt.copy()
    for step in range(1, max_terms + 1):
        score = np.abs(Xt.T @ resid) / norms
        score[sel_cols] = -1
        sel_cols.append(int(np.argmax(score)))
        coef, *_ = np.linalg.lstsq(Xt[:, sel_cols], rt, rcond=None)
        resid = rt - Xt[:, sel_cols] @ coef
        sel = [(c // 3, c % 3) for c in sel_cols]
        n_nodes, text = nodes(feats, sel, coef)
        row = {"terms": step, "nodes": n_nodes, "train": float(np.mean(resid ** 2) / np.mean(rt ** 2)), "expression": text}
        for c, (F, T, y, b) in held.items():
            p = pred_tensor(F, T, sel, coef)
            row[c] = ratio(p, y)
            row[f"{c}_realizable"] = float(np.mean(is_realizable(b + p)))
        row["train_realizable"] = float(np.mean(is_realizable(bt + pred_tensor(Ft, Tt, sel, coef))))
        curve.append(row)
    return curve


def main():
    train = load(train_case_ids(), 3000)
    heldout = {c: load([c], 4000) for c in ["curved_step", *redteam_case_ids()]}
    out = {"label": "exploratory", "mode": "frozen", "fit": "train only (data v3, 3000/case)", "arms": {}}
    for arm, names in (("invariants", ["I1", "I2"]), ("standard", ["I1", "I2", *STANDARD])):
        curve = run_arm(names, train, heldout)
        out["arms"][arm] = curve
        print(f"== {arm}")
        for b in BUDGETS:
            fit = [r for r in curve if r["nodes"] <= b]
            if fit:
                r = fit[-1]
                rt = " ".join(f"{c[:12]}={r[c]:.3f}" for c in heldout if c != "curved_step")
                print(f"  <= {b:3d} nodes ({r['terms']:2d} terms, {r['nodes']}): curved_step {r['curved_step']:.3f} "
                      f"(realizable {r['curved_step_realizable']:.3f}, train {r['train_realizable']:.3f}) | {rt}")
    Path("runs/arms").mkdir(parents=True, exist_ok=True)
    json.dump(out, open("runs/arms/control2-features-2026-11-03.json", "w"), indent=2, default=float)


if __name__ == "__main__":
    main()

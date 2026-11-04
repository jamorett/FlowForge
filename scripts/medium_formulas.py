"""Do medium-size closed-form formulas capture the ceiling headroom? (exploratory, frozen, no API)

Greedy forward selection (OMP) of grammar-expressible terms f(I1, I2) * T_k, fitted on the
data-v3 train split only, never on validation. After each added term the formula is written
in the DSL, its node count taken from the repo parser (cap lifted for this probe only), and
curved_step scored. Checkpoints are re-scored with the repo scorer and checked for
realizability. Output: runs/arms/medium-formulas-2026-11-03.json.
"""
import json

import numpy as np

from flowforge.data.frozen_fields import load_frozen_fields, score_on_cases, train_case_ids
from flowforge.dsl import parser as dsl_parser
from flowforge.dsl.evaluate import candidate_anisotropy
from flowforge.ladder.ladder import _realizability

dsl_parser.MAX_NODES = 10_000  # probe only: measure size, do not enforce the 25-node cap

TRAIN = train_case_ids()


def load(cases, n):
    inv, basis, y, brans = load_frozen_fields(cases, max_points_per_case=n, seed=0, return_b_rans=True)
    I = np.stack([inv["I1"], inv["I2"]], 1)
    T = np.stack([basis[f"T{k}"] for k in (1, 2, 3)], 1)
    y, brans = np.asarray(y, float), np.asarray(brans, float)
    m = np.isfinite(I).all(1) & np.isfinite(T).reshape(len(T), -1).all(1) & np.isfinite(y).reshape(len(y), -1).all(1)
    return I[m], T[m], y[m], brans[m], inv, basis


def fmt(x):
    return f"({x:.6g})" if x < 0 else f"{x:.6g}"


def dictionary(I_train):
    """(name, dsl_text, numpy f(I1, I2)) for grammar-expressible scalar features."""
    feats = [("1", "1", lambda a, b: np.ones_like(a))]
    for p in range(0, 4):
        for q in range(0, 4 - p):
            if p + q:
                txt = " * ".join(["I1"] * p + ["I2"] * q)
                feats.append((txt, txt, lambda a, b, p=p, q=q: a ** p * b ** q))
    for var, col in (("I1", 0), ("I2", 1)):
        x = I_train[:, col]
        qs = np.quantile(x, [0.1, 0.3, 0.5, 0.7, 0.9])
        spread = float(np.quantile(x, 0.9) - np.quantile(x, 0.1)) or 1e-3
        for c in qs:
            for w in (0.25, 0.5, 1.0):
                width = w * spread
                s_t = 1.0 / width
                s_g = 1.0 / width ** 2
                feats.append((f"tanh[{var},{c:.3g},{w}]", f"tanh({fmt(s_t)} * ({var} - {fmt(c)}))",
                              lambda a, b, col=col, c=c, s=s_t: np.tanh(s * ((a, b)[col] - c))))
                feats.append((f"gauss[{var},{c:.3g},{w}]", f"exp({fmt(-s_g)} * ({var} - {fmt(c)}) ** 2)",
                              lambda a, b, col=col, c=c, s=s_g: np.exp(-s * ((a, b)[col] - c) ** 2)))
        for d in (0.01, 0.03, 0.1, 0.3):
            feats.append((f"div[{var},{d}]", f"div(1, {d} + {var})",
                          lambda a, b, col=col, d=d: 1.0 / ((d + (a, b)[col]) ** 2 + 1e-4)))
    q1 = np.quantile(I_train[:, 0], [0.2, 0.5, 0.8])
    q2 = np.quantile(I_train[:, 1], [0.2, 0.5, 0.8])
    s1 = 1.0 / (0.5 * (np.quantile(I_train[:, 0], 0.9) - np.quantile(I_train[:, 0], 0.1))) ** 2
    s2 = 1.0 / (0.5 * (np.quantile(I_train[:, 1], 0.9) - np.quantile(I_train[:, 1], 0.1))) ** 2
    for c1 in q1:
        for c2 in q2:
            feats.append((f"gauss2[{c1:.3g},{c2:.3g}]",
                          f"exp({fmt(-s1)} * (I1 - {fmt(c1)}) ** 2 + {fmt(-s2)} * (I2 - {fmt(c2)}) ** 2)",
                          lambda a, b, c1=c1, c2=c2: np.exp(-s1 * (a - c1) ** 2 - s2 * (b - c2) ** 2)))
    return feats


def columns(feats, I, T):
    """Design matrix over the 6 independent components (off-diagonals weighted sqrt(2))."""
    iu = [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]
    w = np.array([1, 1, 1, np.sqrt(2), np.sqrt(2), np.sqrt(2)])
    Tv = np.stack([T[:, :, i, j] for i, j in iu], axis=2) * w  # (N, 3, 6)
    F = np.stack([f(I[:, 0], I[:, 1]) for _, _, f in feats], 1)  # (N, J)
    X = np.einsum("nj,nkc->ncjk", F, Tv).reshape(len(I) * 6, len(feats) * 3)
    return X, Tv, w, iu


def target_vec(y, w, iu):
    return (np.stack([y[:, i, j] for i, j in iu], 1) * w).reshape(-1)


def expression(feats, sel, coef):
    by_k = {1: [], 2: [], 3: []}
    for (j, k), c in zip(sel, coef):
        txt = feats[j][1]
        by_k[k + 1].append(fmt(c) if txt == "1" else f"{fmt(c)} * {txt}")
    return " + ".join(f"({' + '.join(t)}) * T{k}" for k, t in by_k.items() if t)


def main():
    It, Tt, yt, bt, _, _ = load(TRAIN, 3000)
    feats = dictionary(It)
    Xt, _, w, iu = columns(feats, It, Tt)
    rt = target_vec(yt, w, iu)
    norms = np.linalg.norm(Xt, axis=0) + 1e-30
    Iv, Tv_, yv, bv, _, _ = load(["curved_step"], 4000)
    Xv, _, _, _ = columns(feats, Iv, Tv_)
    rv = target_vec(yv, w, iu)
    print(f"train rows {len(It)}, features {len(feats)} x 3 tensors")

    sel_cols, curve = [], []
    resid = rt.copy()
    for step in range(1, 41):
        score = np.abs(Xt.T @ resid) / norms
        score[sel_cols] = -1
        sel_cols.append(int(np.argmax(score)))
        A = Xt[:, sel_cols]
        coef, *_ = np.linalg.lstsq(A, rt, rcond=None)
        resid = rt - A @ coef
        val = float(np.mean((rv - Xv[:, sel_cols] @ coef) ** 2) / np.mean(rv ** 2))
        trn = float(np.mean(resid ** 2) / np.mean(rt ** 2))
        sel = [(c // 3, c % 3) for c in sel_cols]
        expr = expression(feats, sel, coef)
        nodes = dsl_parser.complexity(dsl_parser.validate_candidate(expr)) if hasattr(dsl_parser, "complexity") else None
        curve.append({"terms": step, "nodes": nodes, "train_ratio_6c": trn, "curved_step_ratio_6c": val, "expression": expr})
        print(f"terms {step:2d}  nodes {nodes}  train {trn:.3f}  curved_step {val:.3f}")

    checks = []
    for row in curve:
        if row["terms"] in (3, 5, 8, 10, 15, 20, 30, 40):
            ex = row["expression"]
            try:
                repo = score_on_cases(ex, ["curved_step"])["curved_step"]["ratio"]
                inv, basis, _, brans = load_frozen_fields(TRAIN, max_points_per_case=4000, seed=0, return_b_rans=True)
                ok_train = _realizability(candidate_anisotropy(ex, inv, basis), brans)
                inv, basis, _, brans = load_frozen_fields(["curved_step"], max_points_per_case=4000, seed=0, return_b_rans=True)
                ok_val = _realizability(candidate_anisotropy(ex, inv, basis), brans)
            except AssertionError as exc:
                checks.append({"terms": row["terms"], "nodes": row["nodes"], "error": str(exc)})
                continue
            checks.append({"terms": row["terms"], "nodes": row["nodes"], "curved_step_repo": repo,
                           "realizable_train": ok_train, "realizable_curved_step": ok_val})
            print(f"check terms {row['terms']}: repo curved_step {repo:.3f}, realizable train {ok_train[1]:.3f} "
                  f"curved_step {ok_val[1]:.3f}")
    json.dump({"label": "exploratory", "mode": "frozen", "fit": "train only (data v3, 3000/case)",
               "curve": curve, "checks": checks},
              open("runs/arms/medium-formulas-2026-11-03.json", "w"), indent=2, default=float)


if __name__ == "__main__":
    main()

"""Ceiling of the closure form on curved_step (exploratory, frozen, no API, no locked data).

Asks: how low can worst_validation_ratio go for ANY model of the form
sum_k g_k(...) * T_k, regardless of who proposes it?

  P0  pointwise projection of the curved_step target onto span(T1..T3) (and T1..T4):
      the absolute ceiling of the tensor form, any inputs, fitted on validation itself.
  P1  best g(I1, I2) fitted on curved_step itself (kNN local least squares): ceiling
      of the form with the two invariants the grammar allows.
  P2  best g(I1, I2) learned from the train split only: kNN and a large ridge library
      (polynomials, tanh, exp, rational in I1, I2), alpha chosen by leave-one-family-out.

Realizability is ignored, so every number is an optimistic bound. Ratio = MSE / MSE(zero
correction), same as flowforge.data.frozen_fields.score_expression.
Output: runs/arms/ceiling-2026-11-03.json.
"""
import json
import os

import numpy as np
from scipy.spatial import cKDTree

from flowforge.data.frozen_fields import (
    load_frozen_fields, score_on_cases, train_case_ids, validation_case_ids,
)
from flowforge.dsl.evaluate import candidate_anisotropy

VAL = validation_case_ids()
assert VAL == ["curved_step"], VAL
TRAIN = train_case_ids()
FAMILY = {c: ("hill" if "hill" in c else "bump" if "bump" in c else "plate") for c in TRAIN}
EPS = 1e-4


def load(cases, n, seed=0):
    inv, basis, target = load_frozen_fields(cases, max_points_per_case=n, seed=seed)
    I = np.stack([inv["I1"], inv["I2"]], axis=1)
    T = np.stack([basis[f"T{k}"] for k in (1, 2, 3, 4)], axis=1)  # (N, 4, 3, 3)
    return I, T, np.asarray(target, float)


def ratio(pred, target):
    """Scorer ratio on rows with a finite target (non-finite predictions count as 0)."""
    m = np.isfinite(target).reshape(len(target), -1).all(axis=1)
    p = np.nan_to_num(pred[m], nan=0.0, posinf=0.0, neginf=0.0)
    return float(np.mean((p - target[m]) ** 2) / np.mean(target[m] ** 2))


def usable(I, T, target):
    return (np.isfinite(I).all(axis=1) & np.isfinite(T).reshape(len(T), -1).all(axis=1)
            & np.isfinite(target).reshape(len(target), -1).all(axis=1))


def normal_terms(T, target, k):
    """Per point G[a,b] = <T_a, T_b>, h[a] = <T_a, target> over the first k tensors."""
    Tk = T[:, :k]
    return np.einsum("naij,nbij->nab", Tk, Tk), np.einsum("naij,nij->na", Tk, target)


def apply(g, T):
    return np.einsum("na,naij->nij", g, T[:, :g.shape[1]])


def solve(G, h, lam=1e-8):
    k = G.shape[-1]
    scale = np.trace(G, axis1=-2, axis2=-1)[..., None, None] / k + 1e-30
    return np.linalg.solve(G + lam * scale * np.eye(k), h[..., None])[..., 0]


def zfeat(I, ref):
    z = np.log(np.abs(I) + EPS)
    return (z - ref[0]) / ref[1]


def knn_g(I_fit, G_fit, h_fit, I_query, K, ref, exclude_self=False):
    tree = cKDTree(zfeat(I_fit, ref))
    _, idx = tree.query(zfeat(I_query, ref), k=K + int(exclude_self))
    if exclude_self:
        idx = idx[:, 1:]
    return solve(G_fit[idx].sum(axis=1), h_fit[idx].sum(axis=1), lam=1e-6)


def library(I):
    """Scalar features phi_j(I1, I2): the grammar's function families, many scales."""
    x, y = I[:, 0], I[:, 1]
    cols = [np.ones_like(x)]
    for a in range(0, 5):
        for b in range(0, 5 - a):
            if a + b:
                cols.append((x / 0.05) ** a * (y / 0.05) ** b)
    for s in (2.0, 10.0, 50.0, 200.0):
        cols += [np.tanh(s * x), np.tanh(s * y), np.exp(-s * x), np.exp(-s * y)]
    for d in (0.01, 0.05, 0.2, 1.0):
        cols += [d / (d + x), d / (d + y)]
    return np.stack(cols, axis=1)


def ridge_fit(I, G, h, lam):
    Phi = library(I)
    mu, sd = Phi[:, 1:].mean(0), Phi[:, 1:].std(0) + 1e-12
    Phi = np.concatenate([Phi[:, :1], (Phi[:, 1:] - mu) / sd], axis=1)
    J, k = Phi.shape[1], G.shape[1]
    A = np.einsum("nj,nm,nab->jamb", Phi, Phi, G).reshape(J * k, J * k)
    r = np.einsum("nj,na->ja", Phi, h).reshape(J * k)
    W = np.linalg.solve(A + lam * np.trace(A) / (J * k) * np.eye(J * k), r).reshape(J, k)
    return W, mu, sd


def ridge_pred(model, I, T):
    W, mu, sd = model
    Phi = library(I)
    Phi = np.concatenate([Phi[:, :1], (Phi[:, 1:] - mu) / sd], axis=1)
    return apply(Phi @ W, T)


out = {"label": "exploratory", "mode": "frozen", "validation": VAL, "train": TRAIN,
       "note": "realizability ignored: optimistic bounds", "results": {}}
R = out["results"]

# Validation exactly as the scorer loads it (4000 points, seed 0).
Iv, Tv, yv = load(VAL, 4000, seed=0)
mv = usable(Iv, Tv, yv)
print(f"curved_step: {len(yv)} points, {mv.sum()} usable")

# Sanity: our ratio matches the repo scorer for a known champion.
sparse_v3 = "3.765 * T3 + (-3.491) * tanh(I1) * T3 + 3.277 * tanh(I1) * T2 + (-2.974) * T2"
ours = ratio(candidate_anisotropy(sparse_v3, {"I1": Iv[:, 0], "I2": Iv[:, 1], **{f"I{i}": np.zeros(len(Iv)) for i in (3, 4, 5)}},
                                  {f"T{k}": Tv[:, k - 1] for k in (1, 2, 3, 4)}), yv)
repo = score_on_cases(sparse_v3, VAL)["curved_step"]["ratio"]
print(f"sanity sparse_v3: ours {ours:.4f} repo {repo:.4f}")
assert abs(ours - repo) < 1e-6
R["sanity_sparse_v3"] = repo

# P0: pointwise projection (any g, any inputs) on curved_step itself.
for k in (3, 4):
    G, h = normal_terms(Tv[mv], yv[mv], k)
    pred = np.zeros_like(yv)
    pred[mv] = apply(solve(G, h), Tv[mv])
    R[f"P0_pointwise_T1..T{k}"] = ratio(pred, yv)

# P1: best g(I1, I2) fitted on curved_step itself (leave-self-out kNN).
ref_v = (np.log(np.abs(Iv[mv]) + EPS).mean(0), np.log(np.abs(Iv[mv]) + EPS).std(0))
Gv, hv = normal_terms(Tv[mv], yv[mv], 3)
for K in (10, 50, 200, 1000):
    pred = np.zeros_like(yv)
    pred[mv] = apply(knn_g(Iv[mv], Gv, hv, Iv[mv], K, ref_v, exclude_self=True), Tv[mv])
    R[f"P1_insample_knn_K{K}"] = ratio(pred, yv)
for lam in (1e-8, 1e-6, 1e-4):
    pred = np.zeros_like(yv)
    pred[mv] = ridge_pred(ridge_fit(Iv[mv], Gv, hv, lam), Iv[mv], Tv[mv])
    R[f"P1_insample_library_lam{lam:g}"] = ratio(pred, yv)
pred = np.zeros_like(yv)
pred[mv] = apply(np.broadcast_to(solve(Gv.sum(0), hv.sum(0)), (mv.sum(), 3)), Tv[mv])
R["P1_insample_constant_g"] = ratio(pred, yv)

# P2: learned from train only (more points than the swarm used: 20000 per case).
It, Tt, yt = load(TRAIN, 20000, seed=0)
mt = usable(It, Tt, yt)
fam = np.concatenate([[FAMILY[c]] * n for c, n in
                      ((c, len(load([c], 20000, seed=0)[2])) for c in TRAIN)])
It, Tt, yt, fam = It[mt], Tt[mt], yt[mt], fam[mt]
Gt, ht = normal_terms(Tt, yt, 3)
ref_t = (np.log(np.abs(It) + EPS).mean(0), np.log(np.abs(It) + EPS).std(0))
print(f"train: {len(yt)} usable points, families {dict(zip(*np.unique(fam, return_counts=True)))}")

pred = np.zeros_like(yv)
pred[mv] = apply(np.broadcast_to(solve(Gt.sum(0), ht.sum(0)), (mv.sum(), 3)), Tv[mv])
R["P2_train_constant_g"] = ratio(pred, yv)
for K in (50, 200, 1000, 5000):
    pred = np.zeros_like(yv)
    pred[mv] = apply(knn_g(It, Gt, ht, Iv[mv], K, ref_t), Tv[mv])
    R[f"P2_train_knn_K{K}"] = ratio(pred, yv)

cv = {}
for lam in (1e-8, 1e-6, 1e-4, 1e-2):
    scores = []
    for f in ("hill", "bump", "plate"):
        tr, te = fam != f, fam == f
        model = ridge_fit(It[tr], Gt[tr], ht[tr], lam)
        scores.append(ratio(ridge_pred(model, It[te], Tt[te]), yt[te]))
    cv[lam] = float(np.mean(scores))
    pred = np.zeros_like(yv)
    pred[mv] = ridge_pred(ridge_fit(It, Gt, ht, lam), Iv[mv], Tv[mv])
    R[f"P2_train_library_lam{lam:g}"] = ratio(pred, yv)
best_lam = min(cv, key=cv.get)
R["P2_train_library_cv_choice"] = {"lam": best_lam, "cv_mean_ratio": cv,
                                   "curved_step": R[f"P2_train_library_lam{best_lam:g}"]}

R["reference"] = {"sparse_v3_best_seed": 0.733, "sparse_v3_seed_mean": 0.748,
                  "loop_v2_v3_best_seed": 0.688, "loop_v2_seed_mean_range": [0.850, 0.869]}

os.makedirs("runs/arms", exist_ok=True)
json.dump(out, open("runs/arms/ceiling-2026-11-03.json", "w"), indent=2, default=float)
for k, v in R.items():
    print(f"{k}: {v if not isinstance(v, float) else round(v, 4)}")

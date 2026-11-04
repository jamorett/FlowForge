"""Train-kNN ceiling on curved_step with realizability enforced by per-point shrinkage."""
import json
import numpy as np
from flowforge.data.frozen_fields import load_frozen_fields
from flowforge.physics.tensors import is_realizable

exec(open("scripts/ceiling.py", encoding="utf-8").read().split("out = {")[0])
It, Tt, yt = load(TRAIN, 20000, seed=0)
mt = usable(It, Tt, yt); It, Tt, yt = It[mt], Tt[mt], yt[mt]
Gt, ht = normal_terms(Tt, yt, 3)
ref_t = (np.log(np.abs(It) + EPS).mean(0), np.log(np.abs(It) + EPS).std(0))
inv, basis, y, brans = load_frozen_fields(["curved_step"], max_points_per_case=4000, seed=0, return_b_rans=True)
I = np.stack([inv["I1"], inv["I2"]], 1); T = np.stack([basis[f"T{k}"] for k in (1, 2, 3, 4)], 1)
y, brans = np.asarray(y, float), np.asarray(brans, float)
out = {}
for K in (50, 200):
    p = apply(knn_g(It, Gt, ht, I, K, ref_t), T)
    ok_base = is_realizable(brans)
    lo, hi = np.zeros(len(p)), np.ones(len(p))
    hi[is_realizable(brans + p)] = 1.0
    need = ~is_realizable(brans + p)
    for _ in range(20):  # largest s in [0,1] with b_rans + s*p realizable
        mid = (lo + hi) / 2
        ok = is_realizable(brans + mid[:, None, None] * p)
        lo = np.where(need & ok, mid, lo); hi = np.where(need & ~ok, mid, hi)
    s = np.where(need, lo, 1.0)
    shrunk = s[:, None, None] * p
    out[f"knn{K}"] = {"raw": ratio(p, y), "shrunk_to_realizable": ratio(shrunk, y),
                      "realizable_after": float(np.mean(is_realizable(brans + shrunk)[ok_base])),
                      "baseline_realizable": float(ok_base.mean())}
    print(K, out[f"knn{K}"])
json.dump(out, open("runs/arms/ceiling-realizable-2026-11-03.json", "w"), indent=2)

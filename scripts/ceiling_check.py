"""Robustness of the train-kNN ceiling: other held-out cases + realizability (exploratory)."""
import json
import numpy as np
import importlib.util, sys
from flowforge.data.frozen_fields import load_frozen_fields, redteam_case_ids, available_attack_flows, score_on_cases
from flowforge.ladder.ladder import _realizability

src = open("scripts/ceiling.py", encoding="utf-8").read().split("out = {")[0]
exec(src)  # helper functions only

It, Tt, yt = load(TRAIN, 20000, seed=0)
mt = usable(It, Tt, yt); It, Tt, yt = It[mt], Tt[mt], yt[mt]
Gt, ht = normal_terms(Tt, yt, 3)
ref_t = (np.log(np.abs(It) + EPS).mean(0), np.log(np.abs(It) + EPS).std(0))
lib = ridge_fit(It, Gt, ht, 1e-6)
champs = {"sparse_v3": "3.765 * T3 + (-3.491) * tanh(I1) * T3 + 3.277 * tanh(I1) * T2 + (-2.974) * T2",
          "loop_v2_v3": "0.255839*T1 + ((-7.49174) + (+7.35441)*tanh(12.4939*I1))*T2 + (3.89159*exp((-1.5)*I1))*T3"}
atk = sorted({f["case_id"] for f in available_attack_flows() if f.get("case_id")})
res = {}
for c in ["curved_step"] + list(redteam_case_ids()) + atk:
    inv, basis, y, brans = load_frozen_fields([c], max_points_per_case=4000, seed=0, return_b_rans=True)
    I = np.stack([inv["I1"], inv["I2"]], 1); T = np.stack([basis[f"T{k}"] for k in (1, 2, 3, 4)], 1); y = np.asarray(y, float)
    m = usable(I, T, y)
    row = {}
    for K in (50, 200):
        p = np.zeros_like(y); p[m] = apply(knn_g(It, Gt, ht, I[m], K, ref_t), T[m])
        row[f"knn{K}"] = round(ratio(p, y), 3)
        row[f"knn{K}_realizable"] = round(_realizability(p[m], np.asarray(brans)[m])[1], 3)
    p = np.zeros_like(y); p[m] = ridge_pred(lib, I[m], T[m])
    row["library"] = round(ratio(p, y), 3)
    for n, ex in champs.items():
        row[n] = round(score_on_cases(ex, [c])[c]["ratio"], 3)
    res[c] = row
    print(c, row)
json.dump(res, open("runs/arms/ceiling-check-2026-11-03.json", "w"), indent=2)

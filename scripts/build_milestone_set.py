"""Build the pre-declared locked milestone-1 candidate set (decisions.md 2026-11-03, option B).

Per approach, the champion with the best curved_step validation in COMPLETED data-v3 runs (E2, E3, E4),
as trained, plus the same structure refit on all non-locked data. Never reads data/locked.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from flowforge.baselines.sparse import fit_sparse_baseline  # noqa: E402
from flowforge.config import load_cases  # noqa: E402
from flowforge.data.frozen_fields import available_attack_flows, load_frozen_fields  # noqa: E402
from flowforge.dsl.expr_fit import fit_expression  # noqa: E402

A = Path("runs/arms")


def best(rows):
    return min((r for r in rows if r.get("metric") is not None), key=lambda r: r["metric"])


def seeds(tag, arms=("swarm", "swarm_no_redteam")):
    out = []
    for s in (42, 43, 44, 45, 46):
        d = json.loads((A / f"{tag}-s{s}.json").read_text(encoding="utf-8"))
        out += [r for a in arms for r in d["arms"][a]["seeds"]]
    return out


picks = {
    "sparse_v3": best(json.loads((A / "e2-v3-sparse.json").read_text())["seeds"]),
    "random_grammar_v3": best(list(json.loads((A / "e2-v3-random.json").read_text())["arms"].values())[0]["seeds"]),
    "loop_v1_v3": best(seeds("e3-v3")),
    "loop_v2_v3": best(seeds("e4-v2")),
}
candidates = {name: r["expression"] for name, r in picks.items()}
candidates["constant_v2data_posthoc"] = "0.333 * T1 + (-3.05432) * T2 + 1.5 * T3"

ids = [c["id"] for c in load_cases()["cases"] if c["split"] != "locked"]
ids += [f["case_id"] for f in available_attack_flows() if f["case_id"] not in ids]
inv, basis, target, b_rans = load_frozen_fields(ids, max_points_per_case=4000, return_b_rans=True)
import numpy as np  # noqa: E402
# same rule as score_expression: drop rows whose target (or inputs) are non-finite (a few in convdiv/curved_step)
ok = np.isfinite(target).reshape(len(target), -1).all(1) & np.isfinite(b_rans).reshape(len(target), -1).all(1)
for d in (inv, basis):
    for k, v in d.items():
        ok &= np.isfinite(v).reshape(len(target), -1).all(1)
inv, basis = {k: v[ok] for k, v in inv.items()}, {k: v[ok] for k, v in basis.items()}
target, b_rans = target[ok], b_rans[ok]
print(f"rows kept {int(ok.sum())} of {len(ok)}")

for name in ("random_grammar_v3", "loop_v1_v3", "loop_v2_v3"):
    fit = fit_expression(candidates[name], inv, basis, target, snap=True, b_rans=b_rans)
    assert fit["status"] in ("ok", "no_improvement"), (name, fit)
    candidates[f"{name}_refit_all"] = fit["expression"]
fit = fit_expression("0.1 * T1 + 0.1 * T2 + 0.1 * T3", inv, basis, target, snap=True, b_rans=b_rans)
candidates["constant_refit_all"] = fit["expression"]
candidates["sparse_refit_all"] = fit_sparse_baseline(inv, basis, target, seed=picks["sparse_v3"]["seed"])["expression"]

meta = {"candidates": candidates, "non_locked_cases": ids,
        "picked_by_validation": {k: {"seed": v["seed"], "curved_step": v["metric"]} for k, v in picks.items()}}
(A / "milestone1-candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
(A / "milestone1-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print(json.dumps(meta["picked_by_validation"], indent=1))
for k, v in candidates.items():
    print(f"{k:28s} {v}")

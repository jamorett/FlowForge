"""Plan (a): every existing arm re-fitted exactly as before (data-v3 train) and scored on the 11 validation hills.

No API. Each LLM champion is rebuilt from its saved feature formulas; the rebuilt formula must reproduce the
saved curved_step ratio (sanity check). Output: runs/arms/hills29-eval-a.json.
"""
import json
from pathlib import Path

import numpy as np

from flowforge.data.feature_dsl import Feature
from flowforge.data.features import STANDARD
from flowforge.data.frozen_fields import train_case_ids
from flowforge.orchestrator.loop_v3 import FixedFeature, load_set
from flowforge.search import omp

VAL = ["alph05_4071_2024", "alph05_7071_3036", "alph05_10071_4048", "alph10_6_3036", "alph10_9_4048",
       "alph10_12_2024", "alph15_7929_4048", "alph15_10929_2024", "alph15_13929_3036", "alph075_80355_3036",
       "alph125_99645_3036"]
VAL = [f"hill29_{v}" for v in VAL]


def evaluate(names, feats, train, sets):
    D, P, T, y = train
    arrays = {f.name: f(P) for f in feats}
    model = omp.search(names, ({**D, **arrays}, T, y), 40)
    scores = omp.score(model, {c: ({**Dv, **{f.name: f(Pv) for f in feats}}, Tv, yv) for c, (Dv, Pv, Tv, yv) in sets.items()})
    hills = [scores[c] for c in VAL]
    return {"formula": model["formula"], "nodes": model["nodes"], "curved_step": scores["curved_step"],
            "hills_mean": float(np.mean(hills)), "hills_worst": float(np.max(hills)),
            "hills": {c: scores[c] for c in VAL}}


def main():
    train = load_set(train_case_ids(), 3000)
    sets = {c: load_set([c], 4000) for c in VAL + ["curved_step"]}
    out = {"label": "exploratory", "mode": "frozen", "train": "data v3 (as the original runs)", "arms": {}}
    out["arms"]["invariants"] = evaluate(["I1", "I2"], [], train, sets)
    out["arms"]["standard"] = evaluate(["I1", "I2", *STANDARD], [], train, sets)
    for k in ("invariants", "standard"):
        a = out["arms"][k]
        print(f"{k:12s} curved {a['curved_step']:.3f}  hills mean {a['hills_mean']:.3f} worst {a['hills_worst']:.3f}")
    for tag in ("v3", "v3long", "v3seed"):
        rows = {}
        for seed in (42, 43, 44, 45, 46):
            d = json.load(open(f"runs/arms/loop-v3-{tag}-{seed}.json"))["seeds"][str(seed)]
            feats = [FixedFeature(n) if n in STANDARD else Feature(n, f, r, train[1]) for n, f, r in d["features"]]
            r = evaluate(["I1", "I2", *[f.name for f in feats]], feats, train, sets)
            assert abs(r["curved_step"] - d["curved_step"]["curved_step"]) < 1e-9, (tag, seed, r["curved_step"])
            rows[seed] = r
            print(f"{tag:7s} {seed}  curved {r['curved_step']:.3f}  hills mean {r['hills_mean']:.3f} worst {r['hills_worst']:.3f}")
        out["arms"][tag] = rows
        m = [r["hills_mean"] for r in rows.values()]
        print(f"== {tag}: hills mean {np.mean(m):.3f} ± {np.std(m, ddof=1):.3f}")
    Path("runs/arms/hills29-eval-a.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

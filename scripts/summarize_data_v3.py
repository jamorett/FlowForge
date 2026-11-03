"""Combine the data-v3 arms (E2, E3, E4, E5) into one run_arms-format file for the UI Results page.

Exploratory, frozen, curved_step validation. Writes runs/arms/data-v3-summary.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from scripts import run_arms  # noqa: E402

A = Path("runs/arms")
SEEDS = (42, 43, 44, 45, 46)


def per_seed(tag, arm):
    rows, spent = [], 0.0
    for s in SEEDS:
        f = A / f"{tag}-s{s}.json"
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            rows += d["arms"][arm]["seeds"]
            spent += d["spent_usd"] / 2  # both arms share one per-seed total
    return rows, spent


arms, spent = {}, 0.0
arms["sparse_baseline"] = json.loads((A / "e2-v3-sparse.json").read_text())["seeds"]
arms["random_grammar"] = list(json.loads((A / "e2-v3-random.json").read_text())["arms"].values())[0]["seeds"]
for label, tag in (("loop_v1", "e3-v3"), ("loop_v2", "e4-v2"), ("loop_v2.1", "e5-v21")):
    for arm, suffix in (("swarm", ""), ("swarm_no_redteam", "_no_redteam")):
        rows, s = per_seed(tag, arm)
        arms[f"{label}{suffix}"], spent = rows, spent + s
out = {"label": "exploratory", "mode": "frozen", "data": "v3", "rounds": 5, "groups": 2,
       "seeds": list(SEEDS), "spent_usd": round(spent, 2), "incomplete": any(len(r) < 5 for r in arms.values()),
       "arms": {k: {"seeds": v, "summary": run_arms.summarize_or_none([r["metric"] for r in v], len(v))}
                for k, v in arms.items()}}
(A / "data-v3-summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
for k, v in out["arms"].items():
    s = v["summary"]
    print(f"{k:24s} n={len(v['seeds'])} " + (f"{s['mean']:.3f} ± {s['stdev']:.3f}" if s else "incomplete"),
          [round(r["metric"], 3) for r in v["seeds"]])
print("spent (E3+E4+E5 swarm arms):", out["spent_usd"])

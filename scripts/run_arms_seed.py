"""Run both swarm arms for ONE seed (same collect_swarm_arm as run_arms.py), so seeds run in parallel.

usage: python scripts/run_arms_seed.py SEED TAG LOOP BUDGET_USD   (LOOP = v1 | v2)
writes runs/arms/<TAG>-s<SEED>.json; red-team breaks go to runs/arms/<TAG>-attacks/.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from flowforge.orchestrator import round as round_v1  # noqa: E402
from scripts import run_arms  # noqa: E402

seed, tag, loop, budget = int(sys.argv[1]), sys.argv[2], sys.argv[3], float(sys.argv[4])
round_v1.ATTACKS_DIR = Path("runs/arms") / f"{tag}-attacks"
run_arms.LOOP[0] = loop
spent, incomplete = [0.0], [False]
out = {"tag": tag, "seed": seed, "loop": loop, "data": "v3", "mode": "frozen", "label": "exploratory",
       "rounds": 5, "groups": 2, "arms": {}}
for arm in ("swarm", "swarm_no_redteam"):
    out["arms"][arm] = run_arms.collect_swarm_arm(arm, [seed], 5, 2, budget, False, spent, incomplete)
    print(arm, [(r["metric"], r["expression"]) for r in out["arms"][arm]["seeds"]], flush=True)
out.update(spent_usd=spent[0], incomplete=incomplete[0])
Path(f"runs/arms/{tag}-s{seed}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"done spent=${spent[0]:.2f} incomplete={incomplete[0]}", flush=True)

"""E6: loop v2.1 with the node cap raised (FLOWFORGE_MAX_NODES), one seed per process.

Same as scripts/run_arms_seed.py, but sessions are prefixed with the tag so they never
mix history with other loop-v2 sessions. usage: run_e6.py SEED TAG BUDGET_USD
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")
from flowforge.dsl import parser  # noqa: E402
from flowforge.orchestrator import loop_v2  # noqa: E402
from flowforge.orchestrator import round as round_v1  # noqa: E402
from scripts import run_arms  # noqa: E402

seed, tag, budget = int(sys.argv[1]), sys.argv[2], float(sys.argv[3])
assert parser.MAX_NODES == loop_v2.MAX_NODES == int(os.environ["FLOWFORGE_MAX_NODES"]), "cap not applied"
round_v1.ATTACKS_DIR = Path("runs/arms") / f"{tag}-attacks"
run_arms.LOOP[0] = "v2"
original = loop_v2.run_round
loop_v2.run_round = lambda *a, session=None, **k: original(*a, session=f"{tag}-{session}", **k)
spent, incomplete = [0.0], [False]
out = {"tag": tag, "seed": seed, "loop": "v2.1", "max_nodes": parser.MAX_NODES, "data": "v3",
       "mode": "frozen", "label": "exploratory", "rounds": 5, "groups": 2, "arms": {}}
for arm in ("swarm", "swarm_no_redteam"):
    out["arms"][arm] = run_arms.collect_swarm_arm(arm, [seed], 5, 2, budget, False, spent, incomplete)
    print(arm, [(r["metric"], r["expression"]) for r in out["arms"][arm]["seeds"]], flush=True)
out.update(spent_usd=spent[0], incomplete=incomplete[0])
Path(f"runs/arms/{tag}-s{seed}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"done spent=${spent[0]:.2f} incomplete={incomplete[0]}", flush=True)

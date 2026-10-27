"""Probe S4a/S5 gaps: replay, validation, ladder rungs. Read-only checks."""
import os, sys, tempfile, json
sys.path.insert(0, ".")
results = {}
# 1 replay zero-token
from flowforge.agents.runtime.event_logger import EventLogger, prompt_hash
from flowforge.agents.runtime.client import ModelRuntime
with tempfile.TemporaryDirectory() as d:
    from pathlib import Path
    lg = EventLogger(Path(d))
    lg.log({"prompt_hash": prompt_hash("hello"), "model": "m", "tokens": 5, "response": {"text": "{}"}})
    os.environ["FLOWFORGE_REPLAY"] = "1"
    try:
        r = lg.replay_lookup(prompt_hash("hello")); results["replay_hit"] = r
    except Exception as e: results["replay_hit"] = f"ERR {e}"
    try:
        lg.replay_lookup("deadbeef"); results["replay_miss"] = "NO-RAISE (bad)"
    except Exception as e: results["replay_miss"] = f"raised {type(e).__name__}"
    # missing-hash event: write is now rejected, and a corrupt line errors on scan
    try:
        lg.log({"model": "m", "response": {"text": "x"}}); results["missing_hash_write"] = "NO-RAISE (bad)"
    except Exception as e: results["missing_hash_write"] = f"raised {type(e).__name__}"
    with open(lg.path, "a") as fh: fh.write('{"response": {"text": "x"}}\n')
    try:
        lg.replay_lookup(prompt_hash("hello")); results["missing_hash_scan"] = "no error (bad)"
    except Exception as e: results["missing_hash_scan"] = f"raised {type(e).__name__}: {e}"
    # does client.complete honor replay?
    rt = ModelRuntime(logger=lg)
    results["client_has_complete_structured"] = hasattr(rt, "complete_structured")
    results["client_has_replay_branch"] = "FLOWFORGE_REPLAY" in open("flowforge/agents/runtime/client.py").read()
    del os.environ["FLOWFORGE_REPLAY"]
# 2 schemas risk_audit empty allowed?
from flowforge.agents.schemas import RoundPlan
try:
    RoundPlan(mechanisms=["a"], budget_split={"x": 1.0}, risk_audit=""); results["empty_risk_audit"] = "ACCEPTED (bad)"
except Exception as e: results["empty_risk_audit"] = f"rejected {type(e).__name__}"
try:
    RoundPlan(mechanisms=["a"], budget_split={"x": 1.0}); results["missing_risk_audit"] = "ACCEPTED (bad)"
except Exception as e: results["missing_risk_audit"] = f"rejected {type(e).__name__}"
# 3 ladder rungs
import flowforge.ladder.ladder as L
results["has_rung2"] = hasattr(L, "rung2_short")
results["has_rung3"] = hasattr(L, "rung3_full")
results["has_run_ladder"] = hasattr(L, "run_ladder")
# 4 round mock
from flowforge.orchestrator.round import run_round
res = run_round(1, mock=True)
results["round_keys"] = sorted(res.keys()); results["round_status"] = res["status"]
print(json.dumps(results, indent=1, default=str))

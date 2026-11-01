import subprocess, sys, os, json, pathlib

def run(args, env=None):
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(args, capture_output=True, text=True, timeout=120, env=e)
    return r.returncode, (r.stdout + r.stderr)[:700]

print("export_demo", run([sys.executable, "scripts/export_demo.py"]))
print("reproduce", run([sys.executable, "scripts/reproduce_champion.py", "--champion-hash", "deadbeef"]))
print("reproduce_noarg", run([sys.executable, "scripts/reproduce_champion.py"]))
print("run_arms_mock", run([sys.executable, "scripts/run_arms.py", "--mock"]))
print("run_arms_real", run([sys.executable, "scripts/run_arms.py"]))
sys.path.insert(0, ".")
os.environ["FLOWFORGE_REPLAY"] = "1"
from flowforge.agents.runtime.event_logger import EventLogger, prompt_hash
import tempfile
with tempfile.TemporaryDirectory() as td:
    lg = EventLogger(pathlib.Path(td))
    lg.log({"prompt_hash": prompt_hash("hello"), "response": {"text": "world"}})
    print("replay_hit", lg.replay_lookup(prompt_hash("hello")))
    try:
        lg.replay_lookup("deadbeef"); print("replay_miss NO-RAISE")
    except Exception as e:
        print("replay_miss raises", type(e).__name__, str(e)[:140])
ev = [json.loads(l) for l in pathlib.Path("runs/probe_s55/events.jsonl").read_text().splitlines() if l.strip()]
print("probe_s55", ev, "has_response", any("response" in e for e in ev))
readme = pathlib.Path("README.md").read_text()
print("README_tokens", {k: (k in readme) for k in ["uv ", "docker", "pytest", "reproduce", "export_demo", "FLOWFORGE_REPLAY", "npm", "vite"]})
print("uvlock_venv", pathlib.Path("uv.lock").exists(), pathlib.Path(".venv").exists())
import shutil
for c in ["docker", "uv", "pytest"]:
    print(c, shutil.which(c))
# orchestrator: does round.py have replay mode?
rt = pathlib.Path("flowforge/orchestrator/round.py").read_text()
print("round_has_replay", "replay" in rt.lower(), "round_has_eventlogger", "EventLogger" in rt)
print("export_demo_callers_checked_manually")

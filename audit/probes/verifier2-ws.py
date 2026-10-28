"""Verifier2 WS pacing (wall-clock, bare subscribe) + eventlog/replay + composer/minimax fixes."""
import asyncio, json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
# composer / minimax correct signatures
import numpy as np
from flowforge.composer.gates import compose
comp,pen=compose(np.ones((2,)),np.zeros((2,)),np.array([0.0,1.0]),w=1.0,b=0.0)
print("compose",comp.tolist(),"penalty",pen)
from flowforge.ladder.ladder import minimax_score
print("minimax_ratio", minimax_score({"a":1.0,"b":4.0},{"a":2.0,"b":2.0}))  # max ratio =2.0
# eventlog
from flowforge.agents.runtime.event_logger import EventLogger
with tempfile.TemporaryDirectory() as td:
    lg=EventLogger(Path(td)); lg.log({"type":"model_response","prompt_hash":"abc","response":{"x":1}})
    print("eventlog_lines",len(lg.read_events()))
    try: lg.log({"response":{"y":2}}); print("nohash ALLOWED")
    except Exception as e: print("nohash_refused",type(e).__name__)
    os.environ["FLOWFORGE_REPLAY"]="1"
    print("replay_hit",lg.replay_lookup("abc"))
    try: lg.replay_lookup("missing"); print("replay_miss ALLOWED")
    except Exception as e: print("replay_miss_refused",type(e).__name__)
    del os.environ["FLOWFORGE_REPLAY"]
    print("replay_off_returns",lg.replay_lookup("abc"))
# WS: use runs/ under temp cwd, restore after
import flowforge.api.server as srv
print("ws_sig",srv.ws_events.__code__.co_varnames, "PACE",srv.PACE_SECONDS)
orig=Path.cwd()
with tempfile.TemporaryDirectory() as td:
    os.chdir(td); Path("runs/s1").mkdir(parents=True)
    Path("runs/s1/events.jsonl").write_text("\n".join(json.dumps({"i":i}) for i in range(5)))
    stamps=[]
    class FakeWS:
        async def accept(self): pass
        async def send_text(self,t): stamps.append((time.perf_counter(),t))
    asyncio.run(srv.ws_events(FakeWS(), session="s1"))
    gaps=[round(stamps[i+1][0]-stamps[i][0],3) for i in range(len(stamps)-1)]
    print("ws_count",len(stamps),"gaps",gaps,"first_is_event",stamps[0][1])
    print("ws_bare_default_paced", all(g>=0.04 for g in gaps[:-1]) if len(gaps)>1 else "n/a")
    os.chdir(orig)
# git
import subprocess
r=subprocess.run(["git","-c",f"safe.directory={ROOT.as_posix()}","status","--porcelain"],capture_output=True,text=True,timeout=120,cwd=ROOT)
print("git_status_exit",r.returncode,"lines",len(r.stdout.splitlines())); print(r.stdout[:600])
r=subprocess.run([sys.executable,"audit/check_audit.py"],capture_output=True,text=True,timeout=120,cwd=ROOT)
print("check_audit_exit",r.returncode); print(r.stdout[:1200])

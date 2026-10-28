import asyncio, json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import flowforge.api.server as srv
orig=Path.cwd()
with tempfile.TemporaryDirectory(dir="/tmp") as td:
    os.chdir(td); Path("runs/s1").mkdir(parents=True)
    Path("runs/s1/events.jsonl").write_text("\n".join(json.dumps({"i":i}) for i in range(5)))
    stamps=[]
    class FakeWS:
        async def accept(self): pass
        async def send_text(self,t): stamps.append((time.perf_counter(),t))
    asyncio.run(srv.ws_events(FakeWS(), session="s1"))
    gaps=[round(stamps[i+1][0]-stamps[i][0],3) for i in range(len(stamps)-1)]
    print("ws_count",len(stamps),"gaps_s",gaps)
    print("msgs",[s[1][:40] for s in stamps])
    os.chdir(orig)
print("selector_ws_ok")

"""Bare WS pacing probe, no sockets/event-loop: drive ws_events coroutine manually.
Patches flowforge.api.server.asyncio.sleep to record requested delays.
Signature has no pacing/count -> bare subscribe is server-paced by construction if delays recorded.
"""
import json, os, sys, tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
class Aw:
    def __init__(self, v=None): self.v=v
    def __await__(self):
        yield self
        return self.v
class FakeWS:
    def __init__(self): self.msgs=[]
    def accept(self): return Aw()
    def send_text(self, t): self.msgs.append(t); return Aw()
import flowforge.api.server as srv
delays=[]
orig_sleep = srv.asyncio.sleep
def fake_sleep(d): delays.append(d); return Aw()
srv.asyncio.sleep = fake_sleep
try:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        os.chdir(td)
        p=Path("runs/probe"); p.mkdir(parents=True)
        (p/"events.jsonl").write_text("\n".join(json.dumps({"type":"tick","i":i}) for i in range(5))+"\n")
        import inspect
        print("signature", inspect.signature(srv.ws_events))
        ws=FakeWS(); coro=srv.ws_events(ws, session="probe")
        try:
            while True: coro.send(None)
        except StopIteration:
            pass
        print("messages", len(ws.msgs), "delays", delays, "last", ws.msgs[-1])
        print("PACED_OK bare subscribe: sleep(0.05) after each event" if delays==[0.05]*5 else "PACED_FAIL")
        os.chdir(str(REPO))
finally:
    srv.asyncio.sleep = orig_sleep

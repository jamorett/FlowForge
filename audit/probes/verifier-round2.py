"""Verifier round-2 falsification probe. Read-only except temp dirs.
Exit 0 always if probe itself completes; prints FINDING lines."""
import inspect, json, os, sys, tempfile, time
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
_td = tempfile.mkdtemp(prefix="ff-verifier-", dir=os.environ.get("TEMP", "C:/tmp"))
os.chdir(_td)
print("cwd_is_temp", Path.cwd())

# 1. Oracle disconnect: flip production_target sign -> gate tests still pass?
import numpy as np
from flowforge.physics import frozen_rans
rng = np.random.default_rng(42)
a = rng.normal(size=(4,3,3)); a = 0.5*(a+np.swapaxes(a,-1,-2))
k = np.full(4, 0.05); S = rng.normal(size=(4,3,3)); S = 0.5*(S+np.swapaxes(S,-1,-2))
orig = frozen_rans.production_target(a, k, S)
flipped = -orig
print("FINDING oracle_sign_blind: zero-aDelta identity check uses a=0 so sign flip invisible:",
      bool(np.all(frozen_rans.production_target(np.zeros((4,3,3)), k, S) == 0)))
# u_oracle in test_oracle.py is hardcoded blend, not derived from a_delta/pk_delta
src = (REPO/"tests/integration/test_oracle.py").read_text()
print("FINDING oracle_hardcoded_blend:", "u_base - 0.75 * (u_base - u_dns)" in src,
      "| pk_delta feeds u_oracle:", "pk_delta" in src.split("u_oracle")[1][:200] if "u_oracle" in src else "?")

# 2. Identity triviality
print("FINDING identity_zero_only: test asserts max|0|==0 line present:",
      "u_base + 2.0 * k[:, None] * 0.0" in (REPO/"tests/integration/test_identity.py").read_text())

# 3. Split guard wiring + over/under breadth
from flowforge.data.split_guard import guard_path, _is_locked
for p in ["data/locked/x", "data/raw/../locked/x", "other/locked/x", "data/lockedness/x", "DATA/LOCKED/x"]:
    print("guard", p, "locked=", _is_locked(Path(p)))
callers = []
for f in (REPO/"flowforge").rglob("*.py"):
    t = f.read_text(errors="ignore")
    if "guard_path" in t and "split_guard" not in str(f):
        callers.append(str(f.relative_to(REPO)))
print("FINDING guard_callers_outside_def:", callers)
# symlink escape (lexical only, no resolve)
print("FINDING guard_no_resolve:", "resolve" not in (REPO/"flowforge/data/split_guard.py").read_text())

# 4. Composer evaluate truncation bug
from flowforge.composer.evaluate import evaluate_composition
mods = [np.zeros((2,)), np.zeros((2,)), np.full((2,), 10.0)]
tgts = [np.zeros((2,)), np.zeros((2,)), np.zeros((2,))]
gi = [np.zeros(2)]*3
r = evaluate_composition(mods, gi, tgts, 0.0, 0.0)
print("FINDING composer_truncation: n_modules=3 n_gates=", r["n_gates"], "worst=", r["worst_error"],
      "best_single_worst=", r["best_single_worst"], "beats_single=", r["beats_single"],
      "(preds zip truncated to len-1, target[2]=0 never paired with pred from modules[1:3] correctly)")

# 5. WS pacing with REAL sleep timing (bare subscribe, no args)
import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from flowforge.api import server as srv
Path("runs/probe").mkdir(parents=True, exist_ok=True)
(Path("runs/probe/events.jsonl")).write_text("\n".join(json.dumps({"type":"tick","i":i}) for i in range(5))+"\n")
class FakeWS:
    def __init__(self): self.msgs=[]; self.times=[]
    async def accept(self): pass
    async def send_text(self, t): self.msgs.append(t); self.times.append(time.monotonic())
async def run_ws():
    ws = FakeWS(); t0 = time.monotonic()
    await srv.ws_events(ws, session="probe")
    gaps = [round(b-a,3) for a,b in zip(ws.times, ws.times[1:])]
    print("FINDING ws_real_timing: msgs=", len(ws.msgs), "gaps_s=", gaps, "total=", round(time.monotonic()-t0,3),
          "sig=", str(inspect.signature(srv.ws_events)))
asyncio.run(run_ws())

# 6. Client import (tenacity missing) + registry hardcoded
try:
    import flowforge.agents.runtime.client  # noqa
    print("FINDING client_import: OK")
except Exception as e:
    print("FINDING client_import FAIL:", type(e).__name__, e)
reg = (REPO/"flowforge/agents/tools/registry.py").read_text()
print("FINDING registry_search_cards_hardcoded_empty:", "return []" in reg)
print("FINDING registry_tools:", [l.strip() for l in reg.splitlines() if "@register" in l])

# 7. Round loop: no event log write, mock ignored, synthetic only
rsrc = (REPO/"flowforge/orchestrator/round.py").read_text()
print("FINDING round_no_eventlogger:", "EventLogger" not in rsrc, "| mock used only as echo:", rsrc.count("mock"),
      "| synthetic target 0.5*T1:", "0.5 * basis" in rsrc)

# 8. DSL single-term vs spec sum over T1..T4 + h(I)
esrc = (REPO/"flowforge/dsl/evaluate.py").read_text()
print("FINDING dsl_single_term_T1_only:", "g(I) * T1" in esrc or "* t1" in esrc, "| uses T2/T3/T4:", any(t in esrc for t in ['"T2"','"T3"','"T4"']))

# 9. C++ nut surrogate
csrc = (REPO/"openfoam/src/correctedKOmegaSST/correctedKOmegaSST.C").read_text()
print("FINDING cpp_nut_surrogate:", "nut" in csrc.lower(), "| kEqn present:", "kEqn" in csrc, "| snippet:", [l.strip()[:100] for l in csrc.splitlines() if "nut_" in l][:3])

# 10. run_arms mock formula
print("FINDING run_arms_mock_formula:", "(seed % 7) + len(arm)" in (REPO/"scripts/run_arms.py").read_text())
print("PROBE_DONE")

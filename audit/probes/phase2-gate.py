"""Phase2 gate probe: run mock round in temp cwd, check WS pacing, tensors, guard.
Run: python audit/probes/phase2-gate.py  (timeout 120 via parent subprocess)
Writes only to a TemporaryDirectory; repo root added to sys.path read-only.
"""
import json, sys, tempfile, time, traceback
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
results = {}
# 1. deps
import importlib.util
results["deps"] = {m: bool(importlib.util.find_spec(m)) for m in ["sympy","sklearn","zarr","pytest","fastapi","numpy"]}
# 2. tensors pure rotation (numpy only)
try:
    import numpy as np
    from flowforge.physics.tensors import normalized_tensors, invariants, tensor_basis
    # pure rotation: grad = antisymmetric, omega=2
    grad = np.array([[0., -1., 0.],[1., 0., 0.],[0., 0., 0.]])
    s, w = normalized_tensors(grad, np.array(2.0))
    inv = invariants(s, w); basis = tensor_basis(s, w)
    results["pure_rotation"] = {"s_max": float(np.max(np.abs(s))), "I": {k: float(v) for k,v in inv.items()},
        "T4_max": float(np.max(np.abs(basis["T4"]))), "T1_max": float(np.max(np.abs(basis["T1"])))}
except Exception as e:
    results["pure_rotation_error"] = f"{type(e).__name__}: {e}"
# 3. split_guard in temp cwd
import os
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
    os.chdir(td)
    try:
        import flowforge.data.split_guard as sg
        sg.LOG = Path(td)/"runs"/"vault_access.log"
        try:
            sg.guard_path(Path("data/locked/x"), role="theorist"); results["guard"]="NO_RAISE"
        except PermissionError as e:
            results["guard"] = f"PermissionError logged={sg.LOG.exists()} text={sg.LOG.read_text() if sg.LOG.exists() else ''!r}"
    except Exception as e:
        results["guard_error"] = f"{type(e).__name__}: {e}"
    # 4. mock round gate (exact command equivalent, in temp cwd)
    try:
        from flowforge.orchestrator.round import run_round
        t0=time.time(); r=run_round(1, mock=True); results["mock_round"]={"elapsed":round(time.time()-t0,3), **r}
        # champion dl constants empty?
        results["mock_round_note"]="champion dl uses description_length(complexity, []) in round.py:60"
    except Exception as e:
        results["mock_round_error"] = f"{type(e).__name__}: {e}"; results["mock_round_tb"]=traceback.format_exc()[-1500:]
    # 5. WS pacing via TestClient if available, else code-inspection fallback
    try:
        (Path(td)/"runs"/"probe").mkdir(parents=True, exist_ok=True)
        (Path(td)/"runs"/"probe"/"events.jsonl").write_text("\n".join(json.dumps({"type":"tick","i":i}) for i in range(5))+"\n")
        from fastapi.testclient import TestClient
        from flowforge.api.server import app
        times=[]
        with TestClient(app).websocket_connect("/ws/events?session=probe") as ws:
            while True:
                t=time.perf_counter(); m=ws.receive_text(); times.append(t)
                if json.loads(m).get("type")=="end": break
        gaps=[round((b-a)*1000) for a,b in zip(times, times[1:])]
        results["ws_bare_subscribe"]={"messages":len(times),"gaps_ms":gaps,"paced_ok": all(g>=30 for g in gaps[:-1]) if len(gaps)>1 else None}
    except Exception as e:
        results["ws_error"]=f"{type(e).__name__}: {e}"
        src=(REPO/"flowforge/api/server.py").read_text()
        results["ws_code_fallback"]="PACE_SECONDS=0.05 sleep after each send (server.py:19,111); no client pacing/count params read in ws_events signature (100)"
    os.chdir(str(REPO))
print(json.dumps(results, indent=2, default=str))

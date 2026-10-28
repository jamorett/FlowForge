"""Verifier Round 3 probe: re-execute remaining VERIFIED rows + downgrade spots.

Stdlib + numpy only (env here). Run: python audit/probes/verifier3-main.py
Never opens data/locked/. Temp dirs only for guard/event-logger checks.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        failures.append(name)


# --- P1-08 / P1-10: gate logic probe (subprocess, timeout=120) ---
p = subprocess.run([sys.executable, "audit/probes/gate_logic_probe.py"],
                   cwd=REPO, capture_output=True, text=True, timeout=120)
check("P1-08_P1-10_gate_logic_exit0", p.returncode == 0, f"exit={p.returncode}")
check("P1-08_P1-10_gate_logic_4pass", p.stdout.count("PASS test_") == 4,
      f"stdout={p.stdout.strip()!r}")

# --- P3-01: generator ---
try:
    from flowforge.redteam.generator import generate_attacks
    specs = generate_attacks()
    check("P3-01_count12", len(specs) == 12, f"n={len(specs)}")
    check("P3-01_alphas", sorted({s.alpha for s in specs}) == [0.5, 0.75, 1.25, 1.5],
          f"alphas={sorted({s.alpha for s in specs})}")
    check("P3-01_validation_only", {s.split for s in specs} == {"validation"},
          f"splits={ {s.split for s in specs} }")
except Exception as exc:
    check("P3-01_import", False, repr(exc))

# --- P4-01 / P4-02: composer kernel ---
try:
    import numpy as np
    from flowforge.composer.gates import compose
    out, penalty = compose(np.ones(2), np.zeros(2), [0, 1], w=1.0, b=0.0)
    check("P4-01_sigmoid", bool(np.allclose(out, [0.5, 0.73105858], atol=1e-6)),
          f"out={out}")
    check("P4-02_penalty16", penalty == 16.0, f"penalty={penalty}")
    # P4-06 zip bug reproduction (carried defect, not a VERIFIED claim)
    try:
        from flowforge.composer.evaluate import evaluate_composition
        res = evaluate_composition([np.zeros(2), np.zeros(2), np.zeros(2)],
                                   [np.array([0.0]), np.array([0.0]), np.array([0.0])],
                                   [np.zeros(2), np.zeros(2), np.full(2, 99.0)],
                                   1.0, 0.0)
        check("P4-06_zip_bug_present", res["worst_error"] == 0.0,
              f"worst_error={res['worst_error']} (99-target dropped)")
    except Exception as exc:
        print(f"NOTE P4-06 probe shape differed: {exc!r}")
except Exception as exc:
    check("P4-01_P4-02_import", False, repr(exc))

# --- P2-16: WS pacing by construction ---
srv = (REPO / "flowforge/api/server.py").read_text(encoding="utf-8")
check("P2-16_pace_const", "PACE_SECONDS = 0.05" in srv or "PACE_SECONDS=0.05" in srv)
check("P2-16_no_pacing_param", "pacing" not in srv.split("ws_events")[1][:400].lower()
      if "ws_events" in srv else False)
si, sl = srv.find("send_text"), srv.find("asyncio.sleep")
check("P2-16_send_before_sleep", 0 < si < sl, f"send@{si} sleep@{sl}")

# --- Downgrade spots ---
# P1-02: template files + flat header
tmpl = REPO / "openfoam/templates/periodicHill/system/blockMeshDict"
check("P1-02_files_and_flat", tmpl.exists() and "flat" in tmpl.read_text(encoding="utf-8").lower())
# P6-07: tenacity absent => ModelRuntime unimportable; EventLogger replay works
try:
    import tenacity  # noqa: F401
    check("P6-07_tenacity_absent", False, "tenacity unexpectedly present")
except ModuleNotFoundError:
    check("P6-07_tenacity_absent", True)
try:
    from flowforge.agents.runtime.event_logger import EventLogger
    with tempfile.TemporaryDirectory() as td:
        log = EventLogger(Path(td) / "events.jsonl")
        import inspect
        print("NOTE EventLogger methods:", [m for m in dir(log) if not m.startswith("_")])
        print("NOTE EventLogger sig:", inspect.signature(EventLogger.__init__))
except Exception as exc:
    print(f"NOTE EventLogger probe: {exc!r}")
# P5-05: mock formula present
ra = (REPO / "scripts/run_arms.py").read_text(encoding="utf-8")
check("P5-05_mock_formula", "len(" in ra and "mock" in ra.lower())
# P2-10: guard function in temp cwd
try:
    import os
    from flowforge.data.split_guard import guard_path
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        os.chdir(td)
        try:
            guard_path("data/locked/x", role="theorist")
            check("P2-10_denies", False, "no PermissionError")
        except PermissionError:
            check("P2-10_denies", True)
        except TypeError as exc:
            print(f"NOTE guard_path signature: {exc!r}")
        try:
            r = guard_path("my_locked_notes/x", role="theorist")
            check("P2-10_lookalike_allowed", True, f"returned {r!r}")
        except Exception as exc:
            check("P2-10_lookalike_allowed", False, repr(exc))
        os.chdir(REPO)
except Exception as exc:
    check("P2-10_import", False, repr(exc))
finally:
    os.chdir(REPO)

# --- Round-2 JSON status spots (accuracy, read-only) ---
rows = {}
for x in range(7):
    for r in json.loads((REPO / f"audit/round-2/phase-{x}.json").read_text(encoding="utf-8")):
        rows[r["id"]] = r["status"]
check("spot_P1-02", rows.get("P1-02") == "PRESENT_UNTESTED", rows.get("P1-02"))
check("spot_P6-07", rows.get("P6-07") == "PRESENT_UNTESTED", rows.get("P6-07"))
check("spot_P5-05", rows.get("P5-05") == "PRESENT_UNTESTED", rows.get("P5-05"))
check("spot_P2-10", rows.get("P2-10") == "PRESENT_UNTESTED", rows.get("P2-10"))
check("spot_VERIFIED6", sorted(k for k, v in rows.items() if v == "VERIFIED")
      == ["P1-08", "P1-10", "P2-16", "P3-01", "P4-01", "P4-02"])
check("spot_OM_rows", all(k in rows for k in
      ["P0-19", "P2-19", "P2-20", "P2-21", "P2-22", "P2-23", "P4-13", "P5-17"]),
      f"n_rows={len(rows)}")

print("RESULT:", "FAIL " + ",".join(failures) if failures else "ALL PASS")
sys.exit(1 if failures else 0)

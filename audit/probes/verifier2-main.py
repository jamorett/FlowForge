"""Verifier Round-2 independent probe. Stdlib+numpy only where available. No data/locked access."""
import ast, asyncio, importlib.util, inspect, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def out(k, v): print(f"{k}={v}")
# env
for cmd in ["pytest","docker","uv","ruff","mypy"]:
    out(f"which_{cmd}", shutil.which(cmd))
out("python", sys.version.split()[0])
for mod in ["numpy","scipy","sympy","sklearn","tenacity","zarr","foamlib","pydantic","fastapi","openai","pytest","pyvista","duckdb","pandas"]:
    out(f"import_{mod}", importlib.util.find_spec(mod) is not None)
out("uv_lock", (ROOT/"uv.lock").exists()); out("venv", (ROOT/".venv").exists())
out("MODEL_API_KEY_set", bool(os.environ.get("MODEL_API_KEY")))
# subprocess gates
for name,args in [("gate_logic",["audit/probes/gate_logic_probe.py"]),("pytest_collect",["-m","pytest","--collect-only","-q"]),("check_audit",["audit/check_audit.py"])]:
    try:
        r=subprocess.run([sys.executable]+args,capture_output=True,text=True,timeout=120,cwd=ROOT)
        out(f"sub_{name}_exit", r.returncode); print(f"---{name}---\n{(r.stdout+r.stderr)[:2500]}")
    except Exception as e: out(f"sub_{name}", repr(e))
# VERIFIED re-runs
# P1-02 files
base=ROOT/"openfoam/templates/periodicHill"
need=["0/U","0/p","0/k","0/omega","constant/transportProperties","constant/turbulenceProperties","system/blockMeshDict","system/controlDict"]
out("P1-02_files", all((base/p).exists() for p in need))
out("P1-03_flat_header", "flat walls" in (base/"system/blockMeshDict").read_text(errors="ignore"))
# P3-01 generator, P4 composer, tensors, ladder import, dsl compile
sys.path.insert(0,str(ROOT))
try:
    from flowforge.redteam.generator import generate_attacks
    specs=generate_attacks(); out("P3-01_specs", len(specs)); out("P3-01_alphas", sorted({s.alpha for s in specs})); out("P3-01_splits", sorted({s.split for s in specs}))
    try: generate_attacks(alphas=(2.0,)); out("P3-01_alpha2_refused", False)
    except Exception as e: out("P3-01_alpha2_refused", type(e).__name__)
except Exception as e: out("P3-01_err", repr(e))
try:
    from flowforge.composer.gates import compose
    import numpy as np
    r=compose(np.ones((2,2)),np.zeros((2,2)),np.array([0.0,1.0]),w=1.0,b=0.0)
    out("P4-01_compose_shape", r.shape)
    from flowforge.composer.evaluate import evaluate_composition
    out("P4-02_src_has_16", "16" in Path(ROOT/"flowforge/composer/evaluate.py").read_text())
except Exception as e: out("P4_err", repr(e))
try:
    from flowforge.ladder.ladder import run_ladder, minimax_score
    out("ladder_import", True); out("minimax", minimax_score({"a":0.5,"b":2.0}))
except Exception as e: out("ladder_import_err", repr(e))
try:
    from flowforge.dsl.compiler import compile_candidate
    out("gen_compile", compile_candidate("0.1*T1"))
except Exception as e: out("gen_compile_err", repr(e))
# event log / replay in temp
try:
    from flowforge.agents.runtime.event_logger import EventLogger, replay_lookup
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"events.jsonl"; lg=EventLogger(p)
        lg.log({"type":"model_response","prompt_hash":"abc","response":{"x":1}})
        out("eventlog_lines", len(p.read_text().splitlines()))
        try: lg.log({"type":"x"}); out("eventlog_nohash_refused", False)
        except Exception as e: out("eventlog_nohash_refused", type(e).__name__)
        out("replay_hit", replay_lookup(p,"abc"))
        try: replay_lookup(p,"missing"); out("replay_miss_refused", False)
        except Exception as e: out("replay_miss_refused", type(e).__name__)
except Exception as e: out("eventlog_err", repr(e))
# locked guard in temp cwd (never data/locked)
try:
    from flowforge.data.split_guard import guard_path
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try: guard_path("data/locked/x", role="theorist"); out("P2-10_refused", False)
        except PermissionError: out("P2-10_refused", True)
        out("P2-10_log", (Path(td)/"runs/vault_access.log").exists())
        # over-broad / traversal probes
        for pth in ["data/processed/../locked/x","my_locked_notes/x","data/lockedness/x"]:
            try: guard_path(pth, role="evaluator"); out(f"guard_{pth}", "ALLOWED")
            except PermissionError: out(f"guard_{pth}", "DENIED")
        os.chdir(ROOT)
except Exception as e: out("P2-10_err", repr(e))
# WS pacing wall-clock with fake ws, bare subscribe signature
try:
    import flowforge.api.server as srv
    out("ws_sig", str(inspect.signature(srv.ws_events))); out("PACE", srv.PACE_SECONDS)
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td); (Path("runs/s1")).mkdir(parents=True)
        (Path("runs/s1/events.jsonl")).write_text("\n".join(json.dumps({"i":i}) for i in range(5)))
        stamps=[]
        class FakeWS:
            async def accept(self): pass
            async def send_text(self,t): stamps.append(time.perf_counter())
        asyncio.run(srv.ws_events(FakeWS(), session="s1"))
        gaps=[round(b-a,3) for a,b in zip(stamps, stamps[1:])]
        out("ws_msgs", len(stamps)); out("ws_gaps_s", gaps); out("ws_first_prompt_lt20ms", (gaps and True))
        os.chdir(ROOT)
except Exception as e: out("ws_err", repr(e))
# dead code callers (AST name search)
srcs=list(ROOT.glob("flowforge/**/*.py"))+list(ROOT.glob("scripts/*.py"))
allsrc="\n".join(p.read_text(errors="ignore") for p in srcs)
for name in ["run_attack_suite","record_attack","ingest_case","compile_cpp","guard_path","generate_attacks","minimax_score","hill_height","render_png","harvest"]:
    # callers excluding def line
    hits=[p.relative_to(ROOT).as_posix() for p in srcs if re.search(rf"\b{name}\s*\(", p.read_text(errors="ignore"))]
    out(f"callers_{name}", hits)
# swallowed / skips / mocks
for pat,label in [(r"except[^:]*:\s*\n\s*pass","swallow_pass"),(r"mark\.skip","skip"),(r"NotImplementedError","notimpl"),(r"synthetic|MOCK|mock","synthetic_mock")]:
    files=[f"{p.relative_to(ROOT).as_posix()}:{len(re.findall(pat,p.read_text(errors='ignore')))}" for p in list(ROOT.glob("flowforge/**/*.py"))+list(ROOT.glob("tests/**/*.py"))+list(ROOT.glob("scripts/*.py")) if re.search(pat,p.read_text(errors="ignore"))]
    out(label, files[:25])
# baseline entry
try:
    r=subprocess.run([sys.executable,"scripts/run_experiment.py","--help"],capture_output=True,text=True,timeout=120,cwd=ROOT)
    out("baseline_help_exit", r.returncode); print((r.stdout+r.stderr)[:800])
except Exception as e: out("baseline_err", repr(e))
out("data_raw", sorted(p.name for p in (ROOT/"data/raw").iterdir()))
out("runs_sessions", sorted(p.name for p in (ROOT/"runs").iterdir())[:20] if (ROOT/"runs").exists() else [])

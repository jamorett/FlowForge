"""Round-2 Phases 4-6 probe. Run: python audit/probes/r2p456-probe.py"""
import importlib.util, inspect, json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
out = {}
# composer kernel
try:
    import numpy as np
    from flowforge.composer.gates import compose, sigmoid
    c, pen = compose(np.ones(2), np.zeros(2), np.array([0.0, 1.0]), w=1.0, b=0.0)
    out["compose_values"] = [round(float(x), 6) for x in c]
    out["compose_penalty"] = pen
    out["compose_expected"] = [0.5, round(1/(1+2.718281828459045**-1), 6)]
except Exception as e:
    out["compose_error"] = f"{type(e).__name__}: {e}"
# zip bug: 3 zero modules, targets [0,0,99]
try:
    import numpy as np
    from flowforge.composer.evaluate import evaluate_composition
    mods = [np.zeros(2), np.zeros(2), np.zeros(2)]
    r = evaluate_composition(mods, [np.zeros(2)]*3, [np.zeros(2), np.zeros(2), np.full(2, 99.0)], 1.0, 0.0)
    out["zip_bug"] = r
except Exception as e:
    out["zip_bug_error"] = f"{type(e).__name__}: {e}"
# penalty dropped from elegance
try:
    from flowforge.elegance.engine import description_length
    out["dl_params"] = list(inspect.signature(description_length).parameters)
    src = (ROOT/"flowforge/elegance/engine.py").read_text()
    out["dl_has_gate"] = "gate" in src.lower()
    out["round_imports_composer"] = "composer" in (ROOT/"flowforge/orchestrator/round.py").read_text()
except Exception as e:
    out["elegance_error"] = str(e)
# run_arms mock + real via subprocess timeout=120
for args, key in [(["--mock"], "run_arms_mock"), ([], "run_arms_real")]:
    p = subprocess.run([sys.executable, "scripts/run_arms.py", *args], capture_output=True, text=True, timeout=120, cwd=ROOT)
    out[key] = {"exit": p.returncode, "stdout": p.stdout.strip()[:500]}
# tenacity / ModelRuntime / EventLogger
out["tenacity_present"] = importlib.util.find_spec("tenacity") is not None
try:
    from flowforge.agents.runtime.client import ModelRuntime  # noqa
    out["modelruntime_import"] = "OK"
except Exception as e:
    out["modelruntime_import"] = f"{type(e).__name__}: {e}"
try:
    from flowforge.agents.runtime.event_logger import EventLogger
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)/"events.jsonl"
        lg = EventLogger(p)
        from flowforge.agents.runtime.event_logger import prompt_hash
        lg.log({"prompt_hash": prompt_hash("hello"), "response": {"text": "world"}})
        os.environ["FLOWFORGE_REPLAY"] = "1"
        out["replay_hit"] = lg.replay_lookup(prompt_hash("hello"))
        try:
            lg.replay_lookup(prompt_hash("missing-xyz")); out["replay_miss"] = "no-error"
        except Exception as e:
            out["replay_miss"] = f"{type(e).__name__}: {e}"
        del os.environ["FLOWFORGE_REPLAY"]
        out["replay_off"] = lg.replay_lookup(prompt_hash("hello"))
except Exception as e:
    out["eventlogger_error"] = f"{type(e).__name__}: {e}"
# pytest absent
p = subprocess.run([sys.executable, "-m", "pytest", "--version"], capture_output=True, text=True, timeout=120, cwd=ROOT)
out["pytest"] = {"exit": p.returncode, "out": (p.stdout+p.stderr).strip()[:200]}
# OM-7 / OM-2 searches (exclude data/locked, audit)
hits_freeze, hits_metrics = [], []
for base in ["docs", "configs", "flowforge", "scripts"]:
    for f in (ROOT/base).rglob("*"):
        if f.is_file() and f.suffix in {".md", ".yaml", ".yml", ".py", ".txt", ".json"}:
            t = f.read_text(errors="ignore").lower()
            if "feature freeze" in t or "feature_freeze" in t: hits_freeze.append(str(f.relative_to(ROOT)))
            if any(k in t for k in ["schema-valid rate", "schema_valid_rate", "parse rate", "parse_rate", "duplicate rate", "duplicate_rate", "cost per round", "cost_per_round", "per prompt version", "prompt_version"]): hits_metrics.append(str(f.relative_to(ROOT)))
out["om7_feature_freeze_hits"] = hits_freeze[:20]
out["om2_metrics_hits"] = hits_metrics[:20]
plan = ROOT/"docs/plans/2026-10-26-flowforge-v2-implementation-plan.md"
out["plan_exists"] = plan.exists()
if plan.exists():
    lines = plan.read_text(errors="ignore").splitlines()
    out["plan_lines"] = len(lines)
    out["plan_s6_s7_hits"] = [f"{i+1}:{l.strip()[:100]}" for i, l in enumerate(lines) if "S6.2" in l or "S7.1" in l or "feature freeze" in l.lower()][:10]
print(json.dumps(out, indent=1, default=str))

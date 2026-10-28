"""Phase 4 composer probe (numpy-only, independent oracle). No pytest/sympy."""
import pathlib, re, sys
sys.path.insert(0, ".")
import numpy as np

from flowforge.composer.gates import GATE_DL_PENALTY_BITS, compose, sigmoid, total_dl_penalty_bits
from flowforge.composer.evaluate import evaluate_composition
from flowforge.elegance.engine import description_length, pick_champion

rng = np.random.default_rng(42)
fails = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (" " + detail if detail else ""))
    if not cond: fails.append(name)

# 1 formula vs independent oracle
a1, a2 = rng.standard_normal((4,3,3)), rng.standard_normal((4,3,3))
I = rng.standard_normal(4)
out, pen = compose(a1, a2, I, w=0.7, b=-0.2)
g = 1/(1+np.exp(-(0.7*I-0.2)))
exp = g[:,None,None]*a1 + (1-g[:,None,None])*a2
check("formula", np.allclose(out, exp, atol=1e-12), f"maxdiff={np.max(np.abs(out-exp)):.2e}")
check("penalty16", pen == 16.0 and GATE_DL_PENALTY_BITS == 16.0 and total_dl_penalty_bits(3) == 48.0)
check("sigmoid0", float(sigmoid(np.array([0.0]))[0]) == 0.5)
o2,_ = compose(np.ones((2,3,3)), np.zeros((2,3,3)), np.array([1e9,-1e9]), w=1.0, b=0.0)
check("saturation_clip", np.allclose(o2[0],1.0) and np.allclose(o2[1],0.0), f"{o2[0,0,0]},{o2[1,0,0]}")
out3, pen3 = compose(a1, a2, I, 0.7, -0.2)
check("deterministic_D5core", np.array_equal(out, out3) and pen3 == pen)
# scalar gate_input broadcast edge
try:
    os_, _ = compose(a1, a2, np.array(0.5), 1.0, 0.0); check("scalar_gate", os_.shape == a1.shape)
except Exception as e: check("scalar_gate", False, repr(e))

# 2 evaluate: truncation + pairwise-not-joint demonstration
mods = [np.zeros((2,3,3)) for _ in range(3)]
gates = [np.zeros(2) for _ in range(3)]
tgts = [np.zeros((2,3,3)), np.zeros((2,3,3)), np.full((2,3,3), 99.0)]
r = evaluate_composition(mods, gates, tgts, 1.0, 0.0)
print("evaluate_trunc_demo:", r)
# preds are 2 pairwise blends; errors zip(preds,targets) drops targets[2]
check("evaluate_drops_last_target", r["worst_error"] == 0.0 and r["best_single_worst"] > 1000.0 and r["beats_single"] is True)
check("evaluate_n_gates", r["n_gates"] == 2 and r["dl_penalty_bits"] == 32.0)
# pairwise preds are independent blends, not one composite field: return has no composite array at all
check("evaluate_no_composite_output", set(r) == {"worst_error","best_single_worst","dl_penalty_bits","beats_single","n_gates"}, str(sorted(r)))

# 3 elegance integration: DL has no gate argument; champion unaware
src_e = pathlib.Path("flowforge/elegance/engine.py").read_text(encoding="utf-8")
check("dl_no_gate_param", "gate" not in src_e.lower() and "n_gates" not in src_e)
print("dl_example:", description_length(5, [0.5]), "champion:", pick_champion([{"id":"a","worst_error":1.0,"dl":10.0},{"id":"b","worst_error":1.02,"dl":50.0}])["id"])

# 4 fitting absence + reachability (source inspection, corroborated by imports)
src_g = pathlib.Path("flowforge/composer/gates.py").read_text(encoding="utf-8")
src_v = pathlib.Path("flowforge/composer/evaluate.py").read_text(encoding="utf-8")
src_r = pathlib.Path("flowforge/orchestrator/round.py").read_text(encoding="utf-8")
src_reg = pathlib.Path("flowforge/agents/tools/registry.py").read_text(encoding="utf-8")
allpy = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in pathlib.Path("flowforge").rglob("*.py"))
check("no_fit_gates_anywhere", "fit_gates" not in allpy and "def fit_" not in src_g + src_v)
check("no_optimizer_in_composer", not re.search(r"scipy|minimize|least_squares|curve_fit|grid|search", src_g + src_v))
check("round_never_calls_compose", "compose" not in src_r.split('\"\"\"',2)[-1] and "composer" not in src_r.lower().split("composer.",1)[0][-200:] or ("from flowforge.composer" not in src_r and "compose(" not in src_r))
print("round_imports_composer:", "flowforge.composer" in src_r, "| registry_tools_fit_gates:", "fit_gates" in src_reg)
check("registry_no_fit_gates", "fit_gates" not in src_reg)

# 5 configs + training flows
cfg = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in pathlib.Path("configs").rglob("*") if p.is_file())
check("penalty_not_in_configs", "16" not in cfg and "gate" not in cfg.lower().replace("composer: { model",""))
cases = pathlib.Path("configs/cases.yaml").read_text(encoding="utf-8")
print("train_cases:", re.findall(r"id: (\S+)\s+split: train", cases))
print("processed_dir:", [p.name for p in pathlib.Path("data/processed").iterdir()], "modules_dir:", [p.name for p in pathlib.Path("library/modules").iterdir()])
print("FAILS:", fails)
print("PROBE_DONE")

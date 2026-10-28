"""Phase1 offline probe: imports, client params, callers, hand-written candidate, runner logic. No network/Docker/data/locked."""
import ast, importlib, json, pathlib, sys, traceback
root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
out = {}

def try_import(m):
    try:
        importlib.import_module(m); return "OK"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

for m in ["flowforge.agents.runtime.client","flowforge.dsl.evaluate","flowforge.dsl.compiler","flowforge.ladder.ladder","flowforge.solver.runner","flowforge.solver.field_io","flowforge.agents.runtime.event_logger","flowforge.agents.schemas"]:
    out[f"import:{m}"] = try_import(m)

# client params static AST
src = (root/"flowforge/agents/runtime/client.py").read_text(encoding="utf-8")
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in ("complete","_complete_live","complete_structured","__init__"):
        out[f"client:{node.name}:args"] = [a.arg for a in node.args.args]
out["client:has_temperature_param"] = "temperature" in src.split("def complete")[1].split("def ")[0] if "def complete" in src else False
out["client:hardcoded_response_format"] = 'response_format={"type": "json_object"}' in src
out["client:uses_budgets_yaml"] = "budgets.yaml" in src or "budgets" in src
out["client:uses_reasoning_effort"] = "reasoning_effort" in src or "reasoning" in src
out["client:max_tokens_passed"] = "max_tokens=max_tokens" in src
# budgets.yaml values
out["budgets_text"] = (root/"configs/budgets.yaml").read_text(encoding="utf-8")[:500]

# callers via text search (exclude audit, pycache, .git)
for pat in ["OpenFOAMSolverRunner","ModelRuntime","read_fields","write_correction_fields","run_ladder","candidate_anisotropy"]:
    hits=[]
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in ("audit","__pycache__",".git")): continue
        try: t=p.read_text(encoding="utf-8",errors="replace")
        except: continue
        if pat in t: hits.append(str(p.relative_to(root)))
    out[f"callers:{pat}"] = hits

# hand-written candidate text->a priori attempt (needs sympy)
try:
    from flowforge.ladder.ladder import rung1_scores
    import numpy as np
    inv={f"I{i}": np.zeros(4) for i in range(1,6)}
    basis={"T1": np.zeros((4,3,3))}
    out["handwritten_apriori"] = str(rung1_scores(["0"], inv, basis, np.zeros((4,3,3))))
except Exception as e:
    out["handwritten_apriori"] = f"FAIL {type(e).__name__}: {e}"

# runner pure logic (numpy only)
try:
    from flowforge.solver.runner import residuals_converged, compute_run_hash, timeout_for_mode
    out["runner:converged_ok"] = residuals_converged({"p":1e-5,"Ux":1e-5})
    out["runner:missing_p"] = residuals_converged({"Ux":1e-5})
    out["runner:hash_len"] = len(compute_run_hash("a","b",{}))
    out["runner:timeout_short"] = timeout_for_mode("short")
except Exception as e:
    out["runner:logic"] = f"FAIL {e} {traceback.format_exc()}"

# templates check
bm = (root/"openfoam/templates/periodicHill/system/blockMeshDict").read_text(encoding="utf-8")
out["blockmesh:flat_placeholder"] = "flat walls" in bm
out["blockmesh:cyclic"] = bm.count("type cyclic")
tp = (root/"openfoam/templates/periodicHill/constant/turbulenceProperties").read_text(encoding="utf-8")
out["turb:kOmegaSST_baseline_not_corrected"] = ("RASModel        kOmegaSST" in tp, "corrected" in tp)
out["make_files_exists"] = (root/"openfoam/src/correctedKOmegaSST/Make/files").exists()
out["periodicHill_files"] = sorted(str(p.relative_to(root)) for p in (root/"openfoam/templates/periodicHill").rglob("*") if p.is_file())
out["data_raw"] = sorted(str(p.relative_to(root)) for p in (root/"data/raw").rglob("*"))
out["cpp:modeB_default_zero"] = "return scalar(0)" in (root/"openfoam/src/correctedKOmegaSST/correctedKOmegaSST.H").read_text(encoding="utf-8")
cpp=(root/"openfoam/src/correctedKOmegaSST/correctedKOmegaSST.C").read_text(encoding="utf-8")
out["cpp:nut_surrogate"] = "nut_" in cpp and "deltaNut" in cpp
out["cpp:equation_injection_kOmega"] = ("kEqn" in cpp or "omegaEqn" in cpp or "correctNut" in cpp)

print(json.dumps(out, indent=1, default=str))

"""Phase 5 probe: mock arms only; never runs evaluate_locked or real arms."""
import json, pathlib, re, subprocess, sys
root = pathlib.Path(__file__).resolve().parents[2]
def run(cmd):
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)
    return {"cmd": cmd, "exit": r.returncode, "out": (r.stdout+r.stderr).strip()[:2000]}
out = {}
out["run_arms_mock"] = run([sys.executable, "scripts/run_arms.py", "--mock"])
# summarize formula check by import via runpy namespace without main
import importlib.util
spec = importlib.util.spec_from_file_location("run_arms", root/"scripts/run_arms.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out["arms_seeds"] = {"ARMS": m.ARMS, "SEEDS": m.SEEDS, "summarize_mock_swarm": m.summarize([float((s%7)+len("swarm")) for s in m.SEEDS])}
out["files"] = {p: (root/p).exists() for p in ["scripts/reproduce_champion.py","scripts/run_experiment.py","notebooks/.gitkeep","runs/vault_access.log","data/raw/manifest.json"]}
out["library"] = sorted(str(p.relative_to(root)) for p in (root/"library").rglob("*"))
out["notebooks"] = sorted(str(p.relative_to(root)) for p in (root/"notebooks").rglob("*"))
out["tests_science"] = sorted(str(p.relative_to(root)) for p in (root/"tests/science").rglob("*"))
out["runs"] = sorted(str(p.relative_to(root)) for p in (root/"runs").rglob("*"))
# text searches (no locked data access)
pats = {"library_load_save": r"library/(modules|findings|rejected)|load.*library|save.*module|ModuleLibrary|verified|champion.*lifecycle|stale|re-?verif",
        "mesh_refine": r"mesh.*refin|refin.*mesh|2x|double.*resol",
        "results_table": r"results table|mean.*stdev|mean.*spread"}
for name, pat in pats.items():
    hits=[]
    for p in root.rglob("*.py"):
        if any(x in str(p) for x in ["node_modules",".git","audit"]): continue
        for i,l in enumerate(p.read_text(encoding="utf-8",errors="replace").splitlines(),1):
            if re.search(pat,l,re.I): hits.append(f"{p.relative_to(root)}:{i}:{l.strip()[:140]}")
    out[name]=hits[:30]
# guard behaviour in tmp-like paths: only non-locked allowed + locked denied (writes runs/vault_access.log DENIED - acceptable probe side effect? use monkey by importing and patching LOG)
sys.path.insert(0,str(root))
import flowforge.data.split_guard as sg
orig=sg.LOG
tmp=root/"audit"/"probes"/"_phase5_vault.log"
sg.LOG=tmp
try:
    try: sg.guard_path(pathlib.Path("data/locked/x"), role="auditor"); out["guard_locked"]="ALLOWED-BUG"
    except PermissionError as e: out["guard_locked"]=f"PermissionError: {e}"
    out["guard_normal"]=str(sg.guard_path(pathlib.Path("data/raw/x.npy"), role="auditor"))
    out["guard_log"]=tmp.read_text(encoding="utf-8") if tmp.exists() else ""
finally:
    sg.LOG=orig
    if tmp.exists(): tmp.unlink()
# cases
out["cases_yaml"]=(root/"configs/cases.yaml").read_text(encoding="utf-8")
out["download_CASES_line"]=[l for l in (root/"scripts/download_data.py").read_text(encoding="utf-8").splitlines() if "periodic_hill" in l or "CASES" in l]
out["evaluate_locked_src"]=(root/"scripts/evaluate_locked.py").read_text(encoding="utf-8")
out["reproduce_src"]=(root/"scripts/reproduce_champion.py").read_text(encoding="utf-8")
# git ls-files locked existence only
out["git_locked"]=run(["git","-c","safe.directory=C:/Users/juanc/Desktop/FlowForge","ls-files","data/locked"])
out["git_status_short"]=run(["git","-c","safe.directory=C:/Users/juanc/Desktop/FlowForge","status","--short"])
print(json.dumps(out,indent=2))

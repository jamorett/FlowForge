import subprocess, sys, pathlib, json
R=pathlib.Path.cwd()
def run(a):
    try:
        p=subprocess.run(a,capture_output=True,text=True,timeout=120,cwd=str(R))
        return p.returncode,(p.stdout+p.stderr)[-600:]
    except Exception as e:
        return type(e).__name__,str(e)
out={}
out['plan_exists']=(R/'docs/plans/2026-10-26-flowforge-v2-implementation-plan.md').exists()
out['plan_lines']=len((R/'docs/plans/2026-10-26-flowforge-v2-implementation-plan.md').read_text(encoding='utf-8').splitlines()) if out['plan_exists'] else 0
out['blockmesh']=(R/'openfoam/templates/periodicHill/system/blockMeshDict').read_text(encoding='utf-8')[:400]
out['hill_files']=sorted(str(p.relative_to(R)) for p in (R/'openfoam/templates/periodicHill').rglob('*') if p.is_file())
out['run_experiment_help']=run([sys.executable,'scripts/run_experiment.py','--help'])
out['gate_logic']=run([sys.executable,'audit/probes/gate_logic_probe.py'])
out['pytest']=run([sys.executable,'-m','pytest','--collect-only','-q'])
for k in ['docker','uv']:
    try:
        p=subprocess.run([k,'--version'],capture_output=True,text=True,timeout=120); out[k]=(p.returncode,p.stdout+p.stderr)
    except Exception as e: out[k]=(type(e).__name__,str(e))
# budgets enforcement search (no data/locked)
import re
txt=[]
for p in list((R/'flowforge').rglob('*.py'))+list((R/'scripts').glob('*.py')):
    t=p.read_text(encoding='utf-8',errors='ignore')
    if 'max_solver_runs_per_round' in t or 'budgets.yaml' in t or 'solver_caps' in t: txt.append(str(p.relative_to(R)))
out['budgets_loaders']=txt
c=(R/'flowforge/agents/runtime/client.py').read_text(encoding='utf-8')
out['client_has_check_budget']='check_budget' in c; out['client_SESSION_LIMIT']='SESSION_LIMIT = 50.00' in c
r=(R/'flowforge/solver/runner.py').read_text(encoding='utf-8')
out['runner_timeout_caps']=('SHORT_TIMEOUT_SECONDS = 60.0' in r,'FULL_TIMEOUT_SECONDS = 300.0' in r,'timeout_seconds <= 300.0' in r)
try:
    import sympy; out['sympy']='present'
except Exception as e: out['sympy']=f'{type(e).__name__}: {e}'
print(json.dumps(out,indent=2,default=str))

import json, pathlib
R=pathlib.Path.cwd()
p0=json.loads((R/'audit/round-1/phase-0.json').read_text(encoding='utf-8'))
p1=json.loads((R/'audit/round-1/phase-1.json').read_text(encoding='utf-8'))
probe="audit/probes/r2p01-probe.py exit 0 (subprocess.run timeout=120): plan_exists=True plan_lines=489; run_experiment --help exit 1 ModuleNotFoundError flowforge; gate_logic exit 0 4 PASS; pytest exit 1 No module named pytest; docker/uv FileNotFoundError; sympy ModuleNotFoundError; budgets_loaders=[]"
# Phase0 updates
for r in p0:
    r.setdefault('gap','none')
    if r['id']=='P0-12':
        r['evidence']+=f"; round-2: {probe}"
        r['gap']="BLOCKED_BY_ENV: exact user commands outside sandbox: `uv sync` then `docker run --rm opencfd/openfoam-default:latest simpleFoam -help` then `uv run python scripts/download_data.py --synthetic-fallback` (or real fetch) then `uv run python scripts/run_experiment.py --config configs/experiments/baseline.yaml`; success requires converged profile error vs dataset RANS <0.05 on curved mesh (P1-03). Fresh probe: run_experiment --help exit 1 No module named 'flowforge', docker/uv absent."
    if r['id'] in ('P0-02','P0-05','P0-06','P0-09','P0-15'):
        r['evidence']+=f"; round-2 CH-12 spot-check: {probe}"
        # status unchanged PRESENT_UNTESTED
p0.append({"id":"P0-19","requirement":"OM-6 Solver-run caps per round + session dollar pause as enforced behaviour (spec Guardrails; configs/budgets.yaml solver_caps + session_dollar_limit)","status":"SKELETON","evidence":f"configs/budgets.yaml:1,10-13 session_dollar_limit=50.00, max_solver_runs_per_round=10, 60s/300s caps; flowforge/solver/runner.py:20-31,99,166-168 timeout caps 60/300 asserted in code; flowforge/agents/runtime/client.py:19,65-68,119-120 hardcoded SESSION_LIMIT=50.00 check_budget pre-call (fixed 0.01 est) + post-spend BudgetExceededError; round-2 probe budgets_loaders=[] (no budgets.yaml/solver_caps loader), client unimportable here (tenacity absent per round-1 P1-15)","gap":"Per-round solver-run count (10) never enforced/counted anywhere; dollar pause is hardcoded duplicate not budgets.yaml-driven, per-role caps absent, and neither path executed in this env (no pytest/docker). Enforce via loading budgets.yaml in runner/orchestrator + ModelRuntime and test cap-exceeded pause."})
# Phase1 updates
for r in p1:
    r.setdefault('gap','none')
    if r['id']=='P1-02':
        r['status']='PRESENT_UNTESTED'
        r['evidence']+=f"; round-2 CH-01 downgrade: {probe}; blockMeshDict header flat walls placeholder"
        r['gap']="Files exist, flat mesh, never run: files exist but never meshed/run; no blockMesh/simpleFoam log on curved/dataset mesh (Docker absent). Downgraded VERIFIED->PRESENT_UNTESTED per CH-01."
    if r['id'] in ('P1-08','P1-10'):
        r['evidence']+=f"; round-2 held (verifier s4): gate_logic re-run exit 0 PASS; scope logic only, solver counterpart BLOCKED_BY_ENV"
        r['gap']=r['gap']+" Scope: logic only (held in verifier s4); solver identity/oracle remain BLOCKED_BY_ENV."
    if r['id'] in ('P1-07','P1-12'):
        r['evidence']+=f"; round-2 CH-08: {probe}"
        r['gap']=r['gap']+" CH-08 proof needed outside sandbox: `uv sync` then hand-written candidate -> rung-1 on real Zarr, and generated candidate compiled timed/hash-cached <90s; sympy absent here (probe ModuleNotFoundError)."
    if r['id']=='P1-13':
        r['evidence']+=f"; round-2 CH-08/CH-10: {probe}"
        r['gap']="BLOCKED_BY_ENV: exact user commands: `uv sync` then `uv run python scripts/run_experiment.py --config configs/experiments/baseline.yaml` and `uv run pytest tests/integration -k \"identity_solver or oracle_solver\" -v` after Docker+curved mesh+dataset; here sympy absent, run_experiment exit 1 flowforge not installed."
    if r['id']=='P1-05':
        r['evidence']+=f"; round-2 CH-10: {probe}"
        r['gap']="BLOCKED_BY_ENV: exact user commands: `uv sync`; `docker run --rm opencfd/openfoam-default:latest simpleFoam -help`; fetch dataset (real or `uv run python scripts/download_data.py --synthetic-fallback`); `uv run python scripts/run_experiment.py --config configs/experiments/baseline.yaml` must print converged error <0.05 vs dataset RANS on curved mesh."
    if r['id'] in ('P1-04','P1-06','P1-16','P1-17'):
        r['evidence']+=f"; round-2 CH-12: no execution upgrade without pytest run; {probe}"
(R/'audit/round-2/phase-0.json').write_text(json.dumps(p0,indent=2),encoding='utf-8')
(R/'audit/round-2/phase-1.json').write_text(json.dumps(p1,indent=2),encoding='utf-8')
print(len(p0),len(p1))
from collections import Counter
print(Counter(r['status'] for r in p0)); print(Counter(r['status'] for r in p1))
print('unique',len({r['id'] for r in p0}),len({r['id'] for r in p1}))

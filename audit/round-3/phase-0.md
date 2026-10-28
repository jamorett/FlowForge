# Phase 0 (S0) audit — Round 2 (rebuilt final)

Scope: spec Phase 0 + plan S0. Rows: [phase-0.json](phase-0.json) `P0-01`…`P0-19` (round-1 `P0-01`…`P0-18` rebuilt plus OM-6 row `P0-19`). Base: [round-1 phase-0](../round-1/phase-0.md). Probe: [r2p01-probe.py](../probes/r2p01-probe.py) exit 0 via `subprocess.run(timeout=120)` — plan exists (489 lines), `scripts/run_experiment.py --help` exit 1 `No module named 'flowforge'`, pytest exit 1, docker/uv `FileNotFoundError`, gate-logic exit 0. `data/locked/` never opened. No installs/network/Docker.

Gate verdict: **FAIL / frozen-RANS-only** (unchanged). See [GATE.md](../GATE.md).

## Round-2 challenge responses

- CH-01: UPHELD (Phase-1 scope, noted here) — P1-02 downgraded; no Phase-0 row claimed a meshed/run solver. Evidence: [r2p01-probe.py](../probes/r2p01-probe.py) flat-walls header, docker absent.
- CH-08: UPHELD (Phase-1 scope) — compile/a-priori path blocked (sympy absent in probe); no Phase-0 upgrade made.
- CH-10: UPHELD — `P0-12` stays `BLOCKED_BY_ENV`. Fresh evidence: probe `run_experiment --help` exit 1 `ModuleNotFoundError: No module named 'flowforge'`; docker/uv absent. Exact user commands in `P0-12.gap`: `uv sync`; `docker run --rm opencfd/openfoam-default:latest simpleFoam -help`; dataset fetch; `uv run python scripts/run_experiment.py --config configs/experiments/baseline.yaml` (needs converged error <0.05 on curved mesh).
- CH-12: UPHELD — `P0-02, P0-05, P0-06, P0-09, P0-15` stay `PRESENT_UNTESTED`; no upgrade without a `uv run pytest`/CLI exit 0. Probe confirms pytest/docker/uv absent and `budgets_loaders=[]`.
- CH-14: REBUTTED (plan sub-claim) + UPHELD (OM-6 omission) — verifier said no plan file exists in repo; probe shows [implementation plan](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:1) exists, 489 lines, so round-1 `plan L###` citations are verifiable from checkout. OM-6 was genuinely absent: added as `P0-19` (`SKELETON` — timeout caps in [runner.py](../../flowforge/solver/runner.py:20) and hardcoded dollar check in [client.py](../../flowforge/agents/runtime/client.py:19), but `max_solver_runs_per_round` in [budgets.yaml](../../configs/budgets.yaml:10) has zero loaders/enforcement and nothing was executed).

## Signed account

Counts per status (19 rows): VERIFIED 0 · PRESENT_UNTESTED 5 (P0-02, P0-05, P0-06, P0-09, P0-15) · SKELETON 5 (P0-07, P0-08, P0-10, P0-13, P0-19) · MISSING 3 (P0-03, P0-16, P0-17) · BLOCKED_BY_ENV 5 (P0-01, P0-04, P0-11, P0-12, P0-14) · DECISION_NEEDED 1 (P0-18).

Top 5 gaps: 1) No dataset/manifest (P0-08/P0-16). 2) No `uv.lock`/uv env (P0-03/P0-04). 3) No Docker/OpenFOAM run, unpinned scaffold image (P0-10/P0-11/P0-12). 4) Orphaned budgets/cases/experiment configs, incl. unenforced per-round solver cap (P0-05/P0-06/P0-19). 5) Tolerances/model IDs unfrozen (P0-17/P0-18).

Not checked: `data/locked/` (forbidden), `.env` values, live Kaggle/Meta/GitHub, Docker on a Docker host, `uv sync` resolution, Phase 2+ behaviour.

Confidence: high on file/env facts (fresh probe exit codes observed); zero on solver runtime (never run here). Challenges: upheld 4 (CH-01, CH-08, CH-10, CH-12 — CH-01/CH-08 Phase-1-scoped), rebutted 1 in part (CH-14 plan claim rebutted; its OM-6 omission upheld and added as P0-19).

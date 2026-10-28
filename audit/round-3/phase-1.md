# Phase 1 (S1/S2/S4a) audit — Round 2 (rebuilt final)

Scope: spec Phase 1 + plan S1/S2/S4a. Rows: [phase-1.json](phase-1.json) `P1-01`…`P1-18` rebuilt from [round-1 phase-1](../round-1/phase-1.md). Probe: [r2p01-probe.py](../probes/r2p01-probe.py) exit 0 via `subprocess.run(timeout=120)` — gate-logic 4 PASS, pytest exit 1, docker/uv absent, sympy absent, periodicHill files listed, flat-walls header. `data/locked/` never opened. No installs/network/Docker/API.

Gate verdict: **FAIL (full-solver) / frozen-RANS-only** (unchanged, [GATE.md](../GATE.md)).

## Round-2 challenge responses

- CH-01: UPHELD — `P1-02` downgraded `VERIFIED -> PRESENT_UNTESTED`, gap reads 'files exist, flat mesh, never run'. Evidence: probe lists 12 periodicHill files and reads [blockMeshDict](../../openfoam/templates/periodicHill/system/blockMeshDict:10) flat-walls placeholder header; Docker absent so no `blockMesh`/`simpleFoam` log can exist here. Cannot prove meshed/run — Docker absent.
- CH-08: UPHELD — `P1-07/P1-12` stay `SKELETON`, `P1-13` stays `BLOCKED_BY_ENV`. Probe: `sympy ModuleNotFoundError`; `compile_cpp` has no wmake caller (round-1). Exact user commands in gaps: `uv sync`, then hand-written candidate → rung-1 on real Zarr and one generated candidate timed/hash-cached <90s, plus `uv run pytest tests/integration -k "identity_solver or oracle_solver" -v`.
- CH-10: UPHELD — `P1-05` (and Phase-0 `P0-12`) stay `BLOCKED_BY_ENV`. Probe: `scripts/run_experiment.py --help` exit 1 `No module named 'flowforge'`. Exact user commands in `P1-05.gap`: `uv sync`; `docker run --rm opencfd/openfoam-default:latest simpleFoam -help`; dataset fetch; `uv run python scripts/run_experiment.py --config configs/experiments/baseline.yaml` requiring converged error <0.05 vs dataset RANS on curved mesh.
- CH-12: UPHELD — `P1-04, P1-06, P1-16, P1-17` stay `PRESENT_UNTESTED`; no file-existence upgrade without the row's own pytest/CLI exit 0.
- CH-14: REBUTTED (plan sub-claim) + UPHELD (OM-6) — verifier said plan not in repo; [implementation plan](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:1) exists (probe: 489 lines), so plan citations are checkout-verifiable. OM-6 added in Phase 0 as `P0-19`. `P1-08/P1-10` kept `VERIFIED` per verifier §4 held — logic only, scope noted in evidence/gap; solver counterparts `P1-09/P1-11` remain `BLOCKED_BY_ENV`.

## Signed account

Counts per status (18 rows): VERIFIED 2 (P1-08, P1-10 — logic only, held §4) · PRESENT_UNTESTED 5 (P1-02 downgraded, P1-04, P1-06, P1-16, P1-17) · SKELETON 3 (P1-07, P1-12, P1-18) · MISSING 0 · BLOCKED_BY_ENV 7 (P1-01, P1-05, P1-09, P1-11, P1-13, P1-14, P1-15) · DECISION_NEEDED 1 (P1-03).

Top 5 gaps: 1) Docker+dataset+pytest env absent (P1-01/P1-05). 2) Flat placeholder mesh, curved-mesh decision open (P1-03/P1-02). 3) Mode A nut-surrogate, no equation injection or .npy→OpenFOAM bridge, never compiled (P1-06). 4) Mode B/codegen compile+timing pipeline absent, sympy blocked (P1-07/P1-12/P1-13). 5) Client import blocked (tenacity) and budgets.yaml/temperature/reasoning unwired (P1-15/P1-18).

Not checked: `data/locked/` (forbidden), live Meta API, Docker/wmake compile, real dataset fields, UI, Phase 2+ rungs beyond code reading.

Confidence: high on file/env/logic facts (probe exit 0, gate-logic 4 PASS re-run); low/zero on solver physics (never compiled/run). Challenges: upheld 4 (CH-01, CH-08, CH-10, CH-12), rebutted 1 in part (CH-14 plan claim rebutted with plan-file evidence; OM-6 omission upheld, added as P0-19 in Phase 0).

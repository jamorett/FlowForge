# FlowForge v2 Phase 1 audit (S1, S2, S4a) — Round 1

Scope: spec Phase 1 (Oct 26-27) + plan S1/S2/S4a. Read-only; probes only `audit/probes/phase1-gate-probe.py` (subprocess timeout=120, exit 0). `project_status.md` treated as unverified. `data/locked/` never opened. No installs/network/Docker/Meta API.

## Gate exact check (offline)

Spec gate: *oracle test passes AND hand-written candidate text -> a priori score end to end*.

| Gate half | Result | Evidence |
|---|---|---|
| Oracle solver | UNVERIFIABLE (blocked) | `test_oracle_solver` skipped `tests/integration/test_oracle.py:72-74`; Docker absent (127), dataset absent, pytest absent (exit 1, re-run this session) |
| Hand-written -> a priori | FAIL in this env | Probe: `handwritten_apriori=FAIL ModuleNotFoundError: sympy` via `ladder.rung1_scores -> dsl.evaluate.candidate_anisotropy` |
| Logic surrogates | PASS | `gate_logic_probe.py` re-run exit 0: 4 PASS (identity x2, oracle x2) — arithmetic only, labelled NOT solver results |

**Gate verdict: FAIL (offline) / UNVERIFIABLE as solver claim.** Frozen-RANS-only confirmed (see P4). Do not claim full-solver Phase 1.

## Requirements (P1-01..P1-18)

Full rows in `phase-1.json`. Highlights with reachability:

- **S1 runner** ([runner.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/solver/runner.py)): logic sound (residual gate, 60/300s caps, hash cache proven by probe), but only caller is [run_experiment.py](/C:/Users/juanc/Desktop/FlowForge/scripts/run_experiment.py), which ignores `--config` content. Orchestrator never calls it. PRESENT_UNTESTED.
- **S2 C++** ([correctedKOmegaSST.C](/C:/Users/juanc/Desktop/FlowForge/openfoam/src/correctedKOmegaSST/correctedKOmegaSST.C)): **Mode A is nut-surrogate, not equation injection.** Zero field early-returns (identity plausible). Non-zero: `deltaNut=2*k*mag(aDelta)/max(omega,1e-6)`, `nut_*pkFactor`; own comment admits this. No `kEqn/omegaEqn/correctNut`. Production clamp and guarded denom are real helper code but only feed the surrogate factor. **Mode B is not real**: header hook returns `scalar(0)`, no codegen insertion. SKELETON.
- **Identity/oracle tests**: reconciled with stub-scan — logic tests VERIFIED (probe exit 0), solver tests at `test_identity.py:50-52`, `test_oracle.py:72-74` skipped+NotImplementedError. No contradiction.
- **S4a client** ([client.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/agents/runtime/client.py)): **cannot import here** (`tenacity` missing, import-smoke 47/56). Code has retries/budget/repair, but env-blocked. Event logger + schemas import OK, PRESENT_UNTESTED (pytest absent).
- **Dependencies on Phase 0**: Docker, dataset, uv/pytest env all absent — Phase 1 solver work is downstream-blocked, not code-absent.

## Finding verdicts (this phase)

| Finding | Verdict | Evidence |
|---|---|---|
| P1 data/raw only .gitkeep | CONFIRMED | Probe `data_raw=[data/raw/.gitkeep]`; no DNS/RANS fields |
| P4 gate frozen-only | CONFIRMED | GATE.md decision + this session: gate_logic exit 0 (logic only), pytest exit 1, Docker 127, oracle solver skipped. Hard Decision Rule (plan L285) fires |
| D4 flat placeholder vs curved hill | CONFIRMED, DECISION_NEEDED | `blockMeshDict:10-11` self-labels flat placeholder; `hill_geometry.py` exists but generates no mesh. Owner A decision required before any baseline comparison |
| P2 templates empty | PARTLY REFUTED | periodicHill NOT empty (12 files, probe list) — `project_status.md:45,66-68` wrong. Other templates (channel/bump/flatPlate/squareDuct) only `.gitkeep` — that part goes to Phase 2/3, noted here |
| C3 client params used | PARTLY CONFIRMED (gap) | Used: `max_tokens` (passed), hardcoded `response_format=json_object`. NOT used: `temperature`, `reasoning_effort`/`reasoning`, per-role `budgets.yaml` (never read; AST probe). Global $50 limit only, fixed $0.01 pre-estimate |

Also corrected: `Make/files`+`Make/options` exist — `project_status.md:70,86` wrong (GATE.md already noted).

## Signed account

- Counts: VERIFIED 3 (P1-02, P1-08, P1-10), PRESENT_UNTESTED 4 (P1-04, P1-06, P1-16, P1-17), SKELETON 3 (P1-07, P1-12, P1-18), MISSING 0, BLOCKED_BY_ENV 7 (P1-01, P1-05, P1-09, P1-11, P1-13, P1-14, P1-15), DECISION_NEEDED 1 (P1-03). Total 18.
- Gate: FAIL offline / UNVERIFIABLE solver-side; frozen-only.
- Top 5 gaps: (1) Docker+dataset+pytest env absent; (2) curved mesh decision D4; (3) Mode A nut-surrogate vs equation injection + .npy bridge; (4) Mode B/codegen compile+timing pipeline absent; (5) client import blocked + budgets.yaml/temperature/reasoning unwired.
- Not checked: live Meta API, Docker/wmake compile, real dataset fields, UI, Phase 2+ rungs beyond rung1 code reading, `data/locked/` (forbidden).
- Confidence: High on file/env facts (all probe-backed, exit codes observed); low on solver physics (never compiled/run — by design of this env).

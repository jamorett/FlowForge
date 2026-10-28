# Phase 5 audit — S7.1–S7.3 experiments (Round 2)

Scope: spec Phase 5, plan S7.1–S7.3. Rows: [phase-5.json](phase-5.json) P5-01..P5-17. Probe: [r2p456-probe.py](../probes/r2p456-probe.py) exit 0. `data/locked/` never opened (existence only via git, Round 1). No installs/network/Docker/API. `evaluate_locked.py` not run (would consume budget).

## Gate verdict: FAIL

0/9 real runs, 0 locked scores, no mesh check, no results table. Mock numbers are bookkeeping only.

## Round-2 challenge responses

- **CH-03 — UPHELD. P5-05 downgraded VERIFIED → PRESENT_UNTESTED.** Fresh probe (`subprocess.run(timeout=120)`): `--mock` exit 0 gives `swarm 6.0 [5,6,7]`, `swarm_no_redteam 17.0`, `sparse_baseline 16.0` — `len(arm)/seed` formula at [run_arms.py:29](../../scripts/run_arms.py:29); real mode returns `needs verified S1-S6`. Choice justified: PRESENT_UNTESTED, not SKELETON, because `summarize()` (3-seed assert, mean/stdev) is real executable bookkeeping re-executed here — more than shape — but with no pytest pass and no solver/DNS content it is not VERIFIED. Requirement now labels it **bookkeeping-only, never reportable as results**; quoting these means as results would be synthetic-as-real.
- **CH-12 — UPHELD for P5-08.** Kept PRESENT_UNTESTED; guard function real but unenforced at tool boundaries, no pytest run (probe pytest exit 1).
- **CH-14 (OM-2) — UPHELD, row added in this phase.** P5-17 MISSING: probe hits only plan text and [thresholds.py:4](../../flowforge/agents/evals/thresholds.py:4) `RESEARCH_MIN_PARSE_RATE=0.95` (threshold constant, not per-prompt-version tracking). OM-2 fits Phase 5 as experiment/agent-quality reporting, so it is a Phase-5 row, not deferred to Phase 6.
- **CH-14 (plan missing) — REBUTTED in part.** Plan exists at [docs/plans/2026-10-26-flowforge-v2-implementation-plan.md](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md) (489 lines; S7.1:426). OM-row omissions remain UPHELD.
- **CH-02/CH-06 — not in this phase** (see phase-6/phase-4 Round-2 files).

## Signed account

Counts (17 rows): VERIFIED 0, PRESENT_UNTESTED 2 (P5-05 downgraded, P5-08), SKELETON 4 (P5-01, P5-02, P5-06, P5-11), MISSING 9 (P5-03, P5-04, P5-07, P5-09, P5-10, P5-12, P5-14, P5-15, P5-17), BLOCKED_BY_ENV 1 (P5-16), DECISION_NEEDED 1 (P5-13). Gate Phase 5: **FAIL**. Top gaps: (1) no arms harness/budgets; (2) locked evaluator scores nothing; (3) no cross-session library; (4) no mesh check; (5) no per-prompt-version agent metrics (OM-2). Not checked: evaluate_locked execution, real arms, locked data, Docker/solver, live API. Confidence: high on code/disk/mock behaviour.
Signed account

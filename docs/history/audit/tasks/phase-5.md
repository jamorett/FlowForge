# Tasks — Phase 5 (S7.1–S7.3 experiments)

Owners: A = physics/OpenFOAM, B = agents/API/UI (plan l.75).
Do not start gate tasks until S1–S6 gates pass or GATE.md's
frozen-RANS substitute is explicitly declared. Never exceed 3 locked
evaluations total; never run `evaluate_locked.py` in audit/CI sandboxes.

## T5.1 Decide D5 + D3 before any run (A+B, lead)

- Files: decision note in `docs/`; `scripts/reproduce_champion.py`
  contract; `configs/cases.yaml` provenance comment.
- Dep: none. Fixes P5-11/P5-13 decision halves.
- Acceptance: D5 recorded as replay+hash reproduction (not live
  re-call); D3 checked against real curated manifest + Closure
  Challenge README test list (outside sandbox) → `re10595` train
  provenance stated with manifest hash.
- Hours: 3. Owner: A+B. Risk: high — adverse D3 answer invalidates
  the periodic-hill held-out claim and forces a split change.

## T5.2 Cross-session library module (B)

- Files: new `flowforge/library/` (load/save one file per module in
  `library/modules/`, lifecycle candidate→verified→champion/demoted,
  `library/rejected/` hash dedup, `library/findings/` links, stale
  marking on solver/mesh/case-set hash change); board summary +
  theorist reuse callers in `flowforge/orchestrator/round.py`;
  extend `flowforge/redteam/attacks.py:20` to store score/baseline
  and re-run suite on verified modules.
- Dep: Phase 2 champion pool. Fixes P5-12 (P3).
- Acceptance: `pytest tests/unit -k library` → save→load round-trip,
  lifecycle transitions, stale-on-hash-change, rejected dedup all pass.
- Hours: 12. Owner: B (A reviews scope/evidence fields). Risk: medium.

## T5.3 Real arms harness, 3×3, same budget (A+B)

- Files: `scripts/run_arms.py` (real mode: per arm×seed session dir
  under `runs/`, seed 42/43/44 passed + logged, budget from
  `configs/budgets.yaml`, solver-budget cap shared); flesh out
  `configs/experiments/{swarm,swarm_no_redteam,sparse_baseline}.yaml`
  (budget/cases/seeds); add SST + a-priori-only baselines per spec
  l.277; `scratch/probe_seed.py` (plan l.440).
- Dep: T5.2, S1–S6 gates (or declared frozen substitute). Fixes
  P5-01…P5-05, P5-14 (RP1/RP2 inputs).
- Acceptance: probe_seed: two same-seed replay runs → identical
  candidate hashes; then 9 run dirs each with hashes, scores, seed,
  budget spend; `summarize` table emitted with losses included.
- Hours: 16. Owner: B lead, A solver budget. Risk: high — upstream
  solver/dataset still BLOCKED_BY_ENV (GATE.md).

## T5.4 Locked evaluator that scores (A)

- Files: `scripts/evaluate_locked.py` (validate milestone ∈
  {1,2,final}, fixed metric pre-registered in `configs/`, score
  locked cases via evaluator-only path, append score+hash to log);
  wire `flowforge/data/split_guard.py` into agent tools.
- Dep: locked dataset present (outside sandbox), T5.1, champion
  from T5.3. Fixes P5-06/P5-07/P5-08, RP6 pair (champion vs
  most-accurate in one milestone budget line).
- Acceptance: dry-run on synthetic locked fixture in CI → log line
  with score; 4th invocation → exit non-zero `budget exhausted`;
  swarm `guard_path` denial logged. Real milestones: exactly ≤3.
- Hours: 8. Owner: A. Risk: high — any extra real invocation is
  unrecoverable snooping; rehearse only on fixtures.

## T5.5 Mesh-refinement check (A)

- Files: new `scripts/mesh_refinement.py` (2× periodic-hill mesh via
  `openfoam/meshing/`, champion coarse vs fine worst-case error);
  `tests/science/test_mesh_refinement.py`.
- Dep: T5.3 champion, real hill mesh (not flat placeholder, D4).
  Fixes P5-09/P5-15 (numerical leg).
- Acceptance: refinement table → `|Δ worst-case error| < 2%`
  or gate recorded FAIL with numbers, no silent pass.
- Hours: 6. Owner: A. Risk: high — mesh generation is the Phase 1
  placeholder's known weak point.

## T5.6 Results table + notebooks + champion reproduction (A+B)

- Files: `notebooks/` results notebook (mean±spread, wins/losses,
  `frozen | short | full` label on every table/figure, RP1/RP2/RP6
  verdicts incl. negatives); `scripts/reproduce_champion.py`
  (replay-mode, hash lookup, error diff <1e-5 per plan l.444);
  `tests/science/` protocol tests (3×3 completeness, ≤3 cap).
- Dep: T5.3–T5.5. Fixes P5-10/P5-11/P5-14/P5-15.
- Acceptance: outsider command `python scripts/reproduce_champion.py
  --champion-hash <logged>` → exit 0, reproduced errors within 1e-5;
  notebook renders the complete table from run dirs alone.
- Hours: 8. Owner: both. Risk: medium.

## Gate re-test (A+B, after T5.3–T5.6)

- Command: 9 run dirs + vault log + mesh table + notebook table.
- Expected: complete 3×3 table (mean±spread, losses shown), ≤3
  `LOCKED_EVAL` lines with scores, mesh Δ<2%, champion reproduced.
  Only then mark Phase 5 gate PASS.
- Hours: 2. Owner: both. Risk: gate stays FAIL while P5-16
  (dataset/Docker/API) is unresolved.

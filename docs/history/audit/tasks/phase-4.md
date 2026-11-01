# Tasks — Phase 4 (S6 composer, Nov 1 gate)

Owners: A = physics/OpenFOAM, B = agents/API/UI (spec l.301). Shared: experiments/freeze.
Deps reference Phase 2 (ladder/elegance/round, `audit/round-1/phase-2.json`
P2-05/P2-12) and the Phase-4 rows in `audit/round-1/phase-4.json`.
Cut order (plan): RP4 composer is the first cut — if T4.1+T4.2 are not
green by Nov 1 EOD, do T4.5 (ship best single) and skip the rest.
All scores carry the `frozen | short | full` label (audit/GATE.md).

## T4.1 Gate fitting: fit (w, b) on training flows (B, A reviews objective)

- Files: new `flowforge/composer/fitting.py` (`fit_gates(modules, gate_inputs, targets, seed=42) -> GateFit{w, b, worst_error, dl_penalty_bits}` using `scipy.optimize.minimize`/bounded scalar search over the P4-01 blend); register `fit_gates` in `flowforge/agents/tools/registry.py` (schema-validated, budget-metered like `fit_constants`); typed `GateSpec` in `flowforge/agents/schemas.py` replacing `CompositionPlan.gates: list[dict]`.
- Dep: P4-01 (formula, done). Fixes P4-03, P4-09 (tool half).
- Acceptance: `python -m pytest tests/unit/test_composer_fitting.py -q` (new: fitted `(w,b)` beats a coarse grid search on 2 synthetic modules, deterministic at `seed=42`, fitted composite beats both singles on a regime-split fixture) → expected: exit 0, all pass; plus `python -c "from flowforge.agents.tools.registry import TOOLS; assert 'fit_gates' in TOOLS"` → exit 0.
- Hours: 6. Risk: medium — scalar gate may underfit multi-regime data; if the objective is non-smooth at saturation, bound `w·I+b` and log the active-point fraction. Owner B.

## T4.2 Joint composition + fix evaluation (B)

- Files: `flowforge/composer/evaluate.py` (recursive joint composite: one composite array out, per-gate `(w_i, b_i)`, score every target — no `zip` truncation; assert `len(preds)==len(targets)`), `flowforge/composer/gates.py` (keep `compose` as the 2-module kernel; add `compose_many` folding it), tests in `tests/unit/test_field_io_composer.py` + new last-flow regression test.
- Dep: T4.1. Fixes P4-04, P4-06 (scoring half), P4-07 (comparands).
- Acceptance: `python -m pytest tests/unit/test_s55_s6.py tests/unit/test_field_io_composer.py -q` → expected: exit 0, including a test where only the last flow separates composite from single (fails on current code: `worst_error` ignores `targets[-1]`); `python audit/probes/phase4-composer.py` → expected: exit 0 with the truncation demo inverted (probe updated in the same change).
- Hours: 5. Risk: medium — recursive gating order changes semantics; freeze the fold order (module order = library order) in the docstring before coding. Owner B.

## T4.3 Elegance wiring + frozen configs (B, A approves values)

- Files: `flowforge/elegance/engine.py` (`description_length(..., n_gates=0)` adds `16 * n_gates`; `pick_champion` unchanged), new `configs/tolerances.yaml` (`gate_penalty_bits: 16`, `champion_margin: 0.03`, `snap_tolerance: 0.01`) loaded by `gates.py`/`engine.py` with code constants as fallback, `flowforge/orchestrator/round.py` (pass real constants + `n_gates` when enriching the champion pool).
- Dep: T4.2. Fixes P4-05, P4-11 (C2 Phase-4 slice).
- Acceptance: `python -m pytest tests/unit -q -k "champion or elegance or composer"` → expected: exit 0, including: gated candidate with worse DL loses to an equal-error single within the 3% pool; changing `gate_penalty_bits` in the YAML changes `description_length` (config actually read).
- Hours: 4. Risk: low — values are already specified (16/3%/1%); only plumbing. Do not retune values in this task. Owner B.

## T4.4 Round integration: Composer step with real modules (A+B)

- Files: `flowforge/orchestrator/round.py` (step 8: load rung-3 survivors, evaluate each as a field per training flow via `flowforge/dsl/evaluate.py`, fit gates (T4.1), compose (T4.2), score with ladder `minimax_score`, emit a `composition` event to the event log), `library/modules/` writer (composite stored as a module record: expression, constants, gates, scope, provenance, evidence hashes — with Phase-5/library owner), `prompts/composer.yaml` + composer role invocation only if the LLM proposes module sets (record the `CompositionPlan`; fitting stays deterministic, D5).
- Dep: T4.1–T4.3; Phase-2 round/event-log; at least 2 verified modules in `library/modules/` (Phase-5 lifecycle — if none exist, seed two hand-written modules and label the session `frozen`). Fixes P4-08, P4-10, P4-09.
- Acceptance: `python -m flowforge.orchestrator.round --round 1` on the frozen pool → expected: exit 0, output contains a `composition` entry with per-training-flow errors for both `periodic_hill_re5600` and `periodic_hill_re10595`, `dl_penalty_bits = 16 * n_gates`, and one `composition` line in `runs/<session>/events.jsonl`. This is the Phase-4 gate command.
- Hours: 8. Risk: high — depends on Phase-2 survivors being real fields, not synthetic T1 targets; if only synthetic fields exist, the gate is met in `frozen` form only and must be reported as such, never as solver-scored. Owners A+B.

## T4.5 RP4 keep/cut decision (A+B, Nov 1 EOD, hard deadline)

- Files: decision record in `runs/<session>/` + one line in the session findings (`library/findings/`); no code unless the cut fires (then: champion = best single from `pick_champion`, gates dropped).
- Dep: T4.4 (or its documented failure). Fixes P4-07.
- Acceptance: decision file exists stating keep-or-cut with the composite-vs-single minimax + DL table from T4.4 → expected: composite kept only if it beats the best single on worst-case training error after the DL penalty is counted in champion selection; otherwise the single champion is named and Phase 5 proceeds without gates.
- Hours: 1. Risk: low as a task, high as a schedule gate — this is the pre-committed cut (plan: RP4 first). Do not slip Nov 1 freeze for it. Owners A+B.

## T4.6 Composer test completion (B)

- Files: `tests/unit/test_s55_s6.py`, `tests/unit/test_field_io_composer.py`, new `tests/unit/test_composer_fitting.py` (from T4.1): add broadcast-mismatch and non-finite rejection, gate saturation, DL-in-champion, all-training-flows (2-case fixture keyed to `configs/cases.yaml` train split), and fitted-gate determinism.
- Dep: T4.1–T4.3. Fixes P4-12.
- Acceptance: `uv run pytest tests/unit -q` (outside the audit sandbox, after `uv sync`) → expected: exit 0, zero skips in composer tests; coverage of `flowforge/composer/` ≥ 90% (`--cov=flowforge.composer`).
- Hours: 3. Risk: low. Owner B. Note: pytest is absent in the audit env (declared dev dep, no `uv.lock`) — first run may surface Phase-2 sympy/sklearn failures outside composer scope; report them, do not fix here.

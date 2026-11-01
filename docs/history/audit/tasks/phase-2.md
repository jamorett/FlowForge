# Tasks — Phase 2 (S3, S4b, S5) — ordered

Owners: A = physics/OpenFOAM, B = agents/API/DSL. Hours are focused-work estimates. Every acceptance command runs after `uv sync` outside the audit sandbox (no installs in audit).

1. **Build env + get first observed Phase-2 test pass** (B, 1h, risk: low)
   Files: `uv.lock` (new), none else. Deps: none.
   Accept: `uv run pytest tests/unit/test_dsl.py tests/unit/test_physics.py tests/unit/test_evaluate.py tests/unit/test_ladder.py tests/unit/test_split_guard.py tests/unit/test_s55_s6.py -q` → exit 0, all pass. This converts P2-01/05/12 from PRESENT_UNTESTED.

2. **Decide D1/D2/D6 and freeze tolerances in configs** (A+B, 3h, risk: high — sign error invalidates targets)
   Files: `configs/tolerances.yaml` (new: elegance_margin=0.03, snap_tol=0.01, safe_eps=1e-4, realizability_tol=1e-4, zero_strain_tol, rotation_tol), `flowforge/dsl/grammar.py`, `flowforge/physics/frozen_rans.py`, `flowforge/elegance/engine.py` (read tolerances from configs, single source), decision log in `docs/`.
   Accept: `uv run pytest tests/unit/test_physics.py -q` plus new pure-rotation test (`s=0,w!=0` candidate must vanish or limit state redefined) → exit 0; `grep -rn "0.03\|0.01" configs/tolerances.yaml` shows both margins. Deps: 1.

3. **Complete candidate format: sum over T1..T4 + h(I) production + candidate hash/dedup** (B, 6h, risk: medium)
   Files: `flowforge/dsl/evaluate.py` (multi-basis `candidate_anisotropy`, `candidate_production`), `flowforge/orchestrator/round.py` (reject re-proposed hash), `tests/unit/test_evaluate.py`.
   Accept: `uv run pytest tests/unit/test_evaluate.py -q` → exit 0 incl. test that a `T4`-only candidate is symmetry/trace-free and a known 2-term candidate reproduces hand-computed `aDelta`. Deps: 1,2 (D6 defines T4 limit behaviour).

4. **Wire the real round: roles via runtime, fitting, EventLogger per step** (B, 8h, risk: high)
   Files: `flowforge/orchestrator/round.py` (Board→Theorist→Coder→ladder→Analyst/Skeptic→RedTeam→Composer, log every step to `runs/<session>/events.jsonl`), `flowforge/agents/tools/registry.py` (`search_cards`→literature, add `eval_apriori`), `flowforge/dsl/fitting.py` (design-matrix builder + refit-after-snap).
   Accept: `uv run python -m flowforge.orchestrator.round --mock-llm --round 1` → exit 0 and `runs/<session>/events.jsonl` contains one event per stage; then recorded-session replay at zero tokens. Deps: 1,3,5.

5. **Flesh out prompts + literature harvester beyond fixtures** (B, 6h, risk: medium)
   Files: `prompts/*.yaml` (grammar, mechanism, JSON-only detail), `flowforge/literature/harvester.py` (OpenAlex/Semantic Scholar + pdfplumber extraction, full ClosureCard fields in `cards.py`), `data/literature/` cache.
   Accept: `uv run pytest tests/unit -q -k "literature or prompt"` → exit 0 with 3 recorded samples per role validating against `flowforge/agents/schemas.py`; harvester returns ≥1 non-fixture card from a cached response. Deps: 1.

6. **Ingest real cases to Zarr + call guard from swarm tools** (A+B, 5h, risk: medium)
   Files: `flowforge/data/ingest.py` (foamlib raw read + `configs/cases.yaml` registration, call it from a script/CLI), `flowforge/agents/tools/registry.py` (route all data reads through `guard_path`).
   Accept: `uv run pytest tests/unit/test_split_guard.py -q` → exit 0 incl. a tool-level locked-read refusal that appends to `runs/vault_access.log`; Zarr round-trip probe `uv run python scratch/probe_zarr_store.py` → `PROBE OK`. Deps: 1, dataset (Phase 1).

7. **Canonical channel + flatPlate templates** (A, 6h, risk: medium)
   Files: `openfoam/templates/channel/`, `openfoam/templates/flatPlate/` (0/, constant/, system/ from periodicHill pattern + geometry).
   Accept: `ls openfoam/templates/channel openfoam/templates/flatPlate` shows case files (not only `.gitkeep`); short rung-2 run on channel completes or is Docker-blocked with the block recorded. Deps: Phase 1 solver.

8. **Wall-clock WS pacing proof on a real socket** (B, 1h, risk: low)
   Files: none (probe exists: `scratch/probe_ws_pacing.py`).
   Accept: server running outside sandbox, `python scratch/probe_ws_pacing.py` → `PACING_OK bare subscribe paced ~50ms` with bare subscribe (no pacing/count). Deps: 4 (events to stream).

9. **Ladder minimax wiring** (B, 2h, risk: low)
   Files: `flowforge/ladder/ladder.py`, `flowforge/orchestrator/round.py` (score survivors by `minimax_score` vs SST per case, not raw MSE).
   Accept: `uv run pytest tests/unit/test_ladder.py -q` → exit 0 incl. worst-case-not-average ranking test. Deps: 1,6 (per-case targets).

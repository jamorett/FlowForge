# Tasks — Phase 3 (S6 red team + UI)

Owners: A = physics/OpenFOAM, B = agents/API/UI (spec l.301).
Deps reference Phase 1 (solver/data) and Phase 2 (ladder/round/API)
gates; do not start gate tasks until those land or a frozen-RANS
substitute pool is explicitly declared. All acceptance commands run
outside this audit sandbox where noted.

## T3.1 Wire generated flows to scripted meshes (A)

- Files: `openfoam/meshing/hill_geometry.py`,
  `openfoam/templates/periodicHill/system/blockMeshDict` (new
  generator script under `openfoam/meshing/`), consume
  `flowforge/redteam/generator.py:34` specs (12 default).
- Dep: Phase 1 baseline mesh decision (GATE.md D4); fixes P3-02.
- Acceptance: for each of the 12 specs, generate a case dir and run
  `blockMesh` in the OpenFOAM container → expected: exit 0 for all
  12, wall geometry differs from flat placeholder (checkMesh OK).
- Hours: 6. Risk: high — alpha deformation (`base**alpha`) may not
  match dataset hill profile; owner must validate vs Xiao et al.
  before meshing (see audit note 3).

## T3.2 First recorded break (A)

- Files: new runner (e.g. `scripts/run_redteam.py`) calling
  `flowforge/redteam/attacks.py:32` `run_attack_suite` +
  `broke_threshold` + `record_attack` into `library/attacks/`;
  per-flow invariants/basis must actually vary by flow.
- Dep: T3.1 (for solver-backed attacks) or frozen-RANS targets +
  Phase 2 ladder survivors as the candidate pool; fixes P3-03/P3-04.
- Acceptance: `python scripts/run_redteam.py --session demo`
  → expected: exit 0 and ≥1 `library/attacks/attack_*.json` written
  with candidate, flow spec, score and baseline recorded (extend
  the JSON schema; current writer stores neither score nor hash).
- Hours: 6. Risk: high — no candidate may actually break at 1.5×;
  if none breaks, record the negative result and lower nothing
  silently (report per RP5).

## T3.3 Attack visible in UI (B)

- Files: `flowforge/api/server.py` (emit/serve attack results:
  read `library/attacks/` or score events), `ui/src/pages/
  MissionControl.tsx` (attack-specific feed), `ui/src/components/
  MatrixHeatmap.tsx` (honour `locked_greyed`, cell click →
  inspector), `ui/src/pages/CandidateInspector.tsx` (attack
  history from data, not prose).
- Dep: T3.2. Fixes P3-08/P3-09/P3-10 gate visibility.
- Acceptance: with the T3.2 session loaded, start API + UI
  (`cd ui; npm run dev`) → expected: Matrix shows the broken
  candidate × generated-flow cell, locked columns grey, clicking
  the cell opens the Inspector with that attack listed.
- Hours: 8. Risk: medium — event schema for score/attack events
  must be frozen with Phase 2 owners first.

## T3.4 PyVista render path + SAM decision (A+B)

- Files: `flowforge/render/error_map.py` (add the promised
  off-screen mesh render or delete the docstring claim), new
  `flowforge/render/sam_client.py` only if endpoint confirmed;
  `ui/src/pages/CandidateInspector.tsx` (display rendered PNG).
- Dep: Phase 1 fields on disk; Meta endpoint docs check (B).
  Fixes P3-05/P3-06.
- Acceptance: decision logged in repo (confirm or cut SAM, 1h);
  then `python -c "render one error map from a real field pair"`
  → expected: exit 0, PNG opens and matches the `.npy` sidecar;
  without SAM, Inspector shows the plain error map.
- Hours: 5 (+1 decision). Risk: medium — PyVista off-screen in
  container is the usual failure point; cut SAM first per plan
  cut order if slipping.

## T3.5 Finish the three thin views (B)

- Files: `ui/src/pages/Vault.tsx` + new API endpoint for locked
  milestones/access log; `ui/src/pages/Replay.tsx` (real timeline
  scrubber over `events.jsonl`: range input, play/pause, index);
  `ui/src/pages/MissionControl.tsx` (group cards, budget/token/
  solver meters, champions strip, session start/pause per spec
  l.250); read flow lists from `configs/cases.yaml` in
  `flowforge/api/server.py` instead of hardcoding.
- Dep: Phase 2 event/budget schema. Fixes P3-08/P3-11/P3-12.
- Acceptance: `cd ui; npm run build` → expected: exit 0, zero
  TypeScript errors; Vault renders milestone rows from the API
  (empty state when none), Replay scrubs a recorded session
  without the API re-streaming from event 0.
- Hours: 10. Risk: medium — session-control (start/pause) needs
  an orchestrator control endpoint that does not exist yet.

## T3.6 Prove the UI build + live session end to end (B)

- Files: none new; run in main checkout (this audit could not:
  build writes `ui/dist/`). Also add `ui/node_modules/` and
  `ui/dist/` to `.gitignore` and untrack them (H2 CONFIRMED:
  4683 + 62 files) — coordinate with whoever owns hygiene.
- Dep: T3.3/T3.5.
- Acceptance: `cd ui; npm run build` → exit 0; `npm run dev` +
  FastAPI session with ≥1 scored candidate → expected: Mission
  Control streams events at ~20/s and the Matrix populates.
- Hours: 3. Risk: low-medium — TypeScript errors may surface on
  first real build of current `src/` (never yet run).

## T3.7 S6 tail: harness fixtures + curriculum (B)

- Files: `flowforge/agents/evals/` (one positive + one negative
  fixture per harness set), `library/curriculum/` (linked
  examples). Fixes P3-15.
- Dep: Phase 2 harness contracts.
- Acceptance: fixtures load in their eval runners → expected:
  positive passes, negative fails, thresholds unchanged.
- Hours: 4. Risk: low.

## Gate re-test (A+B, after T3.1–T3.3, T3.6)

- Command: T3.2 runner, then API + `cd ui; npm run dev`.
- Expected: ≥1 recorded attack in `library/attacks/`, the break
  visible as a Matrix cell and in the Inspector, locked columns
  grey. Only then mark the Phase 3 gate PASS.
- Hours: 1. Risk: gate stays FAIL if upstream Phase 1/2 remains
  frozen-only with no declared substitute candidate pool (P3-16).

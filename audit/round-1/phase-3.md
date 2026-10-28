# Phase 3 audit — S6 red team + UI (round 1)

Scope: spec Phase 3 (Oct 30–31) + UI/UX Model Lab + red team, plan S6
(l.393–418, esp. S6.1 l.397–398, S6.3 l.401–409). Rows:
[audit/round-1/phase-3.json](phase-3.json) (P3-01…P3-16). Tasks:
[audit/tasks/phase-3.md](../tasks/phase-3.md). `project_status.md`
treated as unverified throughout. `data/locked/` never opened. No
installs, no network, no Docker, no `npm install`, no UI build run.

## Gate verdict: FAIL

Phase 3 gate = "the red team breaks at least one candidate and the
attack is visible in the UI" (spec l.326; plan l.394, l.458).

- No attack is recorded anywhere: `library/attacks/` contains only
  `.gitkeep`. Probe (python subprocess, timeout=120, exit 0):
  `matrix('default')` → `candidates=[]`, `cells=[]`; the only session
  log, `runs/probe_s55/events.jsonl`, is 5 synthetic `{"type":"tick"}`
  lines with no candidate/flow/error event for any UI to show.
- The chain is never executed in production code. Caller search
  (exit 0): `record_attack` ← tests only; `run_attack_suite` ← no
  callers at all; `render_png` ← tests only; `generate_attacks` ←
  `flowforge/api/server.py:72-77` (matrix labels only) + tests/probe.
  `flowforge/orchestrator/round.py:33-82` never imports redteam,
  render or composer — RedTeam exists only in its l.3 docstring.
- Upstream is blocked anyway (P3-16, BLOCKED_BY_ENV): no dataset,
  no Docker, frozen-RANS-only per [audit/GATE.md](../GATE.md:60).

FAIL (not UNVERIFIABLE): the absence is positively observed, not
merely untested.

## What is real

- **Generator (P3-01 VERIFIED, function-level).**
  [flowforge/redteam/generator.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/redteam/generator.py:34)
  enforces alpha ∈ [0.5, 1.5], positive Re, validation-only split.
  Probe exit 0: 12 default specs (4 alphas × 3 Re), train split and
  alpha=2.0 refused. Bumps are an allowed `kind` but no caller ever
  requests them.
- **Attack primitives (P3-04 PRESENT_UNTESTED).**
  [flowforge/redteam/attacks.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/redteam/attacks.py:32)
  `run_attack_suite` + `broke_threshold` (1.5× baseline) behave as
  coded on synthetic arrays (probe exit 0). Caveat for the lead:
  the same invariants/basis are passed for every flow, so per-flow
  physics never varies; and `record_attack` keys files by
  `candidate[:8]`, overwriting per candidate with no score stored.
- **Rendering (P3-05 SKELETON).** Answer to the brief's question:
  **stdlib PNG, not PyVista.**
  [flowforge/render/error_map.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/render/error_map.py:35)
  is a genuine zlib/struct PNG encoder + `.npy` sidecar (probe:
  PNG magic confirmed). PyVista is declared
  ([pyproject.toml](/C:/Users/juanc/Desktop/FlowForge/pyproject.toml:23))
  but not installed (probe `ModuleNotFoundError`) and no PyVista
  code exists — the docstring's `render_mesh_png` is not defined.
- **SAM 3.1 (P3-06 MISSING).** No client exists; the only SAM text
  is the [flowforge/render/__init__.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/render/__init__.py:1)
  docstring. Plan l.394 makes SAM conditional on endpoint
  confirmation — no confirm/cut decision is recorded.
- **Meshing (P3-02 SKELETON).**
  [openfoam/meshing/hill_geometry.py](/C:/Users/juanc/Desktop/FlowForge/openfoam/meshing/hill_geometry.py:13)
  is an analytic cosine profile only. Nothing wires it into the
  flat placeholder `blockMeshDict` (its own header admits this),
  so generated flows have no meshes.

## UI: real data path, thin pages

Answer to the brief's question: **Mission Control and the Matrix do
fetch/stream from FastAPI; Inspector, Vault and Replay-content are
static or re-streamed text.**

- Real: [ui/src/api/client.ts](/C:/Users/juanc/Desktop/FlowForge/ui/src/api/client.ts:6)
  fetches `/api/session/state` + `/api/matrix`, opens
  `/ws/events`; TanStack Query wired in
  [ui/src/main.tsx](/C:/Users/juanc/Desktop/FlowForge/ui/src/main.tsx:7);
  [MatrixHeatmap.tsx](/C:/Users/juanc/Desktop/FlowForge/ui/src/components/MatrixHeatmap.tsx:8)
  is a real Plotly heatmap of backend cells;
  [EquationView.tsx](/C:/Users/juanc/Desktop/FlowForge/ui/src/components/EquationView.tsx:5)
  is real KaTeX. Server pacing is real code
  ([flowforge/api/server.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/api/server.py:99):
  50 ms/event even for a bare subscribe). Zero-physics-in-React
  discipline holds.
- Thin/stub-shaped: Mission Control has no groups, budget meter,
  champions or start/pause (P3-08); the Matrix ignores
  `locked_greyed`, has no cell click → inspector and no Elegance
  view (P3-09); the Inspector shows one hardcoded composer formula
  and prose claims for profiles/barycentric/error-map/attack-history
  (P3-10); Vault is static text with no endpoint behind it (P3-11);
  Replay has a session-name input but no scrubber (P3-12).
  `ui/src/state/` is an empty `.gitkeep`.
- Build plausibility (P3-07 PRESENT_UNTESTED): `ui/package.json`
  scripts/deps are complete and coherent; `node --version` →
  v24.22.0 exit 0; `ui/node_modules/.bin/vite.cmd` and all key
  packages exist on disk; a tracked `ui/dist/index.html` references
  hashed assets, proving a build once ran. Per instructions the
  build was **not** run here (it would write `ui/dist/`), so a
  clean build of current `src/` is unproven, not confirmed.

## Findings verdicts (Phase 3 scope)

- **H2 (partly: `ui/node_modules` + `ui/dist` tracked / not
  ignored) — CONFIRMED.** My own count from
  `audit/evidence/git-ls-files.txt` and a live
  `git ls-files` (both exit 0): **4683** `ui/node_modules/` files
  and **62** `ui/dist/` files tracked (4770 `ui/` files of 4917
  total). [.gitignore](/C:/Users/juanc/Desktop/FlowForge/.gitignore:1)
  (9 lines) has no `ui/node_modules` or `ui/dist` entry.
- **D3 (partly) — noted, not resolved here.** Training cases are
  `periodic_hill_re5600`/`re10595`
  ([configs/cases.yaml](/C:/Users/juanc/Desktop/FlowForge/configs/cases.yaml:3));
  the generator sweeps the same geometry family at the same
  Reynolds numbers (5600, 10595) plus 20000, differing only by
  alpha (defaults exclude the α=1.0 training shape) and a forced
  `validation` split. So attack-flow segregation holds by label,
  but "beyond the data" is only an alpha perturbation of the
  training family — if a generated α/Re case is ever promoted,
  D3's overlap question reopens. No generated flow touches the
  locked square-duct/hump cases.
- Other proven notes for the lead: (1) `error_map.py` docstring
  advertises a non-existent `render_mesh_png`; (2) server matrix
  train/locked lists are hardcoded, not read from
  `configs/cases.yaml`; (3) `hill_height` uses `base**alpha`, whose
  sampled peak *decreases* with alpha in my probe — steepness
  semantics need an owner check against Xiao et al.; (4) stub-scan
  reconciliation: `attacks.py:23 return None` is the intended
  not-broke branch and `error_map.py:3` is a keyword false
  positive ("no placeholder text") — neither is a stub; the
  Phase 3-relevant scan silence on UI `.tsx` is because the scan
  does not cover TypeScript.

## Signed account

- Counts (16 rows): VERIFIED 1 (P3-01, function-level only),
  PRESENT_UNTESTED 3 (P3-04, P3-07, P3-13), SKELETON 8 (P3-02,
  P3-03, P3-05, P3-08…P3-12), MISSING 3 (P3-06, P3-14, P3-15),
  BLOCKED_BY_ENV 1 (P3-16), DECISION_NEEDED 0 rows (one decision
  owed inside P3-06's gap: SAM confirm-or-cut).
- Gate: **FAIL** — no recorded break, no attack visible in UI.
- Top 5 gaps: (1) attack chain never wired (orchestrator → suite
  → `library/attacks/` → UI cell); (2) generated flows have no
  meshes or solver path; (3) Inspector/Vault/Replay are static
  shells and the Matrix cannot grey locked columns or open cells;
  (4) PyVista path absent and SAM undecided, so error-map/SAM
  evidence for the Analyst does not exist; (5) harness fixtures +
  curriculum (S6 tail clause) missing, and the UI build of current
  source is unproven.
- Not checked: `npm run build`/`npm run dev` execution and any
  browser rendering (forbidden here — would write `ui/dist/`);
  pytest suite (pytest absent, exit 1 in evidence); WebSocket
  pacing over a real socket; OpenFOAM meshing/solver (no Docker);
  `data/locked/` (never opened); Meta/SAM endpoint (no network,
  no API key).
- Confidence: high on code reachability, counts and gate FAIL
  (all directly probed, exit 0); medium on UI build plausibility
  (inferred from on-disk `node_modules` + tracked dist, not run).

Signed account

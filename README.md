# FlowForge v2

An autonomous science team that discovers turbulence closures — plus a live UI
that watches it work. Research groups propose candidate equations, a red team
attacks them, winners are validated through a real OpenFOAM farm running in
Docker, and SAM 3.1 segments the error maps so you can see *where* each
candidate fails. Everything streams to a React cockpit: groups interacting,
equations proposed, red-team challenges, and evaluations as they happen.

Methodology follows [v2 Build spec.md](v2%20Build%20spec.md); work sequencing
follows [docs/plans/2026-10-26-flowforge-v2-implementation-plan.md](docs/plans/2026-10-26-flowforge-v2-implementation-plan.md).
Tolerances are frozen in `configs/tolerances.yaml` — never loosened to make a
check pass.

## How it fits together

- **Agents** (`flowforge/agents/`): theorist, coder, skeptic, red-team,
  composer, champion, analyst. Rounds run single-group or multi-group
  (`--groups N`: N research lines plus cross-group champion merge).
- **Physics ladder** (`flowforge/agents/harness/`): rung 0 (expression checks)
  → rung 1 (a priori vs frozen-RANS targets) → rung 2/3 (coupled solver
  validation). Gates in `flowforge/composer/gates.py`.
- **Solver farm** (`flowforge/solver/`, `openfoam/`): our `correctedKOmegaSST`
  closure (fixed-field Mode A + explicit SpaRTA stress via `divDevReff`) runs
  in a pinned OpenFOAM image (`docker/openfoam.Dockerfile`). Content-hashed
  result cache; fields travel on the run result.
- **Data** (`flowforge/data/`, `scripts/`): Kaggle RANS/DNS corpus ingested to
  Zarr stores with frozen-RANS targets (`a_delta`, `Pk_delta`, `U_dns`,
  `b_dns`). Raw CSVs and processed stores stay out of git (CC-BY-4.0, ~884 MB).
- **SAM 3.1** (`flowforge/render/sam_client.py`): error maps stream to
  `POST <base>/responses` (`model: sam-3.1`, same Bearer `MODEL_API_KEY`). Concept prompt
  first; on zero matches the local box is re-sent as a box prompt and SAM
  answers with a refined box plus mask under our id. Every result is labeled
  `sam-3.1`, `local-fallback`, or `none` — never misreported.
- **API + UI** (`flowforge/api/server.py`, `ui/`): FastAPI backend, React +
  Plotly cockpit. Mission Control starts mock (free) or live rounds;
  Candidate Inspector shows live candidates with a `LIVE`/`OFFLINE SAMPLES`
  badge.

## Status (2026-10-29, verified this session)

Green:

- Unit suite green (190+ tests), UI `tsc --noEmit` clean.
- Baseline SST converges in the container (`converged=True`, ~837 steps on
  the hill mesh with non-orthogonal correctors).
- Solver gates green: **identity** (zero correction == baseline SST,
  diff < 1e-6) and **injection** (nonzero field moves the solution).
- SAM 3.1 live-verified with a real key: concept stream, token-grammar
  parser, and the full propose→dispose box-refine loop on a real error map.
- Multi-group rounds, regions endpoints, live theorist/composer prompts.

Open:

- **Oracle gate** (`tests/integration/test_solver_oracle.py`, frozen
  `oracle_ratio: 0.70`): still red. Fixed so far: the stress correction
  sign in `divDevReff`, a spurious stress on wall faces, the oracle case
  (the old "Re 10595" store was case_1p5, the alpha=1.5 hill at Re 5600)
  and nu (Re_h on the crest bulk velocity -> 2.254e-4). First pass now
  0.855 (was 0.967); the 3-pass recalibration loop diverges (1.24, 1.43).
  Even live injection of the exact DNS stress gives ~1.15, so the
  remaining gap is case/DNS equivalence (mesh, wall treatment, mapping).
  No tolerance was touched. Per the build spec, frozen-RANS a-priori
  scoring carries the candidate ranking.

## Setup (fresh clone)

Prereqs: Python 3.12, Node 18+, Docker Desktop, a Meta Model API key.

1. `pip install -e ".[dev]"` and `cd ui && npm install`.
2. `cp .env.example .env` and put your key in `MODEL_API_KEY`.
   `.env` is git-ignored — never commit it. `FLOWFORGE_REPLAY=1` forces
   zero-token mode (no network calls at all).
3. Data — either `python scripts/download_data.py --synthetic-fallback`
   (tiny smoke corpus) or drop the Kaggle CSVs (`komegasst.csv`, `REF.csv`)
   into `data/raw/` and run `python -m flowforge.data.ingest_csv`.
4. Solver image: `docker build -f docker/openfoam.Dockerfile
   -t flowforge-openfoam:local .` (or `docker compose -f
   docker/compose.yaml build`). Compiles `libcorrectedKOmegaSST` on
   OpenFOAM v2512; takes several minutes once. `flowforge-openfoam:local`
   is the runner default (`FLOWFORGE_OPENFOAM_IMAGE` overrides it).
5. Tests: `python -m pytest tests/unit -q` (fast, no Docker/key).
   Integration/solver gates need Docker Desktop running + the image and
   take minutes (a stopped daemon fails the gates instead of skipping):
   `python -m pytest tests/integration/test_solver_identity.py -q`
   (identity + injection, ~6 min),
   `python -m pytest tests/integration/test_solver_oracle.py -q`
   (DNS oracle, ~3–7 min).
6. Serve: `python -m uvicorn flowforge.api.server:app --port 8000`, then
   `cd ui && npm run dev` (needs `VITE_API=http://localhost:8000`) and open
   the Vite address (usually `http://localhost:5173`). Start with a mock
   round from Mission Control to validate the setup before running a live
   round.

Costs: live rounds and SAM calls consume API credits (approximately $0.60
observed for the initial live rounds); mock mode and `FLOWFORGE_REPLAY=1`
incur no cost. Solver-gate runs each require minutes of container time.

## Guardrails

- Never read `data/locked/` directly — locked evaluation only via
  `scripts/evaluate_locked.py` (logged, max 3 runs).
- `data/`, `runs/`, `.env`, `scratch/`, `ui/node_modules/` are git-ignored.
  Probe scripts live in `scratch/` and are never committed as results.
- Mock/synthetic outputs are bookkeeping only — never reported as results.

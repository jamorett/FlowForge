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
  `POST <base>/responses` (`model: sam-3.1`, same Bearer key). Concept prompt
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
  `oracle_ratio: 0.70`): DNS-derived corrections on the data-derived hill
  mesh move the solution the right way, but the 0.70 bar is not met:
  single-shot ratio ≈ 0.97 (reattachment zone ≈ 0.89), 3-pass
  recalibration loop 0.967 (non-compounding). The gate stays red until
  the ratio clears — no tolerance was touched. Known blockers: uniform
  mesh can't represent DNS wall layers (wall-graded meshing is staged in
  `hill_mesh.py`), and the live-k gap (correction uses solved k, not DNS
  k). Per the build spec, coupled evaluation continues; frozen-RANS
  a-priori scoring carries the candidate ranking meanwhile.

## Setup (fresh clone, friend's PC included)

Prereqs: Python 3.12, Node 18+, Docker Desktop, a Meta Model API key.

1. `pip install -e ".[dev]"` and `cd ui && npm install`.
2. `cp .env.example .env` and put your key in `MODEL_API_KEY`.
   `.env` is git-ignored — never commit it. `FLOWFORGE_REPLAY=1` forces
   zero-token mode (no network calls at all).
3. Data — either `python scripts/download_data.py --synthetic-fallback`
   (tiny smoke corpus) or drop the Kaggle CSVs (`komegasst.csv`, `REF.csv`)
   into `data/raw/` and run `python -m flowforge.data.ingest_csv`.
4. Solver image: `docker build -f docker/openfoam.Dockerfile
   -t flowforge-openfoam:local .` (compiles `libcorrectedKOmegaSST`;
   takes several minutes once), then
   `FLOWFORGE_OPENFOAM_IMAGE=flowforge-openfoam:local` (or export it).
5. Tests: `python -m pytest tests/unit -q` (fast, no Docker/key).
   Integration/solver gates need Docker + the image and take minutes:
   `python -m pytest tests/integration/test_solver_identity.py -q`
   (identity + injection, ~6 min),
   `python -m pytest tests/integration/test_solver_oracle.py -q`
   (DNS oracle, ~3–7 min).
6. Serve: `python -m uvicorn flowforge.api.server:app --port 8000`, then
   `cd ui && npm run dev` (needs `VITE_API=http://localhost:8000`) and open
   the Vite address (usually `http://localhost:5173`). Start a mock round
   from Mission Control, then a live one once mock looks right.

Honest costs: live rounds and SAM calls spend API credits (about $0.60
observed for the first live rounds); mock mode and `FLOWFORGE_REPLAY=1`
spend nothing. Solver-gate runs each take minutes of container time.

## Guardrails

- Never read `data/locked/` directly — locked evaluation only via
  `scripts/evaluate_locked.py` (logged, max 3 runs).
- `data/`, `runs/`, `.env`, `scratch/`, `ui/node_modules/` are git-ignored.
  Probe scripts live in `scratch/` and are never committed as results.
- Mock/synthetic outputs are bookkeeping only — never reported as results.

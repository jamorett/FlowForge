# FlowForge v2

An autonomous science team that discovers turbulence closures — plus a live UI
that watches it work. Research groups propose candidate equations, a red team
attacks them, winners are validated through a real OpenFOAM farm running in
Docker, and SAM 3.1 segments the error maps so you can see *where* each
candidate fails. Everything streams to a React cockpit: groups interacting,
equations proposed, red-team challenges, and evaluations as they happen.

Methodology follows [docs/build-spec.md](docs/build-spec.md); work sequencing
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
  `sam-3.1`, `local-fallback`, or `none` — never misreported. SAM runs only when
  a run enables it (UI "SAM 3.1 segmentation" / `run_arms.py --sam`); otherwise the
  local segmenter is used. The segmented regions (in physical x/h, y/h) are given to
  the Analyst before it diagnoses. Error maps are true spatial rasters since
  2026-11-01; earlier maps reshaped the cell list into a square and are not spatial.
- **API + UI** (`flowforge/api/server.py`, `ui/`): FastAPI backend, React +
  Plotly cockpit. Mission Control starts mock (free) or live rounds;
  Candidate Inspector shows live candidates with a `LIVE`/`OFFLINE SAMPLES`
  badge.

## Repository layout

```text
flowforge/      Python package (agents, dsl, physics, data, solver, ladder, redteam,
                elegance, composer, baselines, orchestrator, literature, render, api)
openfoam/       correctedKOmegaSST C++ class, case templates, hill meshing
configs/        budgets, case splits, frozen tolerances, experiment arms
prompts/        versioned role prompts (hash logged on every call)
library/        cross-session memory: modules, attacks, rejected, findings,
                curriculum, literature (curated closure cards)
scripts/        entry points: download_data, run_experiment, run_arms,
                evaluate_locked, reproduce_champion, export_demo
tests/          unit/ (fast, CI), agents/, science/, integration/ (Docker solver gates)
ui/             React + Plotly cockpit (Vite)
docker/         pinned OpenFOAM image + compose
docs/           build-spec.md (methodology authority), plans/ (sequencing authority),
                history/ (frozen snapshots: Oct 27 audit, Oct 28 status; not current)
notebooks/      analysis and figures
data/  runs/  scratch/   git-ignored: datasets + locked vault, session outputs, probes
```

Run every command from the repo root: `configs/` and `prompts/` are found from
the package location, but `runs/`, `data/` and `library/` resolve relative to the
working directory.

## Status (2026-10-29, verified this session)

Green:

- Offline suite green: 288 passed (unit + agents + science, 2026-10-31);
  UI `tsc --noEmit` clean (last checked 2026-10-29).
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
  Diagnosis (2026-10-31, scratch probes, not results): on the dataset's
  own 99x149 mesh with low-Re walls, our baseline matches the dataset SST
  to 0.0057 (case equivalence solved), yet b-space injection still gives
  1.05. SST's anisotropy shape is already close to DNS; its k is 2-4x too
  low in the shear layer, and `tauDelta = 2*k_solver*aDelta` cannot carry
  that magnitude (stress-referenced injection feeds back through k and
  diverges, 5.3). Next step needs C++: PkDelta as a `kSource()` term
  (currently read but unused) or a fixed, k-independent stress field.
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
6. Serve the API: `python -m uvicorn flowforge.api.server:app --host 127.0.0.1 --port 8000`.
   UI, either way:
   - **Static (recommended for demos):** `cd ui && VITE_API=http://localhost:8000 npx vite build`,
     then `python -m http.server 5173 --bind 127.0.0.1 --directory ui/dist`. No Vite dev
     server runs (its esbuild/vite advisories are fixed only in vite 8).
   - **Dev:** `cd ui && npm run dev` (the Vite proxy forwards `/api` and `/ws`).

   Open `http://localhost:5173`, pick a session in the top bar. Mission Control shows the
   live agent graph, candidate funnel, progress vs SST, champion, red-team arena and SAM
   error regions; Results shows the arms table; Replay re-plays a session at no cost.
   **Run control** (Mission Control, top panel): presets (smoke test, live check, research
   session, ablation, experiment dry run, full experiment) or custom session runs (rounds,
   groups, red team on/off, mock/live, budget cap) and the 3-arm experiment (rounds, groups,
   3 session seeds, budget, dry run, archive old sessions). Pause / resume / stop act between
   rounds; experiments can also be killed. Live runs ask for confirmation with a cost estimate
   and cannot exceed `session_dollar_limit`. Start with the free smoke test.

Costs: live rounds and SAM calls consume API credits (approximately $0.60
observed for the initial live rounds); mock mode and `FLOWFORGE_REPLAY=1`
incur no cost. Solver-gate runs each require minutes of container time.

## Guardrails

- Never read `data/locked/` directly — locked evaluation only via
  `scripts/evaluate_locked.py` (logged, max 3 runs).
- `data/`, `runs/`, `.env`, `scratch/`, `ui/node_modules/` are git-ignored.
  Probe scripts live in `scratch/` and are never committed as results.
- Mock/synthetic outputs are bookkeeping only — never reported as results.

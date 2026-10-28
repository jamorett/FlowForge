# Tasks — Phase 0 (S0) recovery, in dependency order

Owners: A = physics/OpenFOAM, B = agents/API/UI (per spec L301). Estimates are focused work, excluding waiting on accounts/approvals.

## 1. Build the uv environment and commit the lockfile (P0-02, P0-03, P0-04)

- Files/modules: [pyproject.toml](../../pyproject.toml); generated `uv.lock`; `.venv/` (git-ignored).
- Dependencies: none. Unblocks every other task's acceptance command.
- Acceptance: `uv sync` exit 0 and `uv.lock` exists; then `uv run python -c "import sympy, scipy, sklearn, tenacity, zarr, foamlib"` exit 0 (the 9 modules failing import-smoke must pass); `uv run pytest tests/unit tests/agents --collect-only -q` exit 0.
- Estimate: 1 h. Owner: B. Risk: low — pins are already declared; only resolution surprises (e.g. `foamlib`/`pyvista` wheels on Windows) can bite.

## 2. Record the toolchain probe (P0-14)

- Files/modules: none in repo (record output in the run log / PR description); [versions-env.json](../evidence/versions-env.json) is the stale record to supersede.
- Dependencies: Task 1; Docker Desktop installed on the farm laptop.
- Acceptance: `python --version; uv --version; docker --version; node --version` — four version lines, four exit 0 (run via `subprocess.run(..., timeout=120)` wrapper per guardrails).
- Estimate: 0.5 h. Owner: B. Risk: low.

## 3. Decide model IDs and freeze tolerances in configs (P0-17, P0-18; C1, C2)

- Files/modules: [configs/budgets.yaml](../../configs/budgets.yaml) (coder ID), new `configs/tolerances.yaml` (values verbatim from code/plan: 3%, 1%, `1e-6`, `0.70`, `1e-4`, 16 bits, baseline `0.05`, mesh 2%), [plan](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md) L52 model list, [client.py](../../flowforge/agents/runtime/client.py) `RATE_PER_1K` keys.
- Dependencies: decision by project owner (recommendation: coder = `muse-spark-1.3` until Contributor data terms are accepted, per spec L149; `wonder` → documented `muse-wonder-1.0` or dropped). No code wiring in this task beyond renaming keys consistently.
- Acceptance: `grep -rn "muse-code\|\"wonder\"" configs/ flowforge/ docs/plans/` returns no bare non-documented IDs; `python -c "import yaml; yaml.safe_load(open('configs/tolerances.yaml'))"` exit 0.
- Estimate: 1 h + decision latency. Owner: B (A confirms tolerance values). Risk: medium — silently changing a tolerance after results exist invalidates comparisons; commit before any experiment runs.

## 4. Wire the orphaned configs to loaders (P0-05, P0-06, P0-07)

- Files/modules: new small config loader (e.g. `flowforge/config.py` or extend [client.py](../../flowforge/agents/runtime/client.py) to read the session limit); [ingest.py](../../flowforge/data/ingest.py) / `split_guard` to read splits from [cases.yaml](../../configs/cases.yaml); [run_experiment.py](../../scripts/run_experiment.py) to actually parse the experiment YAML (case, model, mesh, budgets) instead of hardcoding.
- Dependencies: Tasks 1, 3 (IDs/tolerances must be final before code reads them).
- Acceptance: `uv run pytest tests/unit -q -k "config or budget or split"` exit 0 with new tests proving: changing `session_dollar_limit` in a temp copy changes `ModelRuntime` enforcement; a `locked` case from `cases.yaml` is refused by the swarm path; `run_experiment.py --config configs/experiments/swarm.yaml` prints the swarm case set, not the hardcoded baseline.
- Estimate: 4 h. Owner: B. Risk: medium — touches budget enforcement; keep `SESSION_LIMIT` as fallback default only.

## 5. Implement the real data fetch and manifest (P0-08, P0-16; P1, D3)

- Files/modules: [scripts/download_data.py](../../scripts/download_data.py) (Kaggle curated fetch + Closure Challenge clone + README format capture), `data/raw/manifest.json` (SHA-256 + source URL + license per file, spec L103), [configs/cases.yaml](../../configs/cases.yaml) locked entries verified against the cloned benchmark.
- Dependencies: Task 1; Kaggle account/token (P0-01, human action); network outside the audit sandbox.
- Acceptance: `uv run python scripts/download_data.py` exit 0; manifest exists and every listed file's SHA-256 recomputes (`python -c` hash check exit 0); a file with a corrupted hash is rejected (negative test); Closure Challenge README metric/submission format recorded and any train/locked overlap resolved in `cases.yaml` before freezing (D3).
- Estimate: 4 h + download time. Owner: A. Risk: high — dataset availability/licence and overlap surprises are the critical path for S1/S2.

## 6. Pin and build the OpenFOAM image; run the S0.4 probe (P0-10, P0-11; D7)

- Files/modules: [docker/openfoam.Dockerfile](../../docker/openfoam.Dockerfile) (pin ESI tag closest to dataset v2006; add correctedKOmegaSST `wmake` build), [docker/compose.yaml](../../docker/compose.yaml).
- Dependencies: Task 2 (Docker present); Task 5 not required for the probe itself.
- Acceptance: `docker run --rm opencfd/openfoam-default:latest simpleFoam -help` (with the pinned tag substituted) prints the OpenFOAM banner, exit 0; `docker build -f docker/openfoam.Dockerfile .` exit 0.
- Estimate: 3 h. Owner: A. Risk: high — ESI version vs dataset v2006 mismatch can silently shift baseline fields; record the exact image digest in the run log.

## 7. Make CI honest and complete (P0-13; C4)

- Files/modules: [.github/workflows/ci.yml](../../.github/workflows/ci.yml) — remove `\|\|` failure-masking fallbacks (fail if uv fails), add the tiny OpenFOAM case job in the pinned container (spec L281), keep the offline synthetic smoke.
- Dependencies: Tasks 1, 6 (CI needs the lockfile and the pinned image).
- Acceptance: a pushed branch shows three green jobs (lint, unit, tiny OpenFOAM case) in GitHub Actions; deliberately breaking a lint rule on a throwaway branch turns CI red (proves the fallbacks no longer mask).
- Estimate: 2 h. Owner: B (A owns the tiny case). Risk: low.

## 8. Re-run the Phase 0 gate and record it (P0-12, P0-14)

- Files/modules: none (evidence only); entry point [scripts/run_experiment.py](../../scripts/run_experiment.py).
- Dependencies: Tasks 1–7. This is the spec gate, strictly stronger than plan S0 acceptance.
- Acceptance: versions printed (Task 2 output) + `data/raw/manifest.json` verified (Task 5) + CI green (Task 7), and `uv run python scripts/run_experiment.py --config configs/experiments/baseline.yaml` runs baseline SST on one periodic hill in the container, exit 0, with `converged=True` printed. Until the dataset-mesh issue (D4, Phase 1) is fixed, label any comparison `frozen | short | full` and do not claim dataset agreement.
- Estimate: 1 h. Owner: A + B jointly. Risk: medium — first real solver run; expect case-setup iterations (Phase 1 budget, not hidden here).

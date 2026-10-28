# FlowForge v2 — Oct 27 EOD gate decision (ANSWER FIRST)

**DECISION FOR TONIGHT: frozen-RANS-only. Do NOT plan on the full solver.**

This replaces the previous static GATE.md. That version claimed no command
could run; in this session the shell works via the explicit PowerShell path
and Python 3.12.10, so the gate was re-tested with commands (below). The
decision is the same, now with observed exit codes.

## Do the tests exist? Yes — logic tests + skipped solver tests

- Identity: [tests/integration/test_identity.py](../tests/integration/test_identity.py)
  - `test_identity_logic` (lines 22-25): pure NumPy threshold check at TOL=1e-6.
  - `test_zero_correction_is_exact_identity` (28-47): `.npy` round-trip +
    `production_target` zero check. No OpenFOAM process.
  - `test_identity_solver` (50-52): `@pytest.mark.skip(reason="needs Docker
    baseline run (S1 verification pending)")`, body `raise NotImplementedError`.
- Oracle: [tests/integration/test_oracle.py](../tests/integration/test_oracle.py)
  - `test_oracle_logic` (28-35): inequality arithmetic at ratio 0.70.
  - `test_dns_injection_targets_reduce_error` (38-69): synthetic DNS;
    line 65 `u_oracle = u_base - 0.75*(u_base - u_dns)` is labelled in the
    docstring (8-9) "NOT a solver result".
  - `test_oracle_solver` (72-74): `@pytest.mark.skip(reason="needs Docker +
    dataset")`, body `raise NotImplementedError`.

## Real OpenFOAM or mocks? Mocks/surrogates only

No test launches OpenFOAM or Docker. The C++ class
`openfoam/src/correctedKOmegaSST/correctedKOmegaSST.C` applies non-zero
corrections through a `nut_` surrogate and says so in its own comment
("until the Docker wmake probe passes, this nut-level coupling is the
shipped Mode A path … never presented as an equation solve"). Zero
correction returns early, so identity-by-construction is plausible in C++,
but it has never been compiled or run here. `Make/files` and `Make/options`
DO exist on disk (contrary to project_status.md:70).

The mesh is not the dataset mesh:
`openfoam/templates/periodicHill/system/blockMeshDict` header says "Periodic
hills placeholder mesh (flat walls; hill profile via
openfoam/meshing/hill_geometry.py in S1 refinement)" — flat walls, so a
baseline-vs-dataset comparison on it is invalid (finding D4).

## Can they run here? Logic yes; solver no; pytest itself no

Observed in this session (all via `subprocess.run(..., timeout=120)`):

| Command | Exit | Decisive output |
|---|---|---|
| `python audit/probes/gate_logic_probe.py` | 0 | `PASS test_identity_logic`, `PASS test_zero_correction_is_exact_identity`, `PASS test_oracle_logic`, `PASS test_dns_injection_targets_reduce_error` |
| `python -m pytest tests/integration/test_identity.py tests/integration/test_oracle.py -v` | 1 | `No module named pytest` |
| `python -m pytest --collect-only -q` | 1 | `No module named pytest` (audit/evidence/pytest-collect.txt) |
| `docker --version` | 127 (FileNotFoundError) | docker not on PATH (audit/evidence/versions-env.json) |
| `uv --version` | 127 (FileNotFoundError) | uv not on PATH; no `uv.lock`, no `.venv` |

The logic probe imports the real test modules and calls the four
non-skipped functions directly (pytest stubbed only inside the probe
process because pytest is absent). That proves the arithmetic, not a
solver identity/oracle result.

## What blocks the full-solver gate (each is BLOCKED_BY_ENV)

1. No Docker here → cannot run `docker run --rm opencfd/openfoam-default:latest simpleFoam -help`, cannot `wmake` the C++ class, cannot run baseline/identity/oracle solver tests.
2. No dataset: `data/raw/` contains only `.gitkeep` (P1 CONFIRMED). No DNS/RANS fields to compare against; baseline tolerance 0.05 cannot be evaluated.
3. Flat placeholder mesh (above) → even with Docker+data, baseline comparison needs the dataset curved-hill mesh.
4. No pytest/ruff/mypy and missing deps (sympy, scipy, sklearn, tenacity, zarr, foamlib absent; numpy/pydantic/fastapi/openai present; import smoke 47/56 OK) → the offline suite cannot run as `pytest` until the environment is built. No installs in this audit (guardrail 2).
5. `MODEL_API_KEY` is not set (name checked only) → no live API path anyway, and credits are forbidden in this audit.

Plan hard rule (plan S2, "Hard Decision Rule"): if the oracle fails or
cannot pass by Oct 27 EOD, activate the Frozen-RANS Fallback and label every
table/figure `frozen | short | full`. That rule fires tonight.

## What you must run tonight (outside this sandbox)

```powershell
# 1. Environment (generates uv.lock, H3)
uv sync
uv run pytest tests/unit tests/integration -q
# 2. Docker probe (S0.4)
docker run --rm opencfd/openfoam-default:latest simpleFoam -help
# 3. Dataset (P1) — real Kaggle/Closure-Challenge fetch, or offline path:
uv run python scripts/download_data.py --synthetic-fallback
# 4. Un-skip and run the two solver tests before any full-solver claim:
uv run pytest tests/integration -k "identity_solver or oracle_solver" -v
```

Until step 4 is green on a real baseline, every result is `frozen`.

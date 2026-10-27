# FlowForge v2 — Current Project Status

## TL;DR
The **Python core is substantively implemented** (not just stubs). The **data folders, library folders, tests/science, and OpenFOAM templates are empty** (only `.gitkeep`). The UI is skeletal. The OpenFOAM C++ solver stub exists but cannot be compiled yet.

---

## ✅ What Is Real and Done

| Module | File(s) | State |
|---|---|---|
| `flowforge/agents/runtime/client.py` | 142 lines | **Complete** — ModelRuntime, budget meter, tenacity retries, replay mode, structured output with repair |
| `flowforge/agents/runtime/event_logger.py` | 82 lines | **Complete** — append-only JSONL event log, prompt hash, replay lookup |
| `flowforge/agents/schemas.py` | 90 lines | **Complete** — All 7 Pydantic v2 role schemas with `risk_audit` guard |
| `flowforge/dsl/grammar.py` | 40 lines | **Complete** — INVARIANTS, SymPy symbol table |
| `flowforge/dsl/parser.py` | 71 lines | **Complete** — validate_candidate, complexity gate (≤25 nodes) |
| `flowforge/dsl/compiler.py` | 56 lines | **Complete** — compile_numpy, compile_cpp, guarded div/sqrt |
| `flowforge/dsl/evaluate.py` | 43 lines | **Complete** — candidate_anisotropy |
| `flowforge/dsl/fitting.py` | 29 lines | **Complete** — scipy curve_fit wrapper |
| `flowforge/dsl/codegen.py` | 22 lines | **Complete** — geometry codegen |
| `flowforge/physics/tensors.py` | 62 lines | **Complete** — invariants, normalized_tensors, tensor_basis, is_realizable |
| `flowforge/physics/frozen_rans.py` | 17 lines | **Complete** — frozen RANS baseline |
| `flowforge/ladder/ladder.py` | 138 lines | **Complete** — full 4-rung ladder, minimax scoring, halving |
| `flowforge/orchestrator/round.py` | 87 lines | **Complete** — run_round, synthetic_fields, champion selection |
| `flowforge/elegance/engine.py` | 59 lines | **Complete** — description_length, pick_champion |
| `flowforge/solver/runner.py` | 173 lines | **Complete** — OpenFOAMSolverRunner, Docker exec, caching, residual parse |
| `flowforge/solver/field_io.py` | 47 lines | **Complete** — foamlib field reader |
| `flowforge/redteam/attacks.py` | 40 lines | **Complete** — attack type definitions |
| `flowforge/redteam/generator.py` | 42 lines | **Complete** — attack generator |
| `flowforge/composer/gates.py` | 48 lines | **Complete** — composition gates |
| `flowforge/composer/evaluate.py` | 31 lines | **Complete** — composition evaluator |
| `flowforge/literature/harvester.py` | 53 lines | **Complete** — literature harvester stub |
| `flowforge/literature/cards.py` | 13 lines | **Complete** — literature card schema |
| `flowforge/data/zarr_store.py` | 103 lines | **Complete** — Zarr store manager |
| `flowforge/data/ingest.py` | 45 lines | **Complete** — data ingest pipeline |
| `flowforge/data/split_guard.py` | 41 lines | **Complete** — train/test split guard |
| `flowforge/render/error_map.py` | 35 lines | **Complete** — error map renderer |
| `flowforge/api/server.py` | 94 lines | **Complete** — FastAPI server |
| `flowforge/agents/harness/contracts.py` | 14 lines | **Stub** — placeholder |
| `flowforge/agents/harness/*/tasks.py` | 4 files, ~8-15 lines each | **Stub** — task placeholders |
| `flowforge/agents/tools/registry.py` | 15 lines | **Stub** — tool registry placeholder |
| `flowforge/agents/evals/thresholds.py` | 12 lines | **Stub** — eval thresholds placeholder |
| `scripts/` | 6 scripts | **Mostly complete** — run_experiment, evaluate_locked, download_data, run_arms |
| `openfoam/src/correctedKOmegaSST/` | `.C` + `.H` | **Stub** — OpenFOAM C++ class, not compilable (no Make/files content) |
| `openfoam/templates/periodicHill/` | `0/`, `constant/`, `system/` dirs exist | **Empty** — directory tree but no OpenFOAM config files inside |
| `prompts/*.yaml` | 7 role files | **Stub** — minimal placeholders (200-280 bytes each) |
| `configs/budgets.yaml` | 679 bytes | **Complete** |
| `configs/cases.yaml` | 505 bytes | **Complete** |
| `configs/experiments/baseline.yaml` | exists | **Complete** |

---

## ❌ What Is Missing (Empty Folders / No Content)

| Location | What's Missing |
|---|---|
| `data/literature/` | PDF papers, BibTeX, reference data for literature grounding |
| `data/raw/` | DNS reference datasets (e.g. periodic hill Re=10595) |
| `data/locked/` | Locked test set Zarr snapshots for the 5 benchmark cases |
| `data/processed/` | Pre-computed Zarr stores |
| `library/attacks/` | Red team attack scenario YAML/JSON files |
| `library/curriculum/` | Ordered learning curriculum YAML files |
| `library/findings/` | Stored research findings |
| `library/modules/` | Composition module definitions |
| `library/rejected/` | Rejected candidate archive |
| `openfoam/templates/periodicHill/0/` | `U`, `p`, `k`, `omega` initial condition files |
| `openfoam/templates/periodicHill/constant/` | `transportProperties`, `turbulenceProperties` |
| `openfoam/templates/periodicHill/system/` | `controlDict`, `fvSchemes`, `fvSolution`, `blockMeshDict` |
| `openfoam/templates/channel/`, `bump/`, `flatPlate/`, `squareDuct/` | Same — all 4 other case templates are empty |
| `openfoam/src/correctedKOmegaSST/Make/` | `files` and `options` for wmake |
| `tests/science/` | Only `.gitkeep` — no science/regression tests |
| `prompts/*.yaml` | Substantive system prompts (currently 200-280 byte placeholders) |
| `runs/` | No experiment run artifacts yet |

---

## 🔶 What Exists but Needs Work

| Item | Issue |
|---|---|
| `flowforge/agents/harness/*/tasks.py` | 4 harness task files are stubs — no real task logic |
| `flowforge/agents/tools/registry.py` | Just a dict placeholder — no actual tool callables registered |
| `flowforge/agents/evals/thresholds.py` | Threshold constants exist but no eval runner |
| `ui/src/pages/*.tsx` | 5 pages exist but are tiny (460-858 bytes) — no real rendering |
| `ui/src/components/*.tsx` | 4 components are minimal stubs |
| `openfoam/src/correctedKOmegaSST.C/.H` | The `b_delta` injection hook is sketched but `Make/files` is missing |

---

## Priority Order to Make It Runnable

1. **OpenFOAM templates** — `periodicHill` case files (S1 gate blocker)
2. **DNS reference data** — at minimum `data/raw/` with periodic hill DNS snapshot
3. **Prompts** — substantive system prompts for all 7 roles (agent loop blocker)
4. **Harness tasks** — fill in the 4 `tasks.py` stubs in `agents/harness/`
5. **Tool registry** — register actual tool callables in `agents/tools/registry.py`
6. **`openfoam/src/correctedKOmegaSST/Make/`** — `files` + `options` for compilation
7. **Science tests** — `tests/science/` regression tests
8. **Library files** — attacks, curriculum YAML seed content

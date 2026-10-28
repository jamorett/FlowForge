# Phase 2 audit — S3 DSL/physics/elegance, S4b data, S5 ladder/literature/round/API

Scope: plan S3/S4b/S5 (plan lines 297–390), spec Phase 2 (spec:316–320), Elegance (spec:197–229), candidate format (spec:133–141). `project_status.md` treated as unverified. `data/locked/` never opened. No installs/network/Docker/Meta API. Rows: [phase-2.json](phase-2.json) `P2-01..P2-18`.

Vocab: `VERIFIED` = executed here; `PRESENT_UNTESTED` = code+tests present, no passing run observed; `SKELETON` = shape only; `MISSING`; `BLOCKED_BY_ENV` = declared dep absent; `DECISION_NEEDED` = semantics unsettled.

## Environment: missing deps are env, not code

`sympy, sklearn, scipy, zarr, pytest, pdfplumber, tenacity` absent; `numpy, pydantic, fastapi, httpx, openai` present. All declared in [pyproject.toml](../../pyproject.toml) (`sympy>=1.12`, `scikit-learn>=1.4`, `zarr>=2.17,<3`, dev `pytest>=8`). No `uv.lock`, no `.venv` ([versions-env.json](../evidence/versions-env.json)). Therefore [import-smoke.txt](../evidence/import-smoke.txt) `dsl/*, literature/* = No module named 'sympy'`, `fitting = sklearn` is **BLOCKED_BY_ENV**, not a code bug. Same for `python -m pytest` exit 1 ([pytest-run.txt](../evidence/pytest-run.txt)).

## Reachability (who calls it)

| Module | Callers |
|---|---|
| `validate_candidate` ([parser.py:78](../../flowforge/dsl/parser.py:78)) | compiler/codegen/evaluate, `ladder.rung0`, `round` champion loop, tests |
| `candidate_anisotropy` ([evaluate.py:26](../../flowforge/dsl/evaluate.py:26)) | ladder rung1/rung3, `round.short_eval`, tests — **single T1 term only** |
| `production_target/anisotropy_target` | `ingest.py:37-40`, integration/unit tests |
| `guard_path` ([split_guard.py:38](../../flowforge/data/split_guard.py:38)) | only `ingest.py:27` on `data/processed/<case>` (never locked) + direct tests. **No swarm tool calls it** |
| `ingest_case`, `harvest`, `read_case` | **nobody** (definitions only; `read_case` only in scratch probe) |
| `run_ladder` | `round.py:49`; tests use `run_ladder_rung01` only |
| `search_cards` ([registry.py:17](../../flowforge/agents/tools/registry.py:17)) | registered, returns `[]` — stub-scan hit reconciled: intentional S5 placeholder, still empty |
| `run_round` | CLI `main`, tests `test_ladder/test_round_champion` mock-only |
| `ws_events` ([server.py:99](../../flowforge/api/server.py:99)) | FastAPI route `/ws/events`; UI is consumer (not audited here) |

Stub-scan reconciliation ([stub-scan.txt](../evidence/stub-scan.txt)): `round.py` mock/synthetic hits are the designed offline path (real ladder, synthetic fields), not hidden mocks of a real path — there is no real path. `harvester.py:23 Placeholder` confirmed. `registry return []` confirmed. `event_logger/server return []` are empty-log fallbacks, by design.

## Gate check — UNVERIFIABLE

Exact gate (spec:320, plan:361): *one research group completes a full round unattended + every step in event log.* Trial: equivalent of `python -m flowforge.orchestrator.round --mock-llm --round 1` executed **only in a temp cwd** via [phase2-gate.py](../probes/phase2-gate.py) (`subprocess.run(timeout=120)`, probe exit 0) so no `runs/` is written in the checkout:

```
mock_round_error: ModuleNotFoundError: No module named 'sympy'
  round.py:35 from flowforge.dsl.parser import ... -> parser.py:10 import sympy
guard: PermissionError logged=True 'DENIED role=theorist path=data/locked/x'
pure_rotation: s_max=0 I={I1:0,I2:-0.5,I3:0,I4:0,I5:0} T4_max=0.1667
ws_error (TestClient): PermissionError WinError 10013 (sandbox socket)
```

Gate = **UNVERIFIABLE** (blocked by env, sympy). By reading, even with sympy the mock round could not satisfy the gate: [round.py:33-74](../../flowforge/orchestrator/round.py:33) ignores `mock` except echoing it, always uses `synthetic_fields()` (8 synthetic points, target `0.5*T1`), calls no Board/Theorist/Coder/Analyst/Skeptic/RedTeam/Composer, fits no constants, and **writes no event log** — `api/server.py` reads `runs/<session>/events.jsonl` that `run_round` never creates. Champion DL uses empty constants ([round.py:60](../../flowforge/orchestrator/round.py:60)).

## S5.5 WebSocket pacing — VERIFIED (logic), wall-clock unverified

Critical check exact: [server.py:99-112](../../flowforge/api/server.py:99) `ws_events(ws, session='default')` — signature has **no pacing/count parameter at all**, so a bare subscribe cannot request a burst. `PACE_SECONDS=0.05` ([server.py:19](../../flowforge/api/server.py:19)); loop sends first line promptly, then `await asyncio.sleep(PACE_SECONDS)` after **every** line. [phase2-ws2.py](../probes/phase2-ws2.py) exit 0 (manual coroutine drive, no sockets): `messages=6 delays=[0.05,0.05,0.05,0.05,0.05] last={"type":"end","sent":5} PACED_OK`. Caveats: real wall-clock spacing unverified (sandbox blocks socketpair, WinError 10013); the `end` message also waits 50 ms after the last event; no backpressure beyond sleep.

## Verdicts

- **D1 — DECISION_NEEDED.** [grammar.py:37-44](../../flowforge/dsl/grammar.py:37): `div(a,b)=a/(b**2+1e-4)`, `sqrt(a)=sqrt(abs(a)+1e-4)`. Plan S3.3 mandates exactly this ([plan:315,329](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:315)); spec requires *only smooth operations* ([spec:141](../../v2%20Build%20spec.md:141)). `abs` has a kink at 0; `div` behaves as `a/b^2` for large `b`, not division by a strictly positive expression. Accept as stabilised semantics + document deviation, or rework grammar. Code follows plan; plan deviates from spec.
- **D2 — DECISION_NEEDED.** [frozen_rans.py:13-18](../../flowforge/physics/frozen_rans.py:13) `DeltaPk_target=-2k(a:S)` matches plan S3.2 ([plan:312](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:312)) and test expects `-0.4` ([test_physics.py:49](../../tests/unit/test_physics.py:49)), but the candidate-side definition is `DeltaPk=+2k(a:S)*h` ([plan:314](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:314)) — opposite sign. Whether plan:312 equals the SpaRTA k-equation residual needs the physics owner; fix plan+code together.
- **D6 — DECISION_NEEDED.** Probe-verified: pure rotation (`s=0, w!=0`) gives `I2=-0.5`, `T4_max=0.1667`, `T1=0`. Plan MUST ([plan:331](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:331)) says at `S=0` invariants `I1,I3,I4,I5` vanish — true, but a `g(I2)*T4` term in the full candidate format ([evaluate.py](../../flowforge/dsl/evaluate.py:26) currently T1-only, masking this) would **not** vanish. [engine.py:43](../../flowforge/elegance/engine.py:43) `zero_strain_ok` checks only a scalar. Define the limit state (`s->0 and w->0`, or require `g->0` for T4 terms) + add a pure-rotation test.
- **C2 — CONFIRMED.** No `configs/tolerances.yaml`. Tolerances are code constants: [engine.py:11-12](../../flowforge/elegance/engine.py:11) 1%/3%, [grammar.py:21](../../flowforge/dsl/grammar.py:21) 1e-4, [tensors.py:56](../../flowforge/physics/tensors.py:56) 1e-4, [engine.py:43,56](../../flowforge/elegance/engine.py:43) 1e-8, duplicated in `agents/harness/symbolic/tasks.py:6`. Plan:84 requires them in `configs/` before experiments.
- **C3 — CONFIRMED (Phase 2 slice).** [prompts/*.yaml](../../prompts/board.yaml) and [budgets.yaml](../../configs/budgets.yaml) carry `temperature`/`reasoning` per role; [client.py](../../flowforge/agents/runtime/client.py) `complete()` sends only `model/messages/max_tokens/response_format={type:json_object}` — no temperature/reasoning, no JSON-schema mode. Unverified against the live endpoint (no key, no network in audit).
- **P2 — CONFIRMED.** `openfoam/templates/{channel,flatPlate,bump,squareDuct}/` contain only `.gitkeep`. Canonical channel/flatPlate cases do not exist; rung2/3 have nothing real to run.
- **P3 — partly, main verdict Phase 5.** `library/{modules,attacks,findings,rejected,curriculum}/` are all only `.gitkeep`; no module writer or board-injection path exists. Noted here; lifecycle verdict belongs to Phase 5.

Other gaps: candidate format is single-term (`g*T1`), no `sum g^n T^n`, no `h(I)` production evaluator, no candidate content-hash/dedup (P2-04/P2-11); `minimax_score` unused by the ladder (raw MSE, not SST-normalised worst case, P2-12); snapping does not refit remaining constants (spec:220); literature harvester is fixture-grade (`MECHANISM:/FORM:` blocks, `doi='fixture'`, arXiv only, no pdfplumber, P2-14); prompts are 8-line stubs over real Pydantic schemas (P2-13).

## Signed account

Counts (18 rows): VERIFIED 2 (P2-10, P2-16), PRESENT_UNTESTED 4 (P2-01,05,09,12), SKELETON 5 (P2-04,11,13,14,15), MISSING 2 (P2-17,18), BLOCKED_BY_ENV 2 (P2-07,08), DECISION_NEEDED 3 (P2-02,03,06 — P2-03 also env-blocked). Gate: **UNVERIFIABLE**.

Top 5 gaps: (1) no real round — mock-only, synthetic, no event log, gate unprovable; (2) sympy/sklearn/zarr/pytest absent (env) so zero Phase-2 tests have an observed pass; (3) candidate format incomplete — single T1 term, no production `h`, no hash/dedup; (4) D1/D2/D6 semantics open (smoothness, Pk sign, pure-rotation limit); (5) channel/flatPlate templates missing + tolerances not in `configs/`.

Not checked: live Meta API (no key/network by rule), Docker/OpenFOAM rungs, real Zarr round-trip at scale, wall-clock WS timing (sandbox socket block), `scripts/evaluate_locked.py` internals, UI consumption of `/ws/events`. Confidence: high on code-reading verdicts, medium on gate (env-blocked).

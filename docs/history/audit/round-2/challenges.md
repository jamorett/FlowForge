# FlowForge v2 — Round-2 Challenges (Verifier Round 2, retry)

> Fresh independent verifier. Skeleton written first, expanded in place.
> Ignores stale `audit/round-2/phase-*.json` (19:48–19:49 prior static audit); the final round will be rebuilt.
> Read-only except this file + `audit/probes/verifier2-*.py`. Never opened `data/locked/`.
> Probes: [verifier2-main.py](../probes/verifier2-main.py), [verifier2-ws.py](../probes/verifier2-ws.py), [verifier2-ws2.py](../probes/verifier2-ws2.py) (all `python subprocess.run(timeout=120)` / direct runs via the explicit PowerShell path).

## 0. Method & scope (independent re-extraction)

**Spec gates (`v2 Build spec.md`, Phases section), re-read independently:**
Phase 0: baseline SST on one periodic hill in the container from one command.
Phase 1: oracle test passes + one hand-written candidate text → a priori score end-to-end (fallback: frozen-RANS-only if oracle fails by Oct 27 EOD).
Phase 2: one research group completes a full round unattended, every step in the event log.
Phase 3: red team breaks ≥1 candidate and the attack is visible in the UI.
Phase 4: a composed closure is scored on all training flows; feature freeze.
Phase 5: results table complete, wins and losses included (3 arms × 3 seeds, ≤3 locked milestones, mesh check).
Phase 6: submitted by Nov 4 21:00 ET (README reproduction + demo video from Replay).

**Plan S0–S7 (as reconstructed from round-1 row requirements + `audit/tasks/phase-*.md`):** S0 env/accounts/configs/CI/Docker; S1 solver runner/baseline; S2 C++ Mode A/B + identity/oracle; S3 tensors/DSL/elegance/fitting; S4 data/Zarr/locked guard/runtime/replay; S5 ladder/prompts/literature/round/WS; S6 red team/UI/composer; S7 arms/locked/mesh/ship. **Note:** no plan file itself exists in the repo tree (root listing + `prompts/` only); round-1 cites "plan L###" line numbers that a reader in this repo cannot verify — see CH-14.

**Round-1 inventory:** 111 rows (P0:18, P1:18, P2:18, P3:16, P4:12, P5:16, P6:13). Statuses: VERIFIED 10, PRESENT_UNTESTED 19, SKELETON 30, MISSING 28, BLOCKED_BY_ENV 17, DECISION_NEEDED 7. VERIFIED = P1-02, P1-08, P1-10, P2-10, P2-16, P3-01, P4-01, P4-02, P5-05, P6-07.

**Omissions vs round-1 (spec clauses with no dedicated row; keyword-checked against all 111 requirement+gap texts):**
- OM-1 Feature recomputation vs the dataset's own features within tolerance (spec Tests layer) — absent.
- OM-2 Agent-layer metrics tracked per prompt version (schema-valid rate, parse rate, duplicate rate, cost per round, spec Tests) — absent as a row (schemas exist, metrics do not).
- OM-3 Elegance tests as a set: limits pass on zero correction / fail on a deliberately wrong closure; description length identical for algebraically equivalent expressions after canonicalization; snapping refits remaining constants (spec Elegance + Tests) — only partially inside P2-05's gap.
- OM-4 Rung-0 equilibrium log-layer limit and smoothness/near-singular gradient check (spec Elegance hard filters) — P2-06 covers zero-strain/rotation only.
- OM-5 Literature etiquette + completeness: robots.txt/identifying user-agent, NASA TMR equation cards, top-30 hand-review artefact (spec Literature) — P2-14 covers APIs/cards only in part.
- OM-6 Solver-run caps per round + session dollar pause as enforced behaviour (spec Guardrails) — budgets exist as orphan config (P0-05) but no enforcement row.
- OM-7 Phase-4 feature freeze as a dated gate artefact — absent.

## 1. Environment facts (re-verified this round)

From [verifier2-main.py](../probes/verifier2-main.py) (exit 0): `python=3.12.10`; `which pytest/docker/uv/ruff/mypy = None` (all absent); imports present: numpy, pydantic, fastapi, openai; **missing: scipy, sympy, sklearn, tenacity, zarr, foamlib, pytest, pyvista, duckdb, pandas**; `uv.lock=False`, `.venv=False`, `MODEL_API_KEY_set=False`; `data/raw = [.gitkeep]` only; `runs/ = [.gitkeep, probe_s55]` (synthetic ticks only). Corroborated by `audit/evidence/versions-env.json` (uv/docker exit 127, node v24.22.0) and by `python -m pytest --collect-only -q` → exit 1 "No module named pytest" (inside probe). Git: single commit `6890af3 FlowForge v2: S0-S7 implementation`; status shows only untracked `audit/` + `estructura.txt`.

## 2. Re-run log (≥30% of VERIFIED + all critical)

VERIFIED re-attempted: 8/10 directly executed (80% ≥ 30%), plus all critical gates.

| Target | Command / probe | Observed |
|---|---|---|
| Oracle + identity (critical) | `python audit/probes/gate_logic_probe.py` | exit 0: `PASS test_identity_logic`, `PASS test_zero_correction_is_exact_identity`, `PASS test_oracle_logic`, `PASS test_dns_injection_targets_reduce_error` |
| Identity/oracle solver (critical) | tests scan in probe | 2× `@pytest.mark.skip` + `NotImplementedError` (`tests/integration/test_identity.py`, `test_oracle.py`); pytest absent exit 1 |
| Baseline (critical) | `scripts/run_experiment.py --help` via subprocess | exit 1 `ModuleNotFoundError: No module named 'flowforge'` from repo root without install; Docker absent → baseline unprovable here |
| P1-02 template files | verifier2-main file existence | `P1-02_files=True`; `P1-03_flat_header=True` (flat-walls placeholder confirmed in blockMeshDict) |
| Generated-candidate compile (critical) | `compile_candidate("0.1*T1")` | `ModuleNotFoundError: No module named 'sympy'` — compile path unexecutable in this env |
| Ladder (critical) | `minimax_score({a:1,b:4},{a:2,b:2})` | `2.0` (correct worst ratio); ladder import OK (numpy-only top level) |
| Event log / replay (critical) | EventLogger in temp dir | 1 line written; response without `prompt_hash` → `ValueError`; `FLOWFORGE_REPLAY=1` hit returns recorded response, miss → `RuntimeError`, replay-off → `None` |
| Locked guard (critical) | `guard_path` in temp cwd only | `data/locked/x` → `PermissionError`, log written (`DENIED role=theorist`); traversal `data/processed/../locked/x` → DENIED; `my_locked_notes/x`, `data/lockedness/x` → ALLOWED |
| P3-01 generator | `generate_attacks()` | 12 specs, alphas [0.5, 0.75, 1.25, 1.5], Re sweep, splits={validation}; alpha=2.0 → `AssertionError` |
| P4-01/P4-02 composer | `compose(ones, zeros, [0,1], w=1, b=0)` | `[0.5, 0.731…]` (sigmoid-correct), penalty `16.0` bits returned |
| P2-16 WS pacing (critical) | code read + fake-WS wall-clock attempts | Signature `(ws, session='default')` — **no pacing/count parameter**; `PACE_SECONDS=0.05`; first `send_text` occurs **before** any sleep, then `await asyncio.sleep(PACE_SECONDS)` after every line (≈20/s, first event prompt). Wall-clock socket timing blocked in this sandbox: Proactor loop `socketpair` → `PermissionError WinError 10013` (same blocker round-1 recorded); a Selector-loop retry hung and was terminated. Timing therefore held **by construction + recorded-sleep evidence from round-1**, not by a fresh wall-clock measurement — see CH-04. |
| Checker | `python audit/check_audit.py` | exit 1 FAIL: stale round-2 `phase-0 row 5: bad status 'UNVERIFIABLE'` + hygiene exit-code regex — expected until the final round is rebuilt |

Mocks/synthetic/dead-code scan (verifier2-main): callers outside their own module — `run_attack_suite`: none in production; `record_attack`: none; `ingest_case`: none; `compile_cpp`: none; `hill_height`: **zero callers at all** in `flowforge/`+`scripts/`; `render_png`, `harvest`: self-only; `guard_path`: only `ingest.py` (on a `data/processed/...` path that can never be locked). Swallowed exceptions: `flowforge/solver/field_io.py` `read_fields` — `except Exception: continue/pass` then silent `.npy`-sidecar fallback returning `{}`; `flowforge/ladder/ladder.py` `rung0` `except Exception: return False`, `rung1/rung2/rung3` convert any exception (including missing sympy) to `DIVERGED_PENALTY`. Skips: exactly the 2 solver tests above. Synthetic-as-real surfaces: `orchestrator/round.py` `synthetic_fields`/`MOCK_CANDIDATES` (12 synthetic/mock hits incl. tests), `scripts/run_arms.py --mock` formula scores, `scripts/download_data.py --synthetic-fallback` (100,3) arrays.

## 3. Challenges

Each CH cites the round-1 row id and the **exact proof** that would close it. All remain unresolved unless listed in §4.

- **CH-01 — P1-02 (VERIFIED overclaim risk).** VERIFIED means only "template files exist"; the mesh is the flat placeholder (P1-03, confirmed `flat walls` header) and nothing was meshed or run. *Proof needed:* a `blockMesh` + baseline `simpleFoam` log on the curved/dataset mesh, or downgrade P1-02 to PRESENT_UNTESTED in the rebuilt final round.
- **CH-02 — P6-07 (VERIFIED contradicts its own gap).** The row's gap admits the ModelRuntime client replay was never executed (tenacity absent). This round verified only `EventLogger.replay_lookup` (hit/miss/off). *Proof needed:* with deps installed, `FLOWFORGE_REPLAY=1` through `ModelRuntime.complete_structured` returning a recorded response with zero network, miss raising; otherwise downgrade to PRESENT_UNTESTED.
- **CH-03 — P5-05 (VERIFIED = mock bookkeeping only).** Mock arm scores are `len(arm)/seed` arithmetic; real mode returns `[]` + "needs S1-S6". Any quotation of these numbers as results would be synthetic-as-real. *Proof needed:* 9 real run dirs with hashes/scores/seeds (T5.3), or an explicit "bookkeeping-only, never reportable" label wherever P5-05 is cited.
- **CH-04 — P2-16 (WS pacing: wall-clock unproven; two defects).** (a) No fresh wall-clock timing was obtainable in this sandbox (WinError 10013; Selector retry hung/terminated) — VERIFIED rests on code construction + round-1 recorded sleeps. (b) The `end` message is sent only after a final 50 ms sleep, and the handler streams only the file snapshot present at connect (no live tail for events appended later). *Proof needed:* outside the sandbox, a bare `ws://…/ws/events` subscribe (no pacing/count sent) with per-message timestamps showing first message prompt and gaps ≈0.05 s; plus a decision/fix for live-tail and end-message delay.
- **CH-05 — P2-10 (locked guard: function verified, boundary unenforced, semantics loose).** No agent tool/registry path calls `guard_path`; its only caller guards a never-locked processed path; `scripts/evaluate_locked.py` does not pass through the guard and never scores anything (logs intent, exits 0 — a false-positive milestone if invoked). `_is_locked` denies **any** path containing a `locked` segment (comment claims a `data/locked` pair rule; code returns `True` for any match), uses lexical folding only (no symlink/resolved-path handling), and logs to a cwd-relative `runs/vault_access.log`. *Proof needed:* integration tests at the real tool boundaries (swarm denied+logged, evaluator-only path works), resolved-path/symlink cases, and an evaluator that actually scores or exits non-zero.
- **CH-06 — P4-01/P4-02 (VERIFIED formula, broken composition path).** Scalar `(w,b)` + single invariant only; the 16-bit penalty is computed then dropped before `description_length`/`pick_champion` (P4-05); `evaluate_composition` `zip(preds, targets)` silently drops the last training flow (round-1 phase-4 probe: targets `[0,0,99]` → `worst_error=0.0, beats_single=True`). *Proof needed:* fix the zip/comparand bug with a last-flow regression test, wire penalty into champion selection, then re-run the composer probe.
- **CH-07 — P3-01 (VERIFIED generator, dead downstream).** `generate_attacks` is correct, but no FlowSpec is ever meshed/solved/scored; `hill_height`/`wall_points` have zero production callers; `run_attack_suite` and `record_attack` have zero production callers; `library/attacks/` holds only `.gitkeep`. Phase-3 gate (break ≥1 candidate, visible in UI) is therefore unreachable. *Proof needed:* one end-to-end attack — generated flow meshed (or frozen-RANS scored), a real candidate broken, `record_attack` file written and rendered in the UI.
- **CH-08 — P1-07/P1-12/P1-13 (generated-candidate compile + a priori path blocked and unwired).** This round: `compile_candidate` → `ModuleNotFoundError: sympy`; `compile_cpp` has no caller inserting code into the C++ class or invoking `wmake`; Mode B marker still returns 0. *Proof needed:* after `uv sync` (outside audit): hand-written candidate → rung-1 score on real Zarr targets, and one generated candidate compiled with a timed, hash-cached build (<90 s rule).
- **CH-09 — Swallowed exceptions mask failures (P1-04/P2-12 adjacent).** `field_io.read_fields` swallows all foamlib errors and silently falls back to `.npy` sidecars (returning `{}` on total failure); ladder rungs convert **any** exception — including a missing-dependency import — into `DIVERGED_PENALTY`/`False`, so a broken environment looks like "all candidates diverged". *Proof needed:* narrow the except clauses, log/raise on missing deps vs candidate errors, and a test where a broken evaluator fails loudly instead of scoring 1e6.
- **CH-10 — P0-12/P1-05 baseline entry point not runnable as documented.** `python scripts/run_experiment.py --help` from the repo root exits 1 (`No module named 'flowforge'`) in the uninstalled env, before any Docker check. *Proof needed:* the documented one-command baseline (post-`uv sync`, with Docker + curved mesh + dataset) printing a converged profile error vs dataset RANS < 0.05, or the Phase-0 gate recorded FAIL/frozen with that command's real output.
- **CH-11 — P2-11/P2-15/P3-13 event-log chain broken in the middle.** `run_round` writes no `events.jsonl` (returns a dict only, always on synthetic fields); the API reads `runs/<session>/events.jsonl` that no production code creates; the only session on disk is `runs/probe_s55` synthetic ticks. EventLogger itself is verified (CH-held part), but "every step appears in the event log" (Phase-2 gate) cannot occur. *Proof needed:* one `run_round` execution emitting a real `events.jsonl` covering board→composer steps, then replayed via the WS endpoint.
- **CH-12 — PRESENT_UNTESTED cluster must not upgrade without execution (P0-02, P0-05, P0-06, P0-09, P0-15, P1-04, P1-06, P1-16, P1-17, P2-01, P2-05, P2-09, P2-12, P3-04, P3-07, P3-13, P4-07, P4-12, P5-08).** Spot-falsification this round found no false VERIFIED upgrades, but: budgets/cases configs have zero loaders, `ingest_case` has zero callers, and no pytest run exists anywhere. *Proof needed (per row):* the row's own `uv run pytest …` / CLI command exiting 0 in the built env — file existence and import-smoke do not suffice.
- **CH-13 — `audit/check_audit.py` loopholes (see §5).** The checker currently FAILs (2 findings) only because of the stale round-2 file; once rebuilt it can PASS while every CH-01…CH-12 stands, because it validates shape, not truth. *Proof needed:* close §5 items L1–L5 (evidence must reference an existing file/command output; duplicate-id and coverage checks; fingerprint must cover staged+untracked content) and re-run to PASS with the challenges file still honestly listing unresolved items (the 3-round escape must not be the mechanism).
- **CH-14 — Missing rows + missing plan (OM-1…OM-7, §0).** Round-1's 111 rows omit the seven spec clauses listed in §0, and the cited plan document is not in the repo, so "plan L###" evidence is unverifiable from the checkout. *Proof needed:* add rows for OM-1…OM-7 (or explicit DECISION_NEEDED exclusions) in the rebuilt final round, and commit or cite an immutable reference for the plan text.

## 4. Held after falsification

These were attacked this round and **held** (no challenge, or challenge limited to scope noted above):

- **P1-08 identity logic** — `gate_logic_probe` exit 0, re-run fresh: zero-correction diff 0 at TOL 1e-6; logic only, solver identity remains BLOCKED_BY_ENV (P1-09, undisputed).
- **P1-10 oracle logic** — same probe: SpaRTA target arithmetic/sign and the synthetic 0.70-ratio inequality pass; explicitly *not* a solver injection result (docstring-labelled), solver oracle remains BLOCKED_BY_ENV (P1-11).
- **P2-10 locked guard (function level)** — denied + logged in a temp cwd, traversal folded, non-vault lookalikes allowed (boundary/semantics issues are CH-05, not a falsification of the function).
- **P3-01 generator** — 12-spec cross-product, validation-only, out-of-range alpha refused (downstream deadness is CH-07).
- **P4-01/P4-02 composer kernel** — blend values match the sigmoid formula exactly; 16-bit penalty returned per gate (dropping/zipping defects are CH-06).
- **Ladder minimax** — worst-case SST-ratio semantics correct (`2.0` on the probe pair); halving keeps top 50% by construction.
- **EventLogger core** — append-only write, missing-hash `ValueError`, replay hit/miss/off semantics all reproduced in a temp dir (chain integration is CH-11; client-level replay is CH-02).
- **WS pacing by construction (P2-16 core)** — bare subscribe cannot request pacing/count; server sends first event promptly then sleeps 0.05 s after every line (≈20/s) — held as code behaviour; wall-clock proof is CH-04.
- **Environment/BLOCKED_BY_ENV rows** — pytest/docker/uv/ruff/mypy absence and the 10 missing declared deps were independently reproduced; BLOCKED_BY_ENV is the honest status, not an excuse (declared in `pyproject.toml`, no `uv.lock`/`.venv`).

## 5. `check_audit.py` loopholes

- **L1 — Evidence is free text.** `check_phase_jsons` only requires non-empty `id/requirement/status/evidence` (lines 57–63); a VERIFIED row with `evidence: "trust me"` passes. No evidence path is opened, no command re-run, `gap` not required, duplicate ids and per-phase row-count/coverage never checked.
- **L2 — "Zero unresolved challenges" is a substring.** Line 143 passes if the phrase appears anywhere (even negated or quoted), and with ≥3 round dirs it passes **regardless** of unresolved challenges. It also only inspects first + last rounds (`rs[0]`, `rs[-1]`, sorted lexicographically by path — `round-10` would sort before `round-2`).
- **L3 — Fingerprint is porous.** Only the unstaged tracked `git diff` is hashed; staged content and untracked **file contents** are never hashed, status/untracked lines are merely substring-matched against `tree-before.txt` (extra or reordered lines pass, deletions of recorded lines are missed), and `git()` return codes are ignored, so a failing git reads as an empty, passing tree.
- **L4 — Existence, not content.** Evidence files, tasks, GATE.md need only exist; REPORT/hygiene checks are substring/regex matches (`exit code\D*\d+` twice anywhere). `pytest-run.txt` could record a failure and still pass.
- **L5 — Findings verdicts are shape-only.** Any non-empty `evidence` string and a verdict in either `status` or `verdict` passes; duplicate ids collapse silently in the dict; nothing ties a verdict to the pre-audit claim it adjudicates.
- Net effect: after the final round is rebuilt, `AUDIT CHECK: PASS` is compatible with every challenge in §3 remaining true. The checker gates paperwork, not physics.

## 6. Verdict

Phase gates on today's evidence: Phase 0 UNVERIFIABLE (no Docker/data), Phase 1 FAIL-full / frozen-RANS fallback correctly declared in `GATE.md`, Phase 2 UNVERIFIABLE, Phases 3–6 FAIL — matching round-1, now with fresh executions behind the logic-level claims. 8/10 VERIFIED rows re-executed; 7 held fully or in part (§4); the rest are scope overclaims or dead downstream paths (§3).

**Unresolved challenges: 14 (CH-01 … CH-14).** The phrase for a clean pass is deliberately not claimed.

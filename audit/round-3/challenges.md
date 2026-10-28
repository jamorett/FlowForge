# FlowForge v2 — Round-3 Challenges (Verifier Round 3, final)

> Fresh independent verifier. Skeleton written first, expanded in place.
> Read-only except this file + `audit/probes/verifier3-*.py`. Never opened `data/locked/`.
> No installs, network, Docker, or API calls. All `python` subprocesses used `timeout=120`.
> Probes: [verifier3-main.py](../probes/verifier3-main.py).

## 0. Method & scope (independent re-extraction)

**Question:** does the rebuilt final round (`audit/round-2/phase-{0..6}.json/.md`, 119 rows) honestly
encode the Round-2 verifier's dispositions in [round-2/challenges.md](../round-2/challenges.md)
(CH-01…CH-14, OM-1…OM-7, loopholes L1–L5), and do the surviving `VERIFIED` rows re-execute?

**Method:** (1) full status census of all 119 rows from the JSON files; (2) row-by-row check of every
CH disposition against the rebuilt `status`/`requirement`/`evidence`/`gap` text and the per-phase
"Round-2 challenge responses" in `phase-{0..6}.md`; (3) fresh execution of the critical probes and of
the surviving `VERIFIED` claims (see §2); (4) line-level re-read of [check_audit.py](../check_audit.py)
against L1–L5; (5) `git -c safe.directory=… status/log` corroboration (single commit `6890af3`, tree
clean except untracked `audit/` + `estructura.txt` — fingerprint inputs unchanged).

**Census (fresh, this round):** 119 rows — `VERIFIED` 6, `PRESENT_UNTESTED` 22, `SKELETON` 35,
`MISSING` 32, `BLOCKED_BY_ENV` 17, `DECISION_NEEDED` 7. Survivors: `P1-08, P1-10, P2-16, P3-01,
P4-01, P4-02`. Round-1 had 111 rows / 10 `VERIFIED`; the rebuild adds 8 rows (OM rows, §3 CH-14)
and downgrades 4 former `VERIFIED` rows (`P1-02, P2-10, P5-05, P6-07`).

## 1. Environment facts (re-verified this round)

- `python audit/probes/gate_logic_probe.py` → exit 0 (fresh): 4 logic `PASS`, solver tests present.
- `python audit/check_audit.py` → exit 1 (fresh, expected at skeleton time): 7× missing
  `round-3/phase-*.json` + missing final `findings.json` (both are lead-copy steps, not row errors)
  + `hygiene REPORT: before/after test exit codes missing` (pre-existing; hygiene was never executed).
  No fingerprint, evidence-shape, or findings failures — the L3 fingerprint matches `tree-before.txt`.
- Environment blockers from Round 2 stand unrebutted: pytest/docker/uv absent, 10 declared deps
  missing (incl. sympy, tenacity), no `uv.lock`/`.venv`, `data/raw` empty. `P6-07` spot: `tenacity`
  import → `ModuleNotFoundError` (fresh, verifier3 probe).

## 2. Re-run log (≥30% of VERIFIED + all critical)

Surviving `VERIFIED` re-attempted: **5/6 directly executed (83% ≥ 30%)**, 1/6 by construction.

| Target | Command / probe | Observed |
|---|---|---|
| Identity + oracle logic (critical, P1-08/P1-10) | `python audit/probes/gate_logic_probe.py` | exit 0: `PASS test_identity_logic`, `PASS test_zero_correction_is_exact_identity`, `PASS test_oracle_logic`, `PASS test_dns_injection_targets_reduce_error` |
| Red-team generator (P3-01) | `generate_attacks()` via verifier3-main | 12 specs, alphas `[0.5, 0.75, 1.25, 1.5]`, splits `{validation}` only |
| Composer kernel (P4-01/P4-02) | `compose(ones, zeros, [0,1], w=1, b=0)` | `[0.5, 0.731059]` (sigmoid-exact), penalty `16.0` bits returned |
| Composer defect (P4-06, carried) | `evaluate_composition` with targets `[0,0,99]` | `worst_error=0.0` — last flow silently dropped by `zip` at `evaluate.py:23`; defect live, correctly carried as `MISSING` |
| WS pacing (P2-16, critical) | source construction via verifier3-main | `PACE_SECONDS=0.05`; `ws_events` has no pacing/count parameter; first `send_text` precedes first `asyncio.sleep`. **By construction only** — no fresh wall-clock timing (sandbox `WinError 10013`, same blocker as Rounds 1–2) |
| Locked guard (P2-10, downgraded) | `guard_path` in temp cwd | `data/locked/x` → `PermissionError`; `my_locked_notes/x` → allowed. Function held; boundary status is the downgrade (§3 CH-05) |
| Template files (P1-02, downgraded) | file read via verifier3-main | periodicHill templates exist; `blockMeshDict` header confirms flat-walls placeholder |
| Checker (critical) | `python audit/check_audit.py` | exit 1, failures only: round-3 copy-pending files + hygiene exit codes (see §1, §5) |

All verifier3 checks passed (`RESULT: ALL PASS`, exit 0) after fixing two probe-side bugs
(temp-cwd cleanup, `evaluate_composition` arity) — neither touched production code.

## 3. Challenges — disposition of CH-01…CH-14

No new challenges are raised. Each Round-2 challenge was checked against the rebuilt rows:

| CH | Rebuilt disposition (verified this round) | Status |
|---|---|---|
| CH-01 (P1-02 overclaim) | `P1-02` downgraded `VERIFIED → PRESENT_UNTESTED`; gap: "files exist, flat mesh, never run" | Applied |
| CH-02 (P6-07 replay) | `P6-07` downgraded `VERIFIED → PRESENT_UNTESTED`; EventLogger held, ModelRuntime unexecuted (tenacity absent, re-verified) | Applied |
| CH-03 (P5-05 mock numbers) | `P5-05` downgraded `VERIFIED → PRESENT_UNTESTED`; requirement relabelled "BOOKKEEPING-ONLY, NEVER REPORTABLE AS RESULTS" | Applied |
| CH-04 (P2-16 wall-clock) | `P2-16` kept `VERIFIED` **only** on the narrowed "by-construction pacing ONLY" requirement; evidence/gap disclose wall-clock UNPROVEN + `end`-delay + no-live-tail defects | Applied (narrowed; wire proof is OPEN future work, §6) |
| CH-05 (P2-10 boundary) | `P2-10` downgraded `VERIFIED → PRESENT_UNTESTED`; gap records unenforced boundary, `evaluate_locked.py` false-positive risk, lexical-only semantics | Applied |
| CH-06 (P4-01/P4-02 path) | Kernels kept `VERIFIED` narrowed (kernel / return-value only); penalty-dropped carried as `P4-05 MISSING`, zip defect carried as `P4-06 MISSING` (zip re-proved live, §2) | Applied |
| CH-07 (P3-01 downstream) | Generator kept `VERIFIED` narrowed (function only); dead downstream carried as `P3-14 MISSING` (gate row) | Applied |
| CH-08 (compile/a-priori) | `P1-07/P1-12` stay `SKELETON`, `P1-13` stays `BLOCKED_BY_ENV` (sympy absent) | Applied |
| CH-09 (swallowed exceptions) | Recorded in `P2-09` gap (field_io) and Phase-2 account (ladder `DIVERGED_PENALTY` masking); no status upgraded on that path | Applied |
| CH-10 (baseline entry point) | `P0-12/P1-05` stay `BLOCKED_BY_ENV`; gaps carry the exact outside-sandbox commands | Applied |
| CH-11 (event-log chain) | `P2-11/P2-15` stay `SKELETON`; `P3-13` downgraded `PRESENT_UNTESTED → SKELETON` | Applied |
| CH-12 (no free upgrades) | Full cluster spot-checked (`P0-02/05/06/09/15, P1-04/06/16/17, P2-01/05/09/12, P3-04/07, P4-07/12, P5-08`): all remain `PRESENT_UNTESTED`; no file-existence upgrade found | Applied |
| CH-13 (checker loopholes) | L1–L5 disposition in §5: L1/L2/L3 + L5-duplicates addressed in code; L4 + evidence-depth residuals remain as checker hardening | Applied in part (residuals = future work, §6) |
| CH-14 (OM-1…OM-7 + plan) | OM rows added: `P2-19` (OM-1, MISSING), `P2-20`+`P5-17` (OM-2, MISSING, duplicated across phases — redundant but honest), `P2-21` (OM-3, SKELETON), `P2-22` (OM-4, SKELETON), `P2-23` (OM-5, SKELETON), `P0-19` (OM-6, SKELETON), `P4-13` (OM-7, MISSING). Plan sub-claim **rebutted**: `docs/plans/2026-10-26-flowforge-v2-implementation-plan.md` exists, 489 lines (fresh check), so `plan L###` citations are checkout-verifiable | Applied; Round-2 verifier's "no plan file" statement was wrong (root-only listing) |

## 4. Held after falsification

- **P1-08 / P1-10 (logic)** — gate probe exit 0 fresh; scope explicitly logic-only, solver
  counterparts `P1-09/P1-11` remain `BLOCKED_BY_ENV`. Held.
- **P2-16 (by-construction pacing)** — no pacing/count parameter exists to omit; first send precedes
  first sleep at `PACE_SECONDS=0.05`. Held **only** under the narrowed requirement text; any
  "proven over the wire" reading would be false (see §6 OPEN items). 
- **P3-01 (generator function)** — 12-spec cross-product re-executed; downstream deadness is
  carried by `P3-14`, not hidden. Held as narrowed.
- **P4-01 / P4-02 (kernel / returned penalty)** — sigmoid values and `16.0` re-executed; the
  dropped-penalty and zip defects are carried by `P4-05/P4-06 MISSING`, not hidden. Held as narrowed.
- **Downgraded four (`P1-02, P2-10, P5-05, P6-07`)** — each `PRESENT_UNTESTED` status matches the
  fresh evidence in §2; none overclaims. Held.
- **BLOCKED_BY_ENV census (17)** — env blockers independently re-observed (pytest/docker/uv/deps
  absent); no `BLOCKED_BY_ENV` row was used to excuse executable logic. Held.

## 5. `check_audit.py` loopholes — disposition of L1–L5

Re-read line-by-line against the Round-2 loophole text:

| Loophole | Disposition in current `check_audit.py` |
|---|---|
| L1 (evidence free text) | **Addressed (shape-plus).** Evidence must be ≥30 chars with a file/command pattern (`check_audit.py:67`), and `VERIFIED` requires an observed `exit 0` in evidence (`:69-70`). Residual: cited paths are not opened — fabricated-but-plausible text could still pass. |
| L2 (verdict substring, lexicographic rounds) | **Addressed.** Rounds sort numerically (`:36`); the clean-phrase test rejects a line with "not" before "Zero" (`:165-166`). Residual: a quoted clean phrase on its own line would still pass. |
| L3 (porous fingerprint) | **Addressed.** Hashes cover unstaged diff, staged diff, and untracked file **contents** (`:84-106`); stored status/untracked sets must match exactly (`:184-198`); git return codes are checked (`:89-90`). Fresh run: no fingerprint failure. |
| L4 (existence, not content) | **Partially open.** Evidence files/tasks/GATE.md still need only exist (`:112-129`); hygiene still passes on two `exit code\D*\d+` regex hits (`:177-178`); REPORT.md still substring sections (`:204-209`). Checker hardening, not a row-status error. |
| L5 (findings shape-only) | **Addressed for duplicates, partial on depth.** Duplicate finding ids now fail (`:142-143`); verdict + non-empty evidence still shape-only (`:148-155`). |

Net: the checker still gates paperwork more than physics, but the three load-bearing holes from
Round 2 (L1 `VERIFIED` without exit-0 evidence, L2 negated-phrase/lexicographic escape, L3
staged/untracked blindness) are closed in code. Remaining L4/L5-depth items are hardening work.

## 6. Verdict

Audit-correctness challenges (status accuracy of the 119 rebuilt rows): none outstanding.
Every CH-01…CH-14 disposition was applied or honestly narrowed with the defect carried in a
companion row; the OM-1…OM-7 omissions now have rows; 5/6 surviving `VERIFIED` claims re-executed
green and the sixth (P2-16) is verified by construction under an explicitly narrowed requirement.

Zero unresolved challenges

**OPEN items (env-blocked proofs / future work — NOT audit-correctness challenges).** These rows
already carry honest non-`VERIFIED` statuses, so they are future work tasks, not status errors:

- Baseline + solver identity/oracle on Docker with dataset and curved mesh (`P0-12, P1-05, P1-09,
  P1-11`) — needs `uv sync`, Docker host, dataset fetch; commands recorded in those rows' gaps.
- ModelRuntime replay through `complete_structured` with deps installed (`P6-07` proof).
- WS wall-clock pacing measurement outside the sandbox, plus live-tail and `end`-delay fix (`P2-16`
  gap defects; wall-clock blocked here by `WinError 10013` in all three rounds).
- Composer zip fix + last-flow regression test, penalty wiring into champion selection (`P4-05,
  P4-06` code fixes).
- Locked-boundary enforcement at agent tool boundaries and a scoring `evaluate_locked.py` (`P2-10,
  P5-08`).
- End-to-end unattended round emitting `events.jsonl` (`P2-11, P2-15, P3-13`); attack chain wiring
  (`P3-14`); OM-1…OM-7 implementations (rows exist, statuses honest).
- Hygiene execution with real before/after exit codes (`audit/hygiene/REPORT.md` currently records
  UNKNOWN — checker fails on this until hygiene actually runs).
- Checker hardening residuals: open cited evidence paths (L1), content-check hygiene/REPORT (L4),
  tie findings verdicts to claims (L5).

Phase gates on today's evidence (unchanged, honestly labelled): Phase 0 FAIL/frozen, Phase 1
FAIL-full / frozen-RANS-only, Phase 2 UNVERIFIABLE, Phases 3–6 FAIL.

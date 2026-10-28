# Phase 3 audit (Round 2) — S6 red team, renders, SAM, UI

Scope: rebuilt from round-1 `P3-01..P3-16`. Fresh round-2 auditor. Read [phase-3.json](phase-3.json), [challenges.md](challenges.md), `audit/evidence/*`, and source. `data/locked/` never opened. No installs/network/Docker/API. No browser/build run.

Vocab: `VERIFIED` = executed and production-reachable for the narrowed requirement as written; `PRESENT_UNTESTED` = code present, no passing production run observed; `SKELETON` = shape only; `MISSING`; `BLOCKED_BY_ENV`; `DECISION_NEEDED`.

## Round-2 challenge responses

- **CH-04 — UPHELD in part (Phase 3 slice, P3-13).** The WS handler is by-construction paced (see Phase 2, P2-16 kept VERIFIED on that narrowed scope, wall-clock UNPROVEN in sandbox). For Phase 3 the consequence is in P3-13's gap: replay/UI streaming inherits the no-live-tail defect (only the snapshot at connect is streamed) and the 50 ms-delayed `end` message.
- **CH-05 — noted, no Phase 3 row changed.** The Vault view (P3-11) is static prose with no API endpoint; evaluator-side guard enforcement is Phase 2 (P2-10, downgraded there). No locked data was opened.
- **CH-07 — UPHELD, P3-01 kept VERIFIED (narrowed to the generator function).** Evidence: fresh inline execution `generate_attacks()` = 12 specs, alphas `[0.5, 0.75, 1.25, 1.5]`, validation-only; `FlowSpec` refuses alpha 2.0 / train split; the generator is also called by `api/server.py matrix()`. Justification for keeping VERIFIED: the requirement in [phase-3.json](phase-3.json) is narrowed to the generator function only, which was executed and is production-reachable via the matrix endpoint. The gap states the UPHELD downstream verdict in full: no FlowSpec is ever meshed/solved/scored, `hill_height`/`wall_points` have zero production callers, `run_attack_suite`/`record_attack` have zero production callers, `library/attacks/` holds only `.gitkeep`, and the Phase 3 gate is unreachable (P3-14 MISSING). Downgrading the generator row itself would misstate a held function; the dead downstream is carried by P3-02/P3-04/P3-14.
- **CH-09 — UPHELD (adjacent note).** Ladder exceptions become `DIVERGED_PENALTY` and `field_io.read_fields` swallows foamlib errors (see Phase 2). Recorded as an adjacent note in P3-04's gap, since attack scoring reuses that a priori path and a broken environment would masquerade as candidate failure.
- **CH-11 — UPHELD, P3-13 downgraded PRESENT_UNTESTED → SKELETON.** Evidence: fresh count in [round.py](../../flowforge/orchestrator/round.py): `events.jsonl` 0, `EventLogger` 0; `run_round` writes no `events.jsonl`, returns a dict only on synthetic fields; the API reads `runs/<session>/events.jsonl` that no production code creates; the only session on disk is `runs/probe_s55` (5 synthetic ticks, no candidate/attack events). Justification: P3-13 requires one live-streamed session visible end to end; with the chain broken in the middle that cannot occur, so PRESENT_UNTESTED overstated it. P2-11/P2-15 (Phase 2) stay SKELETON for the same break.
- **CH-12 — UPHELD (no upgrades).** No Phase 3 PRESENT_UNTESTED row was upgraded without execution. P3-04 and P3-07 remain PRESENT_UNTESTED; P3-13 was downgraded (above). File existence (tracked `ui/dist`, on-disk `node_modules`) was not treated as a build proof for P3-07.
- **CH-14 — UPHELD on omissions, REBUTTED on the missing plan.** OM-1..OM-5 are Phase 2 clauses and were added there as P2-19..P2-23 (MISSING/SKELETON); no Phase 3 OM row was created. Rebuttal on plan: the plan exists in this checkout at [2026-10-26-flowforge-v2-implementation-plan.md](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md) (489 lines, git-tracked), so "plan L###" citations are verifiable here, contrary to the challenges file statement.

## Gate check

Phase 3 gate (red team breaks ≥1 candidate, attack visible in UI): **FAIL** (P3-14 MISSING). No candidate was attacked, no break recorded in `library/attacks/`, and no attack cell/event exists for the UI to show. The generator half is verified (P3-01, narrowed); everything downstream of it is dead code paths with zero production callers.

## Signed account

Counts (16 rows): VERIFIED 1 (P3-01, generator function only), PRESENT_UNTESTED 2 (P3-04, P3-07), SKELETON 9 (P3-02, P3-03, P3-05, P3-08, P3-09, P3-10, P3-11, P3-12, P3-13), MISSING 3 (P3-06, P3-14, P3-15), BLOCKED_BY_ENV 1 (P3-16), DECISION_NEEDED 0 (SAM confirm-or-cut decision still owed inside P3-06). Gate: FAIL.

Top 5 gaps: (1) attack chain never wired — generator → meshing/scoring → `record_attack` → `library/attacks/` → UI cell all dead (CH-07); (2) event-log chain broken in the middle, so no live session can stream (CH-11, P3-13 downgraded); (3) generated flows have no meshes or solver path (P3-02); (4) Inspector/Vault/Replay are static shells, Matrix cannot grey locked columns or open cells (P3-09..P3-12); (5) PyVista path absent and SAM undecided, harness fixtures + curriculum missing (P3-05, P3-06, P3-15).

Not checked: `npm run build`/`npm run dev` and any browser rendering, pytest suite (pytest absent), WebSocket wall-clock timing over a real socket, OpenFOAM meshing/solver (no Docker), SAM/Meta endpoint (no network/key), `data/locked/` contents (never opened). Confidence: high on reachability, counts, and gate FAIL (fresh execution of the generator, server signature/routes, and round.py event-log counts); medium on UI build plausibility (inferred from on-disk packages + tracked dist, not run).

Signed account

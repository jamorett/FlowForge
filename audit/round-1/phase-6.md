# Phase 6 audit — S7.4 ship: demo video, README, submit (round 1)

Scope: spec Phase 6 (Nov 4, submit 21:00 ET, gate=submitted) + plan S7.4
(demo video from Replay, README reproduce commands, submit ~Nov 4 14:00 ET,
7h buffer). Rows: [phase-6.json](phase-6.json) P6-01…P6-13. Tasks:
[audit/tasks/phase-6.md](../tasks/phase-6.md). Probe:
[audit/probes/phase6-probe.py](../probes/phase6-probe.py) (python
subprocess, timeout=120, exit 0). `project_status.md` treated as
unverified (H4). `data/locked/` never opened. No installs, network,
Docker, or Meta API.

## Gate verdict: FAIL

Gate = submitted. Nothing exists to submit: no demo video (zero
`.mp4`/`.mov`), no recorded session, no reproduce README, no results
table or champion from Phases 0–5. This is positively observed, not
untested, so FAIL rather than UNVERIFIABLE. The Nov 4 date is still
future; the verdict is on current ship-readiness.

## Who calls export / replay?

- `export_demo.py`: **nobody.** Caller search (exit 0, excluding
  audit/node_modules) finds only the spec tree listing and
  `estructura.txt`. [scripts/export_demo.py](/C:/Users/juanc/Desktop/FlowForge/scripts/export_demo.py:4)
  itself raises `SystemExit("Not implemented yet. See docs/plans.")`
  (probe exit 1).
- `reproduce_champion.py`: **nobody in code or README.** Only plan
  l.444 names it. Probe: with a hash it prints then exits 1
  ("Needs S1-S3 verification first"); without, argparse exits 2.
- Replay has three disconnected pieces:
  1. [flowforge/agents/runtime/event_logger.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/agents/runtime/event_logger.py:49)
     `replay_lookup` — **VERIFIED** at function level (probe: hit
     returns `{'text':'world'}`, miss raises `RuntimeError`).
  2. [flowforge/agents/runtime/client.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/agents/runtime/client.py:91)
     `ModelRuntime._complete_replay` — present, not executed here
     (`tenacity` absent, see import-smoke).
  3. [flowforge/orchestrator/round.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/orchestrator/round.py:33)
     — **no replay at all** (probe: no `replay`, no `EventLogger`);
     `--mock-llm` is synthetic fields, not a recorded session.
  The UI Replay page does not use any of them: it opens the
  server-paced WebSocket in
  [flowforge/api/server.py](/C:/Users/juanc/Desktop/FlowForge/flowforge/api/server.py:99).

## Is a demo video cut possible?

No. [ui/src/pages/Replay.tsx](/C:/Users/juanc/Desktop/FlowForge/ui/src/pages/Replay.tsx:5)
is a session-name input plus an append-only
[EventFeed](/C:/Users/juanc/Desktop/FlowForge/ui/src/components/EventFeed.tsx:6):
no scrubber, seek, pause-at-event, or in/out markers. The only
recorded session, `runs/probe_s55/events.jsonl`, is five synthetic
`{"type":"tick"}` lines (probe: no `response`, no `candidate`). The
spec's "three demo moments" are never enumerated anywhere — that is
P6-03, DECISION_NEEDED for the owner before filming.

## README reproduction vs reality

[README.md](/C:/Users/juanc/Desktop/FlowForge/README.md:1) is five
lines with zero commands (probe token check: no uv, docker, pytest,
reproduce, export_demo, FLOWFORGE_REPLAY, npm, or vite). Reality it
would have to describe: `uv`/`docker`/`pytest` are all absent here,
there is no `uv.lock` and no `.venv` (H3), and the working commands
live in [audit/GATE.md](/C:/Users/juanc/Desktop/FlowForge/audit/GATE.md:60)
and [.github/workflows/ci.yml](/C:/Users/juanc/Desktop/FlowForge/.github/workflows/ci.yml:1)
(`uv sync --extra dev || pip install -e ".[dev]"`), not in the README.
Every figure/table it should reproduce is also absent: `notebooks/`
holds only `.gitkeep`, there are no PNG figures, and
`scripts/run_arms.py --mock` fabricates scores as `seed%7+len(arm)`
— those numbers must never appear as results.

## Findings verdicts (proven in this phase)

| ID | Verdict | Evidence in this phase |
|---|---|---|
| H4 | CONFIRMED | `estructura.txt` invalid UTF-8, predates `audit/`, lists transient `pip-*` dirs absent from [tree.txt](/C:/Users/juanc/Desktop/FlowForge/audit/evidence/tree.txt:1); `project_status.md` false on templates/Make/scripts/solver (P6-13) |
| H3 | CONFIRMED | Probe: `uv.lock`/`.venv` absent, `uv` not on PATH (P6-11) |
| H6 | CONFIRMED (sample) | README.md:3 itself uses absolute `C:/Users/...` links |
| P1/P4 | CONFIRMED / BLOCKED_BY_ENV | No dataset or Docker, so no Phase 5 results exist to package (P6-12) |
| D5 | DECISION_NEEDED | Only replay gives reproducibility; `reproduce_champion.py` implements none of it (P6-10) |
| C/D/P (others) | not re-proven | Not re-audited in this phase; inherited gate FAILs cited in P6-12 only |

## Structural leftovers

- `estructura.txt` (232,562 B, cp1252 `tree` output) is stale: zero
  `audit` entries, transient `pip-build-tracker-*`/`pip-install-*`
  folders, and `__pycache__` noise, versus the 306-file
  [audit/evidence/tree.txt](/C:/Users/juanc/Desktop/FlowForge/audit/evidence/tree.txt:1).
  It should be deleted or regenerated at packaging; it is not evidence.
- `runs/probe_s55/` is a pacing probe, not a demo session; presenting
  it as one would be a false claim.

Signed account: counts — VERIFIED 1 (P6-07), PRESENT_UNTESTED 0, SKELETON 4 (P6-04, P6-06, P6-10, P6-13), MISSING 6 (P6-01, P6-02, P6-05, P6-08, P6-09, P6-12), BLOCKED_BY_ENV 1 (P6-11), DECISION_NEEDED 1 (P6-03); 13 rows total. Top 5 gaps: (1) no recorded session or champion/results from Phases 0–5, so nothing true to film or reproduce; (2) demo video and export_demo.py do not exist; (3) README has no reproduction commands and the env (uv/Docker/pytest) cannot run them here; (4) Replay has no scrubber and the three demo moments are undefined; (5) stale docs (estructura.txt, project_status.md, absolute-path README links) would mislead judges. Not checked: video tooling/editing software, submission portal/receipt process, UI build or browser rendering, client-level ModelRuntime replay (tenacity absent), any Phase 0–5 re-verification beyond citing their gate files. Gate: FAIL. Confidence: high.

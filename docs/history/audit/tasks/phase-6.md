# Tasks — Phase 6 (S7.4 ship, Nov 4)

Day-by-day fit is handled by the lead; hours/owner/risk/acceptance here.
Owners: A = physics/OpenFOAM, B = agents/API/UI.

1. Decide and name the three demo moments (both). 0.5h. Risk: filming
   starts before content exists. Accept: moment list with event
   timestamps in a script doc, one line each. Dep: none (decision).
2. Produce one real recorded session worth filming (B+A). 8h. Risk:
   high — needs Phases 0–5 gates, champion, red-team break; without
   them only a synthetic/mock session is possible and must be labelled
   as such. Accept: `runs/<session>/events.jsonl` with real
   candidate/score/response events + champion hash. Dep: Phases 0–5.
3. Add Replay scrubber: seek/pause/step by event index (B). 3h. Risk:
   medium. Accept: UI can jump to any event and hold it; server seek
   or client-side event list. Dep: 2.
4. Implement `scripts/export_demo.py` (B). 3h. Risk: medium. Accept:
   running it on the recorded session emits timestamped clips/frames
   or a shot list; exit 0. Dep: 2, 3.
5. Cut demo video from Replay around the three moments (B). 3h. Risk:
   medium (tooling untested). Accept: video file in repo-external
   submission folder + timestamp script matching moments. Dep: 1, 4.
6. Implement `scripts/reproduce_champion.py` (A+B). 4h. Risk: high —
   needs champion hash store and frozen/short/full labelling (D5:
   replay-based, not live LLM). Accept: outsider run reproduces
   champion errors <1e-5 from hash alone, exit 0. Dep: 2.
7. Write README reproduction section (B). 2h. Risk: medium. Accept:
   fresh-checkout commands for env (`uv sync` generating uv.lock),
   data fallback, tests, arms, champion reproduce, demo export; each
   command executed once and output pasted. Dep: 6; env validation
   needs uv/Docker machine (BLOCKED_BY_ENV here).
8. Fix stale docs: regenerate or delete `estructura.txt`, correct
   `project_status.md`, make README links relative (B). 1h. Risk:
   low. Accept: no absolute `C:/` links, no false Complete/Empty
   claims, estructura either absent or regenerated UTF-8. Dep: none.
9. Freeze and submit (both). 1h + buffer to Nov 4 21:00 ET (target
   14:00). Risk: high if 2/6 slip. Accept: submission receipt +
   tagged commit containing README, video link, results table with
   wins and losses and `frozen | short | full` labels. Dep: 1–8.

# FlowForge v2 audit report (Oct 27, 2026)

## 1. Gate decision

**Frozen-RANS-only for tonight (Oct 27 EOD) and until the solver path is
proven outside this sandbox.** Evidence and commands: [GATE.md](GATE.md).
Both solver tests are `@pytest.mark.skip` + `raise NotImplementedError`
(`tests/integration/test_identity.py:50-52`, `test_oracle.py:72-74`); the
four logic tests pass by direct call (gate probe exit 0); pytest, Docker
and uv are absent here (exit 1 / 127); `data/raw/` is empty; the hill mesh
is a flat placeholder. The plan's Hard Decision Rule (plan line 285)
fires. What you must run tonight is in GATE.md and §8 below. Label every
table and figure `frozen | short | full` from now on.

## 2. State of the project

FlowForge v2 is a broad, mostly real Python skeleton (119 audited
requirements: 6 VERIFIED under narrowed scopes, 22 PRESENT_UNTESTED, 35
SKELETON, 32 MISSING, 17 BLOCKED_BY_ENV, 7 DECISION_NEEDED) in which the
offline logic — SpaRTA target arithmetic, the locked-path guard function,
the sigmoid composer kernel, the red-team generator function and
by-construction websocket pacing — demonstrably works, but the entire
solver path (dataset, curved mesh, compiled C++, baseline, solver
identity/oracle), the unattended round with a real event log, the attack
chain, the experiment arms and the packaging layer are dead code,
mocks, or missing, and the declared environment itself does not exist
here (no `uv.lock`, no `.venv`, 10 declared dependencies absent, pytest
absent), so the honest posture is frozen-RANS-only with roughly a week
of defined work to Nov 4.

## 3. Per-phase table

| Phase | VERIFIED | PRESENT_UNTESTED | SKELETON | MISSING | BLOCKED_BY_ENV | DECISION_NEEDED | Gate |
|---|---|---|---|---|---|---|---|
| 0 (S0) | 0 | 5 | 5 | 3 | 5 | 1 | FAIL |
| 1 (S1,S2,S4a) | 2 | 5 | 3 | 0 | 7 | 1 | FAIL (full); frozen declared |
| 2 (S3,S4b,S5) | 1 | 5 | 8 | 4 | 2 | 3 | UNVERIFIABLE |
| 3 (S6 red team+UI) | 1 | 2 | 9 | 3 | 1 | 0 | FAIL |
| 4 (S6 composer) | 2 | 2 | 2 | 7 | 0 | 0 | FAIL |
| 5 (S7.1–S7.3) | 0 | 2 | 4 | 9 | 1 | 1 | FAIL |
| 6 (S7.4) | 0 | 1 | 4 | 6 | 1 | 1 | FAIL |

Details: `audit/round-3/phase-X.json` + `.md` (final round; Round 2
verifier challenges CH-01…CH-14 all applied, Round 3 verdict: Zero
unresolved challenges). Tasks per phase: `audit/tasks/phase-X.md`.

## 4. Pre-audit findings

| ID | Verdict | ID | Verdict |
|---|---|---|---|
| H1 pip temp folders at root | CONFIRMED | C3 API params unverified | CONFIRMED |
| H2 generated artifacts tracked | CONFIRMED | D1 div/sqrt grammar | DECISION_NEEDED |
| H3 no uv.lock | CONFIRMED | D2 ΔPk target definition | DECISION_NEEDED |
| H4 stale estructura/project_status | CONFIRMED | D3 hill overlap / Re10595 | DECISION_NEEDED |
| H5 no AGENTS.md | CONFIRMED | D4 flat mesh vs dataset | DECISION_NEEDED |
| H6 absolute plan link | CONFIRMED | D5 seed byte-identity | DECISION_NEEDED |
| C1 muse-code / wonder IDs | CONFIRMED | D6 zero-strain limit | DECISION_NEEDED |
| C2 tolerances not in configs | CONFIRMED | P1 data/raw empty | CONFIRMED |
| P2 four templates empty | CONFIRMED | P3 no cross-session library | CONFIRMED |
| P4 gate status | CONFIRMED (frozen-only) | | |

Evidence per verdict: `audit/round-3/findings.json`. Corrections to the
original claims: C2's premise undercounts `configs/experiments/*.yaml`
(4 one-line scaffolds); P2 is confirmed for the four named templates,
with periodicHill the exception (12 real files); project_status.md is
also wrong that periodicHill is empty and that `Make/files` is missing.

## 5. SKELETON and MISSING items ranked by critical-path impact

1. Dataset + manifest (`data/raw` only `.gitkeep`; downloader real path
   is a `SystemExit`) — everything solver-side depends on it. MISSING.
2. Curved-hill mesh (template is a self-labelled flat placeholder) —
   baseline comparison invalid until rebuilt. SKELETON.
3. Compilable/equation-level C++ injection (Mode A is a `nut_` surrogate;
   Mode B returns 0; never compiled here). SKELETON/BLOCKED_BY_ENV.
4. End-to-end unattended round emitting `events.jsonl` (`run_round`
   writes none; API reads a file nobody creates). SKELETON.
5. Role prompts, tool registry, harness tasks (stubs returning `[]`/dicts).
   SKELETON.
6. Attack chain: generator verified, but nothing meshes/scores/records an
   attack; `library/attacks/` is `.gitkeep` only. MISSING downstream.
7. Composer: kernel verified; gate fitting missing, 16-bit penalty
   dropped before champion selection, `evaluate_composition` zip bug
   silently drops the last flow. MISSING.
8. Experiment arms: `run_arms.py` real mode returns `[]`; mock scores are
   bookkeeping-only, never reportable. SKELETON.
9. Locked scoring (`evaluate_locked.py` logs intent, scores nothing),
   mesh-refinement check, results table, demo/replay packaging. MISSING.
10. `uv.lock`, tolerances config, AGENTS.md, OM-1…OM-7 rows
    (feature-recomputation check, per-prompt agent metrics, elegance
    test set, log-layer/smoothness rung-0 checks, literature etiquette
    artefacts, enforced caps, feature-freeze artefact). MISSING.

## 6. Task plan

Dependencies and acceptance commands per task: `audit/tasks/phase-X.md`.
Day by day (submission Nov 4, 21:00 ET; target submit ~14:00, 7 h buffer):

- **Oct 27 EOD (tonight):** you run §8 commands (uv sync, Docker probe,
  dataset fetch); declare frozen-only. Owners: you + A.
- **Oct 28:** dataset + curved mesh + baseline in container; un-skip
  solver identity/oracle; time one generated-candidate compile. A.
- **Oct 29:** decisions D1/D2/D6 logged by physics owner; prompts +
  registry + harness tasks; Zarr ingest wired to a caller; first
  unattended mock round emitting `events.jsonl`. A+B.
- **Oct 30:** red-team chain end-to-end (generated flow scored, first
  recorded break in `library/attacks/`). A.
- **Oct 31:** UI live on the websocket stream; red-team break visible;
  Phase 3 gate. B.
- **Nov 1:** composer fitting + penalty wiring + zip fix, or RP4 cut;
  multi-group session; **feature freeze EOD**. A+B.
- **Nov 2–3:** 3 arms × 3 seeds, ≤3 locked evaluations, mesh check,
  results table with losses. Buffer starts Nov 3 EOD.
- **Nov 4 ~14:00:** demo video from Replay, README reproduction, submit.
  Never cut: seeds, no-red-team arm, locked discipline, labels. Cut
  order: RP4 → SAM → UI polish.

## 7. Decisions

- **D1 div/sqrt:** recommend accepting them as a stabilised
  discretisation and documenting the deviation from the spec's
  smooth-only grammar in the methods text; changing the grammar now
  invalidates existing candidates/tests.
- **D2 ΔPk target:** physics owner must confirm whether
  `-2k(aΔ:S)` (target) vs `+2k(aΔ:S)·h` (candidate side) is the intended
  SpaRTA residual; fix plan and code together, never one alone.
- **D3 overlap:** after download, inspect the Closure Challenge README
  and curated manifest; if periodic hills overlap locked material, move
  those cases to validation. Existence of `periodic_hill_re10595` in the
  curated set is UNVERIFIABLE until then.
- **D4 mesh:** rebuild the template from the dataset hill profile;
  never compare flat-mesh runs against dataset RANS.
- **D5 reproducibility:** define reproducibility as replay-hash identity
  (recorded responses + fitted constants), not live-LLM seed identity.
- **D6 limit state:** define the zero-strain limit as s→0 **and** w→0
  together, or require `g(I2)→0` for T4 terms; pin it in
  `configs/tolerances.yaml` once Step H lands.
- **NEW D7:** pin the OpenFOAM ESI image closest to v2006 (dataset
  provenance) instead of `:latest`.
- **NEW D8:** coder model `muse-spark-1.3` until Contributor data terms
  are accepted; confirm or drop `wonder` → `muse-wonder-1.0` (C1).
- **NEW D9:** confirm the SAM 3.1 endpoint this week or cut it (already
  in the cut order).

## 8. Commands

Run these outside the sandbox (all BLOCKED_BY_ENV here):

```powershell
uv sync
uv run pytest tests/unit tests/integration -q
docker run --rm opencfd/openfoam-default:latest simpleFoam -help
uv run python scripts/download_data.py --synthetic-fallback   # offline
# or the real Kaggle / Closure-Challenge fetch into data/raw + manifest
uv run pytest tests/integration -k "identity_solver or oracle_solver" -v
uv run ruff check . ; uv run mypy flowforge
```

C3 probes (need network + credits — never run in this audit): one-token
`muse-spark-1.3` call checking the auth header, usage/reasoning-token
billing fields, `response_format={"type":"json_object"}` vs JSON-schema
mode, and truncation at `max_tokens=2048`.

Hygiene: review and run `audit/hygiene/cleanup.ps1` (dry-run by default)
for the H1 pip folders; Step H itself is blocked — see
`audit/hygiene/REPORT.md`.

## 9. Open disagreements

- **Step H not executed.** Two hygiene-child spawns with
  `worktree_isolation: true` were rejected
  (`workspace_git_probe_failed`). No branch, no commits, no hygiene
  edits exist. `audit/hygiene/REPORT.md` records this with real
  before/after exit codes (both 1, pytest absent). Re-run Step H where
  the git probe passes; do not merge anything until you approve.
- **Round-2 verifier error, rebutted:** it claimed the plan file is not
  in the repo; `docs/plans/2026-10-26-flowforge-v2-implementation-plan.md`
  exists (489 lines), so `plan L###` citations are verifiable. Recorded
  in Round 3 challenges §3 CH-14.
- **P2-16 websocket pacing** is VERIFIED only under the narrowed
  by-construction requirement; wall-clock timing was unobtainable in
  this sandbox in all three rounds (WinError 10013) — wire proof is
  OPEN future work in the row's gap, along with the live-tail and
  end-message defects.
- **Checker residuals (L4/L5-depth):** `check_audit.py` now closes
  L1–L3 and duplicate findings, but evidence paths are not opened and
  REPORT/hygiene remain content-light. It gates paperwork, not physics;
  the statuses above rest on the probes cited in each row.
- Verifier loop: 3 rounds run, Round 3 verdict "Zero unresolved
  challenges"; env-blocked proofs are listed as OPEN future work, not
  as resolved science.

**Stop. No feature implementation and no hygiene merge until you
approve this report.**

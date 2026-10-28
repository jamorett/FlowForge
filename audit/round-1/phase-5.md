# Phase 5 audit — S7.1–S7.3 experiments (round 1)

Scope: spec Phase 5 (l.333–337) + Tests/Science (l.259–281) +
RP1–RP6 (l.289–295), plan S7.1–S7.3 (l.426–436) + S7 guardrails
(l.438–445), [audit/GATE.md](../GATE.md), `audit/evidence/*`,
`configs/cases.yaml` + `configs/experiments/*`. Rows:
[audit/round-1/phase-5.json](phase-5.json) (P5-01…P5-16). Tasks:
[audit/tasks/phase-5.md](../tasks/phase-5.md). `project_status.md`
treated as unverified. `data/locked/` never opened or listed —
existence only via `git ls-files data/locked` → `data/locked/.gitkeep`.
No installs, network, Docker, or Meta API. `scripts/evaluate_locked.py`
and real-mode `run_arms.py` were **not** run (would consume/log budget);
only `--mock` was run. Probe: [audit/probes/phase5-probe.py](../probes/phase5-probe.py).

## Gate verdict: FAIL

Phase 5 gate = complete results table, 3 arms × 3 seeds, ≤3 locked
evals, mesh <2% (plan l.423,461; spec l.337).

| Leg | Command / check | Result |
|---|---|---|
| 3 arms × 3 seeds | `python scripts/run_arms.py --mock` (subprocess, timeout=120) exit 0: `swarm mean 6.0`, `swarm_no_redteam 17.0`, `sparse_baseline 16.0` — formula bookkeeping only; real mode [run_arms.py:29,33](../../scripts/run_arms.py:29) returns `[]` + `needs verified S1-S6` | FAIL (0/9 real runs) |
| ≤3 locked evals | [evaluate_locked.py:8,26](../../scripts/evaluate_locked.py:8) cap=3 + log; `runs/vault_access.log` absent → 0 recorded; script performs no scoring ([evaluate_locked.py:32](../../scripts/evaluate_locked.py:32)) | FAIL (no scores; cap untested) |
| Mesh <2% | Probe regex `mesh.*refin\|2x\|double.*resol` over `*.py`: 0 hits; no script/test/notebook | FAIL (absent) |
| Results table | `notebooks/` = `.gitkeep` only; no table/figures; no `frozen \| short \| full` label in code | FAIL (absent) |

FAIL, not UNVERIFIABLE: absence is positively observed in code, disk,
and the mock probe.

## What is real

- **Mock bookkeeping (P5-05 VERIFIED, narrow).** Stub-scan claim
  reconciled: [run_arms.py:29](../../scripts/run_arms.py:29)
  `scores = [float((seed % 7) + len(arm)) …] if args.mock else []`,
  real mode prints `needs verified S1-S6`. Mock means are
  `len(arm)` arithmetic (swarm `[5,6,7]` → 6.0±1.0), not results.
  [summarize()](../../scripts/run_arms.py:20) correctly asserts
  exactly 3 seeds and computes mean/stdev.
- **Locked cap skeleton (P5-06).**
  [evaluate_locked.py:14](../../scripts/evaluate_locked.py:14)
  counts `LOCKED_EVAL` lines, refuses at 3, logs milestone+reason.
  It never scores, validates milestone names, or reads any case.
- **Guard function (P5-08).**
  [split_guard.py:33](../../flowforge/data/split_guard.py:33)
  `guard_path` denied `data/locked/x` with a logged `DENIED` in the
  probe (exit 0, log redirected/removed) and allowed `data/raw/`.
  It denies *any* `locked` path component, and no agent tool calls it.
- **Reproduce scaffold (P5-11).**
  [reproduce_champion.py](../../scripts/reproduce_champion.py) exists
  but always exits `Needs S1-S3 verification first`. Replay machinery
  it would need exists at
  [event_logger.py:49](../../flowforge/agents/runtime/event_logger.py:49)
  and is never used by it.

## Findings verdicts

- **P3 (no cross-session library module) — CONFIRMED.**
  `library/{modules,attacks,rejected,findings,curriculum}/` hold only
  `.gitkeep`. Search for library load/save, `candidate→verified→
  champion` lifecycle, staleness/re-verification, board summary, or
  dedup (spec l.185–194): zero implementations. The sole writer is
  [attacks.py:20](../../flowforge/redteam/attacks.py:20)
  `record_attack` (no production caller, overwrites by
  `candidate[:8]`, stores no score). P5-12.
- **D3 (Closure Challenge overlap) — DECISION_NEEDED.**
  Train = `periodic_hill_re5600/re10595` (curated,
  [cases.yaml:3](../../configs/cases.yaml:3)); locked =
  `square_duct`/`nasa_wall_mounted_hump` (closure_challenge).
  Spec l.97 places periodic hills in the Closure Challenge *test*
  set, and the curated dataset is absent (no `data/raw/manifest.json`;
  [download_data.py:20](../../scripts/download_data.py:20) lists
  `re10595` but its real path exits without network, synthetic path
  fabricates `(100,3)` arrays). Whether `periodic_hill_re10595`
  exists in — or duplicates a test case of — the curated/Closure
  sets cannot be checked here. Owner must compare the real manifest
  and Closure README test list before any held-out claim. P5-13.
- **D5 (byte-identical hashes, live LLM) — DECISION_NEEDED.**
  Plan l.440 demands same-seed byte-identical candidate hashes;
  live LLM calls cannot guarantee that. The honest mechanism in-repo
  is replay ([event_logger.py:55](../../flowforge/agents/runtime/event_logger.py:55),
  miss = error, zero network). Lead must redefine reproducibility
  as replay + content hashes (solver
  [runner.py:80](../../flowforge/solver/runner.py:80)) and rewrite
  `reproduce_champion.py` against it. P5-11.
- **H4 (project_status.md claims) — partly CONFIRMED (sampled).**
  Overstatements sampled true: `scripts/` called “mostly complete”
  while `run_arms`/`evaluate_locked`/`reproduce_champion` are
  bookkeeping/scaffolds above, and experiment YAMLs are 2-line
  scaffolds. Two status claims are now *stale the other way*:
  periodicHill templates and `correctedKOmegaSST/Make/{files,options}`
  exist on disk (ls exit 0), contradicting status “Empty”/“missing”
  rows — contents still placeholder-grade per GATE.md (flat mesh),
  so neither “done” nor “empty” is accurate. Treat the file as
  unverified, as instructed.

## Dependencies

Phase 5 inherits BLOCKED_BY_ENV (P5-16): GATE.md frozen-RANS-only
(no Docker/uv/dataset/API key, flat mesh), Phase 3 gate FAIL, no
champion pool, no library (P5-12), `tests/science/` empty (P5-15).
Per plan l.445 (freeze), Phase 5 may not invent replacement machinery
to bypass upstream gates.

## Signed account

- Counts (16 rows): VERIFIED 1 (P5-05, mock bookkeeping only),
  PRESENT_UNTESTED 1 (P5-08), SKELETON 4 (P5-01, P5-02, P5-06,
  P5-11), MISSING 8 (P5-03, P5-04, P5-07, P5-09, P5-10, P5-12,
  P5-14, P5-15), BLOCKED_BY_ENV 1
  (P5-16), DECISION_NEEDED 1 (P5-13; D5 decision owed inside P5-11).
- Gate: **FAIL** — 0/9 real runs, 0 locked scores, no mesh check,
  no results table.
- Top 5 gaps: (1) no arms execution harness or budgets (P5-03/04);
  (2) locked evaluator logs intent but scores nothing, on an absent
  dataset (P5-07); (3) no cross-session library, so arms start cold
  (P5-12, P3 CONFIRMED); (4) mesh-refinement check absent (P5-09);
  (5) champion reproduction undefined until D5 replay decision
  (P5-11).
- Not checked: `evaluate_locked.py` execution (forbidden — consumes
  budget), real-mode arms (refused by design), locked data (never
  opened), Docker/solver, live API, second-machine parallelism,
  pytest suite (absent, exit 1 in evidence).
- Confidence: high on code/disk absence and mock behaviour (all
  probed, exit 0); low on dataset provenance (D3 — dataset absent
  by design here).

Signed account

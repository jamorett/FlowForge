# Phase 4 audit — S6 composer (Round 2)

Scope: spec Phase 4, plan S6.2 in [implementation plan](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:399). Rows: [phase-4.json](phase-4.json) P4-01..P4-13. Probe: [r2p456-probe.py](../probes/r2p456-probe.py) exit 0 (`python subprocess.run(timeout=120)` for sub-checks). `data/locked/` never opened. No installs/network/Docker/API.

## Gate verdict: FAIL

Composed closure scored on all training flows: no fitting (P4-03), no joint composite (P4-04), no modules/targets on disk (P4-10), and [evaluate.py:23](../../flowforge/composer/evaluate.py:23) `zip(preds,targets)` drops the last flow.

## Round-2 challenge responses

- **CH-06 — UPHELD (defects) / kernel HELD (narrowed).** Kernel re-proved: `compose=[0.5,0.731059]`, penalty `16.0`. P4-01/P4-02 narrowed to kernel/return-value only and kept VERIFIED on that scope. Penalty-dropped is UPHELD: probe `dl_params=[n_nodes,constants]`, `dl_has_gate=False` — carried as P4-05 MISSING. Zip bug is UPHELD and re-proved: targets `[0,0,99]` → `worst_error=0.0, beats_single=True` — carried as P4-06 MISSING with fix+last-flow regression test required.
- **CH-12 — UPHELD for P4-07, P4-12.** Both kept PRESENT_UNTESTED; probe `pytest exit 1 No module named pytest`. No upgrade without execution.
- **CH-14 (OM-7) — UPHELD, row added.** P4-13 MISSING: probe found feature-freeze text only at plan:445,459; no dated freeze artefact.
- **CH-14 (plan missing) — REBUTTED in part.** Plan exists: [2026-10-26-flowforge-v2-implementation-plan.md](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md) (489 lines; S6.2:399, freeze:445,459), so plan citations are now verifiable in-repo. The OM-row part of CH-14 remains UPHELD (see P4-13; OM-1,3-6 belong to other phases).
- **CH-02/CH-03 — not in this phase** (P6-07 / P5-05; see phase-6/phase-5 Round-2 files).

## What changed vs Round 1

P4-01/P4-02 VERIFIED retained only after narrowing; all other Round-1 statuses unchanged; P4-13 (OM-7) added.

## Signed account

Counts (13 rows): VERIFIED 2 (P4-01 kernel, P4-02 returned penalty), PRESENT_UNTESTED 2 (P4-07, P4-12), SKELETON 2 (P4-04, P4-09), MISSING 7 (P4-03, P4-05, P4-06, P4-08, P4-10, P4-11, P4-13). Gate Phase 4: **FAIL**. Top gaps: (1) no gate fitting; (2) zip drops last flow + penalty dropped before champion selection; (3) no joint composite, no module pool, Composer step unreachable in round.py (`round_imports_composer=False`); (4) no feature-freeze artefact (OM-7). Not checked: live API composer, Docker/OpenFOAM scoring, locked data. Confidence: high (numpy-only kernel executed).
Signed account

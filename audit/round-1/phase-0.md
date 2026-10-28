# Phase 0 (S0) audit — Round 1

Scope: spec Phase 0 (Oct 24–25) + plan S0/S0.1–S0.4. Rows [phase-0.json](phase-0.json): `P0-01`…`P0-18`. Method: opened every S0 code/config file in full; traced callers; reconciled with Step-0 evidence. [project_status.md](../../project_status.md) treated as unverified throughout (H4).

## Requirements and reachability

| ID | Requirement (source) | Reachable from | Status |
|---|---|---|---|
| P0-01 | GitHub/Kaggle/Meta accounts (spec L305) | nothing in repo | BLOCKED_BY_ENV |
| P0-02 | S0.1 pinned `pyproject.toml` (plan L154–191) | pip/uv installers only | PRESENT_UNTESTED |
| P0-03 | `uv sync` generates `uv.lock` (plan L191) | — (file absent) | MISSING |
| P0-04 | uv environment executable (plan L151) | every `uv run …` command | BLOCKED_BY_ENV |
| P0-05 | S0.2 `budgets.yaml` (plan L193–209) | no loader; `client.py:19` hardcodes the limit | PRESENT_UNTESTED |
| P0-06 | S0.2 `cases.yaml`, 6 frozen splits (plan L210–213) | docstring only ([ingest.py:4](../../flowforge/data/ingest.py:4)) | PRESENT_UNTESTED |
| P0-07 | `configs/experiments/*` runnable configs (spec L55) | [run_experiment.py:13](../../scripts/run_experiment.py:13) prints, never parses | SKELETON |
| P0-08 | S0.3 real download + SHA-256 manifest (plan L216) | `__main__` only; real path exits | SKELETON |
| P0-09 | `--synthetic-fallback` offline (plan L230) | [ci.yml:19–20](../../.github/workflows/ci.yml:19) | PRESENT_UNTESTED |
| P0-10 | S0.4 Docker image, ESI pinned (spec L28) | [compose.yaml:2–6](../../docker/compose.yaml:2) | SKELETON |
| P0-11 | `simpleFoam -help` probe exit 0 (plan L220) | manual command only | BLOCKED_BY_ENV |
| P0-12 | Spec gate: baseline SST in container, one command (spec L306–308) | [run_experiment.py:16–22](../../scripts/run_experiment.py:16) → Docker | BLOCKED_BY_ENV |
| P0-13 | CI lint+unit+tiny OpenFOAM case, green (plan L151; spec L281) | GitHub push only | SKELETON |
| P0-14 | Toolchain versions printed (plan L151) | manual probes | BLOCKED_BY_ENV |
| P0-15 | Repo skeleton (spec L47–88) | imports | PRESENT_UNTESTED |
| P0-16 | Closure Challenge clone + README check (plan L151) | nothing | MISSING |
| P0-17 | Tolerances frozen in `configs/` (plan L84–86) | hardcoded in code/tests | MISSING |
| P0-18 | Real model IDs decided (spec L149) | [budgets.yaml:5](../../configs/budgets.yaml:5), [client.py:24](../../flowforge/agents/runtime/client.py:24) | DECISION_NEEDED |

Key reachability finding: Phase 0 config is write-only. Nothing loads [budgets.yaml](../../configs/budgets.yaml) or [cases.yaml](../../configs/cases.yaml); the dollar limit is re-hardcoded as `SESSION_LIMIT` in [client.py:19](../../flowforge/agents/runtime/client.py:19), and [run_experiment.py](../../scripts/run_experiment.py) ignores the content of the experiment YAML it is handed. Config edits therefore cannot change behaviour, and no test would notice.

## Phase gate check (exact, offline)

Plan S0 acceptance (plan L151): *versions printed, dataset manifest exists, CI green on skeleton.*

| Leg | Command / check | Result |
|---|---|---|
| Versions | `python --version` → `Python 3.12.10` exit 0; `uv --version`, `docker --version` → not recognised; [versions-env.json](../evidence/versions-env.json:4) uv/docker exit 127, node `v24.22.0` exit 0 | FAIL (2/4 legs) |
| Dataset manifest | Live listing: `data/raw/` contains only `.gitkeep` (0 bytes); no `manifest.json` | FAIL (proven) |
| S0.3 offline leg | `python scripts/download_data.py --synthetic-fallback` not re-run against the repo (would write `data/raw/`); code path [download_data.py:32–42](../../scripts/download_data.py:32) is deterministic and CI-wired, but no passing run is recorded; `pytest` legs exit 1 `No module named pytest` ([pytest-run.txt](../evidence/pytest-run.txt)) | UNVERIFIABLE |
| S0.4 probe | `docker run --rm opencfd/openfoam-default:latest simpleFoam -help` — docker absent, exit 127 per [versions-env.json](../evidence/versions-env.json:5) | UNVERIFIABLE here / FAIL in this env |
| CI green | [ci.yml](../../.github/workflows/ci.yml) exists; no GitHub run inspectable offline; workflow also lacks the spec's tiny OpenFOAM case and masks failures with `\|\|` fallbacks (L14, L16, L18, L20) | UNVERIFIABLE |

**Gate verdict: FAIL.** The manifest leg is disproven, not merely unobserved, and the uv/Docker legs fail in this environment. The spec's own Phase 0 gate (baseline SST in the container from one command, spec L308) also FAILs: it needs P0-08 + P0-11, and the flat placeholder mesh (GATE.md L37–41, D4) would invalidate the comparison anyway. This corroborates the [GATE.md](../GATE.md) frozen-RANS-only decision.

Reconciliation with automated scans: stub-scan flags [download_data.py:47,55](../evidence/stub-scan.txt:34) — consistent with P0-08 SKELETON (admitted offline stop, not hidden fakery). Import-smoke 47/56 OK with `tenacity`/`sympy`/`sklearn` failures is consistent with P0-02/P0-15 PRESENT_UNTESTED: the skeleton is real code never run in its declared environment. Pytest/ruff/mypy all exit 1 (absent), so no row earns VERIFIED.

## Pre-audit findings in scope

| ID | Verdict | Evidence |
|---|---|---|
| H3 (no `uv.lock`; pip folders) | CONFIRMED | `Test-Path uv.lock` = False live; [versions-env.json:87](../evidence/versions-env.json:87) `uv_lock_exists=false`; 7 pip dirs at root live: `pip-build-tracker-*` ×2, `pip-ephem-wheel-cache-*` ×2, `pip-install-*` ×2, `pip-target-*` ×1. S0.1 pass criteria (plan L191) unmet. |
| H5 (no `AGENTS.md`) | CONFIRMED | `Test-Path AGENTS.md` = False live. Only a planned file in [hygiene/REPORT.md:17](../hygiene/REPORT.md:17), never created. |
| H6 (plan L3 absolute spec link) | CONFIRMED | [plan:3](../../docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:3) links `/C:/Users/juanc/Desktop/FlowForge/v2%20Build%20spec.md`. Same defect in [README.md:2](../../README.md:2) (both links absolute) — breaks on the second machine. |
| C1 (`coder=muse-code`; plan `muse-code`/`wonder` vs documented `muse-spark-1.3`/`muse-spark-1.3-contributor`/`muse-wonder-1.0`) | CONFIRMED → DECISION_NEEDED (P0-18) | [budgets.yaml:5](../../configs/budgets.yaml:5) `coder: muse-code`; plan L52 `muse-code, wonder`, plan L5 `Wonder`; [client.py:24](../../flowforge/agents/runtime/client.py:24) prices `muse-code` + `wonder`. Neither `muse-code` nor bare `wonder` is a documented ID. Spec L149 already gives the fallback: Contributor tier, or Spark if declined. |
| C2 (tolerances not in `configs/`) | CONFIRMED | Live `configs/` = `budgets.yaml`, `cases.yaml`, `experiments/{baseline,sparse_baseline,swarm,swarm_no_redteam}.yaml` only — no tolerances file. Values scattered: [engine.py:11–12](../../flowforge/elegance/engine.py:11) 1%/3%, [test_identity.py:15](../../tests/integration/test_identity.py:15) `1e-6`, [test_oracle.py:17](../../tests/integration/test_oracle.py:17) `0.70`, [tensors.py:56](../../flowforge/physics/tensors.py:56) `1e-4`, [gates.py:13](../../flowforge/composer/gates.py:13) 16 bits, baseline `0.05` only in plan S1.3 text. Violates plan L84–86. |

Additional C-items found in this phase:

- **C4 (new): CI can lie.** [ci.yml:14,16,18,20](../../.github/workflows/ci.yml:14) `\|\|` fallbacks mean a broken uv setup silently degrades to pip/system tools, and there is no Docker/OpenFOAM job — green CI is compatible with a dead solver path (P0-13).
- **C5 (new): unpinned base image.** [openfoam.Dockerfile:1](../../docker/openfoam.Dockerfile:1) `FROM ...:latest` violates S0's own pinned-versions guardrail (plan L226) and leaves the ESI-version decision (D7) implicit in whatever `latest` is on build day.
- **C6 (new): manifest cannot cover locked cases.** [download_data.py:20–25](../../scripts/download_data.py:20) `CASES` omits `square_duct` and `nasa_wall_mounted_hump`, and the real path records no source URL/license (spec L103, L115) — provenance for the locked set is structurally unrecordable as written.

Structurally off (beyond findings): `data/raw`, `data/processed`, `library/*` are all `.gitkeep`-only while [project_status.md](../../project_status.md) labels the consumers of that data "Complete"; the two spec/plan gates for the same phase disagree (spec = solver run; plan S0 = versions+manifest+CI), which let the weaker gate be quoted as progress. `audit/round-2/` phase files from the static pass predate this round and disagree with live checks where the shell now works (e.g. H1 pip folders are in fact present and listed above).

## Signed account

Counts per status (18 rows): VERIFIED 0 · PRESENT_UNTESTED 5 (P0-02, P0-05, P0-06, P0-09, P0-15) · SKELETON 4 (P0-07, P0-08, P0-10, P0-13) · MISSING 3 (P0-03, P0-16, P0-17) · BLOCKED_BY_ENV 5 (P0-01, P0-04, P0-11, P0-12, P0-14) · DECISION_NEEDED 1 (P0-18). Phase gate: **FAIL** (manifest leg disproven; CI leg UNVERIFIABLE).

Top 5 gaps:

1. No dataset or manifest (P0-08/P0-16) — blocks S1 baseline, S2 oracle, and every downstream comparison.
2. No uv environment (P0-03/P0-04) — `uv.lock` missing, uv absent; no plan verification command can run as written.
3. No Docker/OpenFOAM probe (P0-10/P0-11) — image is a 4-line unpinned scaffold; spec Phase 0 gate unreachable.
4. Phase 0 configs are orphaned (P0-05/P0-06/P0-07) — budgets/cases/experiments are never parsed, so S0 "configuration done" claims have no behavioural effect.
5. Tolerances and model IDs unfrozen (P0-17/P0-18, C1/C2) — decisions S1/S2/S4 will silently inherit scattered constants and non-existent model IDs.

What I did not check: `data/locked/` contents (forbidden, never opened); `.env` values (only env-var names in [versions-env.json](../evidence/versions-env.json)); any live Meta/Kaggle/GitHub service; GitHub Actions run history; Docker behaviour on a machine that has it; whether `uv sync` would actually resolve the pinned set; UI, solver physics, and S1+ behaviour (other phases). The synthetic-fallback was not executed against the repo to avoid writing outside the three audit files; its code was read and CI wiring verified instead.

Confidence: high on all file-existence, content, and reachability claims (every cited file opened; listings re-run live this session). Medium on environment claims — they describe this sandbox, where uv/Docker are absent by construction. Zero on runtime behaviour: no S0 command has an observed passing run, which is exactly why VERIFIED is 0.

# Hygiene report (Step H) — BLOCKED: worktree isolation unavailable

Branch: `chore/pre-implementation-hygiene` — NOT created. Two spawn attempts
with `worktree_isolation: true` were rejected by the runtime:
`worktree_isolation_unavailable / workspace_git_probe_failed` (the runtime
could not confirm the workspace as a Git repository, consistent with the
`git dubious ownership` sandbox user mismatch observed in Step 0). Per the
guardrails, no hygiene edits were made on the main checkout, no branch was
created there, and nothing was committed or merged.

## Test exit codes (offline suite, this environment)

Command (before and after, via `subprocess.run(..., timeout=120)`):
`python -m pytest tests/unit tests/integration -q -p no:cacheprovider`

- Before exit code: 1 — `No module named pytest`
- After exit code: 1 — `No module named pytest` (no changes were applied,
  so the after run is the identical environment; recorded honestly, not
  as a hygiene result)

## Planned scope once unblocked (only CONFIRMED findings)

- `.gitignore`: add `pip-build-tracker-*/`, `pip-ephem-wheel-cache-*/`,
  `pip-install-*/`, `pip-target-*/`, `ui/node_modules/`, `ui/dist/`,
  `scratch/__pycache__/`, `runs/probe_s55/`; `git rm --cached` the tracked
  `ui/node_modules/` (4683 files) and `ui/dist/` (62 files).
- Regenerate tree into `docs/structure.txt`; remove `estructura.txt`
  (currently untracked, so this is a delete, not a `git rm`).
- New `AGENTS.md` with the project rules.
- `configs/budgets.yaml`: coder `muse-code` → `muse-spark-1.3` (C1).
- New `configs/tolerances.yaml` with C2 values verbatim, no code wiring.
- Plan line 3 absolute spec link → relative (H6).

## Skipped and why

- All edits above: skipped — the single write-capable hygiene child could
  not be spawned with worktree isolation, and the main checkout is
  write-frozen outside `audit/` by guardrail 1.
- H1 pip-folder deletion: untracked junk; see
  [cleanup.ps1](cleanup.ps1) for the user to review and run.
- To unblock: run this session where the workspace git probe passes
  (or fix the sandbox `safe.directory` ownership mismatch), then re-spawn
  Step H exactly as specified. Do not merge anything until approved.

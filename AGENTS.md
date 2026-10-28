# FlowForge — Agent Rules

## Authority

- `v2 Build spec.md` wins on methodology and research questions RP1–RP6.
- `docs/plans/2026-10-26-flowforge-v2-implementation-plan.md` wins on sequencing.
- If spec and plan conflict on methodology/RP1–RP6, follow the spec; on order of work, follow the plan.

## Work discipline

- Write only within the scope named in your task; verify with commands and report exit codes/output.
- Put probes and throwaway scripts in `scratch/`; never commit probe output as results.
- On Windows PowerShell, `timeout` is not a limit — always use Python `subprocess.run(..., timeout=120)` (or the task-specified timeout) for subprocesses.

## Data and evaluation guardrails

- Never read `data/locked/` directly. Locked evaluation only via `scripts/evaluate_locked.py`, logged, at most 3 evaluations.
- Label every result `frozen`, `short`, or `full` accurately; never present a `frozen` result as `full`.
- Tolerances are frozen in `configs/tolerances.yaml`; do not loosen them to make a check pass.
- Mock/synthetic results are bookkeeping only — never report them as real results.

## Dependencies and external services

- No unpinned dependencies.
- No installs without a security audit and explicit user confirmation.
- No Meta API credits / paid API use without approval.

## Verification

- Run the repo tests/probes that cover your change and report the exact commands and exit codes.
- Do not claim success you did not observe.

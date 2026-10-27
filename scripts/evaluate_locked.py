"""Locked milestone evaluation (S7.2). Max 3 runs total; each logs its reason."""

from __future__ import annotations

import argparse
from pathlib import Path

LOG = Path("runs/vault_access.log")
MAX_EVALS = 3


def count_prior() -> int:
    if not LOG.exists():
        return 0
    return sum(1 for line in LOG.read_text(encoding="utf-8").splitlines()
               if line.startswith("LOCKED_EVAL"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    prior = count_prior()
    if prior >= MAX_EVALS:
        raise SystemExit(f"Locked evaluation budget exhausted ({MAX_EVALS})")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"LOCKED_EVAL milestone={args.milestone} reason={args.reason}\n")
    print(f"Locked eval {prior + 1}/{MAX_EVALS} recorded. Scoring runs in evaluator.")


if __name__ == "__main__":
    main()

"""Locked milestone evaluation recorder (S7.2).

This script NEVER reads ``data/locked`` itself: no locked data exists
for it to read in this change, and scoring happens outside the swarm.
It only records candidate scores that were computed elsewhere and
supplied via ``--scores-file`` (a JSON file), appends an access-log
entry with the reason, and prints the recorded scores.

Usage (all of --milestone and --scores-file are required)::

    python scripts/evaluate_locked.py --milestone 1 \
        --scores-file scores.json --reason "champion check"

Without the required arguments it exits non-zero; a missing or
invalid ``--scores-file`` exits with code 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOG = Path("runs/vault_access.log")
MAX_EVALS = 3


def count_prior(log: Path = LOG) -> int:
    if not log.exists():
        return 0
    return sum(1 for line in log.read_text(encoding="utf-8").splitlines()
               if line.startswith("LOCKED_EVAL"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record locked-milestone scores computed elsewhere. "
                    "This script never reads data/locked itself.")
    parser.add_argument("--milestone", required=True, type=int, choices=(1, 2, 3),
                        help="milestone number (1, 2 or 3); required")
    parser.add_argument("--scores-file", required=True,
                        help="JSON file of candidate scores computed elsewhere; required")
    parser.add_argument("--reason", default="unspecified",
                        help="reason recorded in the access log")
    parser.add_argument("--log-file", default=str(LOG),
                        help="access log to append to (default: runs/vault_access.log)")
    args = parser.parse_args(argv)

    scores_path = Path(args.scores_file)
    if not scores_path.is_file():
        print(f"error: --scores-file not found: {scores_path}", file=sys.stderr)
        return 2
    try:
        scores = json.loads(scores_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: --scores-file is not valid JSON: {scores_path}: {exc}",
              file=sys.stderr)
        return 2
    if not isinstance(scores, (dict, list)):
        print("error: --scores-file must contain a JSON object or array of "
              f"candidate scores: {scores_path}", file=sys.stderr)
        return 2

    log = Path(args.log_file)
    prior = count_prior(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    recorded = json.dumps(scores, sort_keys=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"LOCKED_EVAL milestone={args.milestone} reason={args.reason} "
                 f"scores_file={scores_path} scores={recorded}\n")
    print("NOTE: this script does not read data/locked; it records scores "
          "computed elsewhere and supplied via --scores-file.")
    print(f"Locked eval {prior + 1}/{MAX_EVALS} recorded for milestone "
          f"{args.milestone}.")
    print(f"Recorded scores: {recorded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""3-arm x 3-seed experiment runner (S7.1). Same budget per arm.

Arms: full swarm, no-red-team ablation, sparse baseline. Seeds 42/43/44.
Mock mode exercises bookkeeping without API/Docker; real mode needs S1-S6
verified first. Reports mean and spread, wins and losses alike.
"""

from __future__ import annotations

import argparse
import statistics

ARMS = ("swarm", "swarm_no_redteam", "sparse_baseline")
SEEDS = (42, 43, 44)


def summarize(results: list[float]) -> dict:
    assert len(results) == 3, "science protocol requires exactly 3 seeds"
    return {"mean": statistics.mean(results),
            "stdev": statistics.stdev(results) if len(results) > 1 else 0.0,
            "runs": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    for arm in ARMS:
        scores = [float((seed % 7) + len(arm)) for seed in SEEDS] if args.mock else []
        if scores:
            print(arm, summarize(scores))
        else:
            print(f"{arm}: needs verified S1-S6; run with --mock for bookkeeping")


if __name__ == "__main__":
    main()

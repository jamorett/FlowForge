"""Locked milestone evaluation (S7.2 / Phase 6.2).

Evaluates a champion candidate expression against held-out locked datasets:
  - square_duct (tests secondary flows driven by T2, T3)
  - nasa_wall_mounted_hump (tests APG separation and reattachment)

Protocol:
  - At most 3 milestone evaluations permitted per experimental run.
  - Each evaluation reads the champion expression, compiles it via the DSL
    evaluator, and scores it against locked Zarr store targets.
  - Results are recorded in runs/vault_access.log with a timestamp.
  - This script reads data/locked/ ONLY through the Zarr store API.

Usage::
    python scripts/evaluate_locked.py --milestone 1 \\
        --champion "0.3*T1 + 0.1*I1*T3" --reason "end-of-round champion"

    python scripts/evaluate_locked.py --milestone 2 \\
        --scores-file scores.json --reason "external evaluation"
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG = Path("runs/vault_access.log")
MAX_EVALS = 3
LOCKED_CASES = ("square_duct", "nasa_wall_mounted_hump")


def count_prior(log: Path = LOG) -> int:
    if not log.exists():
        return 0
    return sum(1 for line in log.read_text(encoding="utf-8").splitlines()
               if line.startswith("LOCKED_EVAL"))


def _record(log: Path, milestone: int, reason: str, scores: dict, mode: str) -> None:
    """Append a locked evaluation entry to the access log."""
    log.parent.mkdir(parents=True, exist_ok=True)
    recorded = json.dumps(scores, sort_keys=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"LOCKED_EVAL milestone={milestone} reason={reason} "
                 f"mode={mode} timestamp={ts} scores={recorded}\n")


def evaluate_champion_on_locked(champion_expr: str,
                                locked_root: Path = Path("data/locked"),
                                ) -> dict:
    """Evaluate a champion expression against all locked Zarr stores.

    Returns per-case a-priori MSE and aggregate metrics.
    Raises FileNotFoundError if no locked cases exist.
    """
    import numpy as np

    from flowforge.data.zarr_store import read_case
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.ladder.ladder import apriori_mse

    results: dict[str, float] = {}
    available = []
    for case_name in LOCKED_CASES:
        case_dir = locked_root / case_name
        if not case_dir.exists():
            continue
        available.append(case_name)
        data = read_case(case_dir)

        inv = {k.split("/", 1)[1]: v for k, v in data.items()
               if k.startswith("invariants/")}
        basis = {k.split("/", 1)[1]: v for k, v in data.items()
                 if k.startswith("tensor_basis/")}
        target = data["targets/a_delta"]

        # Evaluate candidate
        pred = candidate_anisotropy(champion_expr, inv, basis)
        mse = apriori_mse(pred, target)

        # Also compute baseline (zero correction) for error ratio
        baseline_pred = np.zeros_like(target)
        baseline_mse = apriori_mse(baseline_pred, target)

        ratio = mse / max(baseline_mse, 1e-12)
        results[case_name] = {
            "mse": float(mse),
            "baseline_mse": float(baseline_mse),
            "error_ratio": float(ratio),
            "n_cells": int(target.shape[0]),
        }

    if not available:
        raise FileNotFoundError(
            f"No locked cases found in {locked_root}. "
            f"Expected: {LOCKED_CASES}"
        )

    # Aggregate: worst-case error ratio across all locked cases
    worst_ratio = max(r["error_ratio"] for r in results.values())
    mean_mse = sum(r["mse"] for r in results.values()) / len(results)

    return {
        "champion": champion_expr,
        "cases": results,
        "worst_error_ratio": worst_ratio,
        "mean_mse": mean_mse,
        "n_cases": len(available),
        "available_cases": available,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Locked milestone evaluation: score a champion on held-out data.")
    parser.add_argument("--milestone", required=True, type=int, choices=(1, 2, 3),
                        help="milestone number (1, 2 or 3); required")
    parser.add_argument("--champion", default=None,
                        help="DSL expression to evaluate (direct mode)")
    parser.add_argument("--scores-file", default=None,
                        help="JSON file of pre-computed scores (recorder mode)")
    parser.add_argument("--reason", default="unspecified",
                        help="reason recorded in the access log")
    parser.add_argument("--log-file", default=str(LOG),
                        help="access log to append to (default: runs/vault_access.log)")
    parser.add_argument("--locked-root", default="data/locked",
                        help="root directory for locked datasets")
    args = parser.parse_args(argv)

    log = Path(args.log_file)
    prior = count_prior(log)
    if prior >= MAX_EVALS:
        print(f"ERROR: {prior}/{MAX_EVALS} locked evaluations already used. "
              "Protocol forbids more.", file=sys.stderr)
        return 1

    if args.champion:
        # Direct mode: evaluate the champion expression against locked stores
        try:
            results = evaluate_champion_on_locked(
                args.champion, locked_root=Path(args.locked_root))
        except FileNotFoundError as exc:
            print(f"WARNING: {exc}", file=sys.stderr)
            print("No locked datasets available. Recording placeholder.", file=sys.stderr)
            results = {"champion": args.champion, "cases": {},
                       "status": "no_locked_data"}
        except Exception as exc:
            print(f"ERROR: Evaluation failed: {exc}", file=sys.stderr)
            results = {"champion": args.champion, "error": str(exc),
                       "status": "failed"}

        _record(log, args.milestone, args.reason, results, mode="direct")
        print(f"Locked eval {prior + 1}/{MAX_EVALS} recorded for milestone "
              f"{args.milestone}.")
        print(f"Champion: {args.champion}")
        if "cases" in results and results["cases"]:
            for case, metrics in results["cases"].items():
                print(f"  {case}: MSE={metrics['mse']:.6f}, "
                      f"ratio={metrics['error_ratio']:.4f}")
        else:
            print(f"  Status: {results.get('status', 'unknown')}")
        return 0

    elif args.scores_file:
        # Recorder mode: record externally computed scores
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
            print("error: --scores-file must contain a JSON object or array",
                  file=sys.stderr)
            return 2

        _record(log, args.milestone, args.reason, scores, mode="recorded")
        print("NOTE: this script does not read data/locked; it records scores "
              "computed elsewhere and supplied via --scores-file.")
        print(f"Locked eval {prior + 1}/{MAX_EVALS} recorded for milestone "
              f"{args.milestone}.")
        print(f"Recorded scores: {json.dumps(scores, sort_keys=True)}")
        return 0

    else:
        print("error: provide --champion (direct) or --scores-file (recorder)",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

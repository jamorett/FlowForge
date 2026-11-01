"""3-arm x 3-seed experiment runner (S7.1). Same budget per arm.

Arms: full swarm, no-red-team ablation, sparse baseline. Seeds 42/43/44.
Mock mode exercises bookkeeping without API/Docker; real mode needs S1-S6
verified first. Reports mean and spread, wins and losses alike.
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import sys
from pathlib import Path

# Ensure project root is importable when invoked as `python scripts/run_arms.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ARMS = ("swarm", "swarm_no_redteam", "sparse_baseline")
SEEDS = (42, 43, 44)

SWARM_ARMS = ("swarm", "swarm_no_redteam")
FROZEN_MODE = "frozen"
FROZEN_METRIC = "worst_validation_ratio (lower is better)"


def summarize(results: list[float]) -> dict:
    assert len(results) == 3, "science protocol requires exactly 3 seeds"
    return {"mean": statistics.mean(results),
            "stdev": statistics.stdev(results) if len(results) > 1 else 0.0,
            "min": min(results),
            "max": max(results),
            "runs": results}


def mann_whitney_u(a: list[float], b: list[float]) -> float:
    """Mann-Whitney U statistic (two-sample, non-parametric).

    For n=3, U in [0, 9]. U=9 means every sample of ``a`` beats every
    sample of ``b``. Used for the RP1/RP2 arm comparisons.
    """
    u = 0.0
    for ai in a:
        for bi in b:
            if ai < bi:
                u += 1.0
            elif ai == bi:
                u += 0.5
    return float(u)


def parse_seed_list(text: str) -> list[int]:
    """Parse a comma-separated seed string into ints."""
    parts = [chunk.strip() for chunk in str(text).split(",")]
    seeds: list[int] = []
    for chunk in parts:
        if chunk == "":
            continue
        seeds.append(int(chunk))
    return seeds


def default_out_path() -> str:
    """Return the default timestamped arms JSON path."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"runs/arms/arms-{stamp}.json"


def summarize_or_none(metrics: list[float]) -> dict | None:
    """Summarize exactly 3 metrics, else None."""
    if len(metrics) != 3:
        return None
    return summarize(metrics)


def make_seed_row(seed: int, metric: float | None, expression: str | None,
                  session: str, cost: float, dry_run: bool) -> dict:
    """Build one per-seed row with alias keys for shape stability."""
    cost_value = float(cost)
    return {
        "seed": int(seed),
        "metric": metric,
        "champion": expression,
        "expression": expression,
        "champion_expression": expression,
        "session": str(session),
        "cost": cost_value,
        "cost_usd": cost_value,
        "dollars_spent": cost_value,
        "dry_run": bool(dry_run),
    }


def round_metric(result: dict) -> float | None:
    """Return a round's champion ratio, or None when unusable."""
    if not isinstance(result, dict):
        return None
    if result.get("status") == "error":
        return None
    champion = result.get("champion")
    if not isinstance(champion, dict):
        return None
    value = champion.get("worst_validation_ratio")
    if value is None:
        return None
    try:
        metric = float(value)
    except (TypeError, ValueError):
        return None
    return metric


def round_expression(result: dict) -> str | None:
    """Return the champion expression, or None when missing."""
    if not isinstance(result, dict):
        return None
    champion = result.get("champion")
    if not isinstance(champion, dict):
        return None
    expression = champion.get("expression")
    return str(expression) if isinstance(expression, str) else None


def round_cost(result: dict) -> float:
    """Return dollars_spent for a round result (0.0 when missing)."""
    if not isinstance(result, dict):
        return 0.0
    try:
        return float(result.get("dollars_spent", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def baseline_metric(baseline: dict) -> float | None:
    """Return worst_validation_ratio from a sparse baseline result."""
    if not isinstance(baseline, dict):
        return None
    value = baseline.get("worst_validation_ratio")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def baseline_expression(baseline: dict) -> str | None:
    """Return the expression from a sparse baseline result."""
    if not isinstance(baseline, dict):
        return None
    expression = baseline.get("expression")
    return str(expression) if isinstance(expression, str) else None


def collect_swarm_arm(arm: str, seeds: list[int], rounds: int, groups: int,
                      budget_usd: float, dry_run: bool,
                      spent: list[float], incomplete: list[bool]) -> dict:
    """Run one swarm arm across seeds, tracking shared spend/budget."""
    from flowforge.orchestrator import round as round_module

    want_redteam = arm != "swarm_no_redteam"
    rows: list[dict] = []
    for seed in seeds:
        session = f"arms-{arm}-s{seed}"
        seed_cost = 0.0
        last_result: dict | None = None
        # A round whose candidates are all rejected must not erase an earlier
        # verified champion: the session keeps its best (lowest) ratio so far.
        best_metric: float | None = None
        best_expression: str | None = None
        completed = 0
        for round_no in range(1, int(rounds) + 1):
            if spent[0] > float(budget_usd):
                incomplete[0] = True
                break
            result = round_module.run_round(
                round_no, mock=False, groups=groups,
                session=session, redteam=want_redteam)
            last_result = result
            completed += 1
            metric_now = round_metric(result)
            if metric_now is not None and (best_metric is None or metric_now < best_metric):
                best_metric, best_expression = metric_now, round_expression(result)
            cost = round_cost(result)
            spent[0] += cost
            seed_cost += cost
        if last_result is None:
            metric: float | None = None
            expression: str | None = None
            if spent[0] > float(budget_usd):
                incomplete[0] = True
        else:
            metric, expression = best_metric, best_expression
            if completed < int(rounds):
                incomplete[0] = True
        rows.append(make_seed_row(seed, metric, expression, session, seed_cost, dry_run))
    metrics = [row["metric"] for row in rows if row["metric"] is not None]
    return {"seeds": rows, "summary": summarize_or_none(metrics), "dry_run": bool(dry_run)}


def collect_sparse_arm(seeds: list[int], dry_run: bool) -> dict:
    """Evaluate the sparse baseline once per seed."""
    from flowforge.baselines import sparse as sparse_module

    rows: list[dict] = []
    for seed in seeds:
        baseline = sparse_module.evaluate_sparse_baseline(seed=seed)
        metric = baseline_metric(baseline)
        expression = baseline_expression(baseline)
        session = f"arms-sparse_baseline-s{seed}"
        rows.append(make_seed_row(seed, metric, expression, session, 0.0, dry_run))
    metrics = [row["metric"] for row in rows if row["metric"] is not None]
    return {"seeds": rows, "summary": summarize_or_none(metrics), "dry_run": bool(dry_run)}


def print_table(arms_output: dict) -> None:
    """Print a short per-arm summary table to stdout."""
    for arm in ARMS:
        info = arms_output.get(arm, {})
        summary = info.get("summary")
        rows = info.get("seeds", [])
        metrics = [row.get("metric") for row in rows]
        if isinstance(summary, dict):
            print(f"{arm}: mean={summary['mean']:.4f} stdev={summary['stdev']:.4f} metrics={metrics}")
        else:
            print(f"{arm}: summary=None metrics={metrics}")


def main(argv: list[str] | None = None) -> dict | None:
    """Run the 3-arm x 3-seed table (mock bookkeeping or real/frozen mode)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seeds", default="42,43,44")
    parser.add_argument("--groups", type=int, default=2)
    parser.add_argument("--budget-usd", type=float, default=10.0, dest="budget_usd")
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args(argv)
    if args.mock:
        for arm in ARMS:
            scores = [float((seed % 7) + len(arm)) for seed in SEEDS] if args.mock else []
            if scores:
                print(arm, summarize(scores))
            else:
                print(f"{arm}: needs verified S1-S6; run with --mock for bookkeeping")
        return None
    try:
        seeds = parse_seed_list(args.seeds)
    except ValueError:
        parser.error("--seeds must be comma-separated ints, e.g. 42,43,44")
    if len(seeds) != 3:
        parser.error("--seeds must contain exactly 3 seeds")
    rounds = int(args.rounds)
    groups = int(args.groups)
    budget_usd = float(args.budget_usd)
    if rounds < 1:
        parser.error("--rounds must be >= 1")
    if groups < 1:
        parser.error("--groups must be >= 1")
    out_path = str(args.out) if args.out is not None else default_out_path()
    dry_run = bool(args.dry_run)

    from flowforge.agents import dispatcher as dispatcher_module
    from flowforge.agents.dispatcher import dispatch_role_mock

    original_dispatch = dispatcher_module.dispatch_role

    def dry_dispatch(role, runtime=None, context=None, **kwargs):
        active = context
        if active is None and isinstance(runtime, dict):
            active = runtime
        if active is None:
            active = {}
        return dispatch_role_mock(role, active)

    if dry_run:
        dispatcher_module.dispatch_role = dry_dispatch  # type: ignore[assignment]
    try:
        spent = [0.0]
        incomplete = [False]
        arms_output: dict = {}
        for arm in SWARM_ARMS:
            arms_output[arm] = collect_swarm_arm(
                arm, seeds, rounds, groups, budget_usd, dry_run, spent, incomplete)
        arms_output["sparse_baseline"] = collect_sparse_arm(seeds, dry_run)
        output = {
            "mode": FROZEN_MODE,
            "metric": FROZEN_METRIC,
            "rounds": rounds,
            "seeds": list(seeds),
            "groups": groups,
            "budget_usd": float(budget_usd),
            "spent_usd": float(spent[0]),
            "incomplete": bool(incomplete[0]),
            "dry_run": bool(dry_run),
            "arms": arms_output,
        }
    finally:
        if dry_run:
            dispatcher_module.dispatch_role = original_dispatch  # type: ignore[assignment]
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print_table(arms_output)
    return output


if __name__ == "__main__":
    main()

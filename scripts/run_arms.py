"""3-arm x 3-seed experiment runner (S7.1). Same budget per arm.

Arms: full swarm, no-red-team ablation, sparse baseline. Seeds 42/43/44.
Mock mode exercises bookkeeping without API/Docker; real mode needs S1-S6
verified first. Reports mean and spread, wins and losses alike.
"""

from __future__ import annotations

import argparse
import datetime
import itertools
import json
import math
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
COMPARISON_METRIC = "worst_validation_ratio"
COMPARISON_PAIRS = (("swarm", "swarm_no_redteam"), ("swarm", "sparse_baseline"))


def summarize(results: list[float]) -> dict:
    assert len(results) >= 3, "science protocol requires at least 3 seeds"
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


def mann_whitney_exact_p(a: list[float], b: list[float]) -> float:
    """Exact one-sided p-value for H1 that ``a`` tends to be lower than ``b``.

    Lower ``worst_validation_ratio`` is better, so large U supports H1.
    Enumerates every split of the pooled values into groups of ``len(a)``
    and ``len(b)`` and counts splits whose U (as ``mann_whitney_u``
    computes it) is >= the observed U.
    """
    observed = mann_whitney_u(a, b)
    pooled = list(a) + list(b)
    size_a = len(a)
    total = 0
    extreme = 0
    for combo in itertools.combinations(range(len(pooled)), size_a):
        picked = set(combo)
        group_a = [pooled[idx] for idx in combo]
        group_b = [pooled[idx] for idx in range(len(pooled)) if idx not in picked]
        stat = mann_whitney_u(group_a, group_b)
        total += 1
        if stat >= observed:
            extreme += 1
    if total == 0:
        return 1.0
    return float(extreme) / float(total)


def comparison_p_min(n1: int, n2: int) -> float:
    """Return the smallest achievable one-sided p for sizes n1 and n2."""
    return 1.0 / float(math.comb(n1 + n2, n1))


# A seed whose planned rounds all ran without an error but never produced a
# champion delivers no correction: it scores as plain SST (ratio 1.0) instead
# of being dropped, so failures count against the arm (decisions.md 2026-11-01).
NO_CHAMPION_RATIO = 1.0


def seed_metric_or_no_champion(metric: float | None, round_results: list[tuple[int, dict]],
                               rounds: int) -> tuple[float | None, bool]:
    """Return (metric, no_champion), scoring a champion-less seed as SST.

    Only a seed that ran every planned round with no errored round is
    scored ``NO_CHAMPION_RATIO``; budget-cut or errored seeds stay None
    (missing, so the arm is reported incomplete).
    """
    if metric is not None:
        return metric, False
    ran_all = len(round_results) == int(rounds) and int(rounds) > 0
    errored = any(isinstance(r, dict) and r.get("status") == "error" for _, r in round_results)
    if ran_all and not errored:
        return NO_CHAMPION_RATIO, True
    return None, False


def arm_metrics(arms_output: dict, arm: str) -> list[float] | None:
    """Return the complete metric list for an arm, else None."""
    info = arms_output.get(arm)
    if not isinstance(info, dict):
        return None
    rows = info.get("seeds")
    if not isinstance(rows, list) or not rows:
        return None
    metrics: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        value = row.get("metric")
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(number):
            return None
        metrics.append(number)
    return metrics


def unavailable_comparison(first: str, second: str, reason: str) -> dict:
    """Return an unavailable comparison entry for two arms."""
    return {
        "available": False,
        "reason": reason,
        "metric": COMPARISON_METRIC,
        "arms": [first, second],
    }


def build_comparison(first: str, second: str, arms_output: dict) -> dict:
    """Build one RP comparison dict for two arms.

    When both arms have complete metrics the entry reports ``u``,
    ``p_one_sided``, ``p_min``, per-arm ``n`` and ``metric``;
    otherwise it reports ``available`` False with a reason.
    """
    first_metrics = arm_metrics(arms_output, first)
    if first_metrics is None:
        return unavailable_comparison(first, second, f"{first} metrics incomplete")
    second_metrics = arm_metrics(arms_output, second)
    if second_metrics is None:
        return unavailable_comparison(first, second, f"{second} metrics incomplete")
    stat = mann_whitney_u(first_metrics, second_metrics)
    p_value = mann_whitney_exact_p(first_metrics, second_metrics)
    p_floor = comparison_p_min(len(first_metrics), len(second_metrics))
    counts = {first: len(first_metrics), second: len(second_metrics)}
    return {
        "available": True,
        "metric": COMPARISON_METRIC,
        "arms": [first, second],
        "u": float(stat),
        "p_one_sided": float(p_value),
        "p_min": float(p_floor),
        "n1": len(first_metrics),
        "n2": len(second_metrics),
        "n": dict(counts),
    }


def build_comparisons(arms_output: dict) -> dict:
    """Build the RP1/RP2 comparisons dict for the arms output."""
    comparisons: dict = {}
    labels = {
        ("swarm", "swarm_no_redteam"): "RP1",
        ("swarm", "sparse_baseline"): "RP2",
    }
    for pair in COMPARISON_PAIRS:
        first, second = pair
        key = f"{first}_vs_{second}"
        entry = build_comparison(first, second, arms_output)
        label = labels.get(pair)
        if label is not None:
            entry["label"] = label
        comparisons[key] = entry
    return comparisons


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


def summarize_or_none(metrics: list[float], expected: int = 3) -> dict | None:
    """Summarize when every one of ``expected`` (>= 3) seeds has a metric, else None."""
    if len(metrics) != int(expected) or len(metrics) < 3:
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


def parse_train_number(value: object) -> float | None:
    """Coerce a train-side value to float, else None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def champion_train_score(champion: dict) -> float | None:
    """Return the train-side selection score for a champion.

    Uses only train/attack data, never validation numbers. Prefers
    ``train_ratio`` / ``train.ratio``, then other numeric ``train``
    payloads, then the mean of ``attack_ratios``.
    """
    if not isinstance(champion, dict):
        return None
    score = parse_train_number(champion.get("train_ratio"))
    if score is not None:
        return score
    train = champion.get("train")
    if isinstance(train, dict):
        for key in ("ratio", "train_ratio", "mse", "mse_after", "score"):
            score = parse_train_number(train.get(key))
            if score is not None:
                return score
    elif train is not None:
        score = parse_train_number(train)
        if score is not None:
            return score
    for key in ("train_mse", "train_score"):
        score = parse_train_number(champion.get(key))
        if score is not None:
            return score
    attack = champion.get("attack_ratios")
    if isinstance(attack, dict) and attack:
        values: list[float] = []
        for value in attack.values():
            parsed = parse_train_number(value)
            if parsed is not None:
                values.append(parsed)
        if values:
            return sum(values) / len(values)
    return parse_train_number(champion.get("attack_ratio"))


def round_train_score(result: dict) -> float | None:
    """Return the train-side score for a round result, or None."""
    if not isinstance(result, dict):
        return None
    if result.get("status") == "error":
        return None
    champion = result.get("champion")
    if not isinstance(champion, dict):
        return None
    return champion_train_score(champion)


def select_seed_champion(
    round_results: list[tuple[int, dict]],
) -> tuple[float | None, str | None, int | None, bool]:
    """Pick the seed champion from collected round results.

    Ranking is train-side first (``round_train_score``: train ratio, then
    mean attack ratio). The validation ratio only breaks ties, and only
    decides when no round logged train-side data at all (legacy rounds);
    every live champion carries a train score, so in practice selection
    never reads validation. The returned metric is always the champion
    ``worst_validation_ratio``. ``fallback`` is True when the last round
    had no usable champion.
    """
    if not round_results:
        return (None, None, None, False)
    _, last_result = round_results[-1]
    fallback = round_metric(last_result) is None
    ranked: list[tuple[int, float, float, float, int, str | None]] = []
    for round_no, result in round_results:
        metric = round_metric(result)
        if metric is None:
            continue
        train = round_train_score(result)
        ranked.append((0 if train is not None else 1,
                       train if train is not None else metric,
                       metric, int(round_no), round_expression(result)))
    if not ranked:
        return (None, None, None, False)
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    _, _, metric, best_round, expression = ranked[0]
    return (metric, expression, best_round, fallback)


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
        round_results: list[tuple[int, dict]] = []
        completed = 0
        for round_no in range(1, int(rounds) + 1):
            if spent[0] > float(budget_usd):
                incomplete[0] = True
                break
            result = round_module.run_round(
                round_no, mock=False, groups=groups,
                session=session, redteam=want_redteam)
            round_results.append((round_no, result))
            completed += 1
            cost = round_cost(result)
            spent[0] += cost
            seed_cost += cost
        if not round_results:
            metric: float | None = None
            expression: str | None = None
            champion_round: int | None = None
            fallback = False
            if spent[0] > float(budget_usd):
                incomplete[0] = True
        else:
            metric, expression, champion_round, fallback = select_seed_champion(round_results)
            if completed < int(rounds):
                incomplete[0] = True
        metric, no_champion = seed_metric_or_no_champion(metric, round_results, rounds)
        row = make_seed_row(seed, metric, expression, session, seed_cost, dry_run)
        row["champion_round"] = champion_round
        row["fallback"] = bool(fallback)
        row["no_champion"] = bool(no_champion)
        rows.append(row)
    metrics = [row["metric"] for row in rows if row["metric"] is not None]
    complete = len(metrics) == len(rows) and len(rows) > 0
    return {"seeds": rows, "summary": summarize_or_none(metrics, len(rows)), "dry_run": bool(dry_run), "complete": bool(complete)}


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
    return {"seeds": rows, "summary": summarize_or_none(metrics, len(rows)), "dry_run": bool(dry_run)}


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
    if len(seeds) < 3 or len(set(seeds)) != len(seeds):
        parser.error("--seeds must contain at least 3 distinct seeds")
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
        comparisons = build_comparisons(arms_output)
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
            "comparisons": comparisons,
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

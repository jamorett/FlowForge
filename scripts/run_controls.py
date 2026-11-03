"""Exploratory proposer controls for the decision run (decisions.md 2026-11-02).

Same live round as the swarm arm (fitter, ladder, realizability gate, red-team
screen, champion selection, validation reporting); only the proposer changes:

- ``single_llm``: the Theorist prompt, model and settings with no Board
  mechanisms, no library findings and no session history; Board, Coder,
  Analyst, Skeptic and Composer are replaced by their fixed mock outputs
  (none of them reaches the champion except through history, which is cut).
- ``random_grammar``: no proposer LLM; random expressions from the DSL grammar
  (g(I) * T_k terms), seeded per seed and round.
- ``swarm_sam_rt110``: the full swarm, with SAM 3.1 error regions for the
  Analyst and the red-team break ratio raised to 1.10; its breaks go to
  ``runs/arms/explore-sam_rt110-attacks`` instead of the permanent library.

The red-team role stays live in all, as in the swarm arm. Output mirrors
``run_arms.py``, with comparisons against the decision-run arms.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import run_arms  # noqa: E402

STUBBED_ROLES = ("board", "coder", "analyst", "skeptic", "composer")
CONTROLS = ("single_llm", "random_grammar", "swarm_sam_rt110")
RT110_BREAK_RATIO = 1.10
RT110_ATTACKS_DIR = Path("runs") / "arms" / "explore-sam_rt110-attacks"


def random_expression(rng: random.Random) -> str:
    """One random candidate: 1-3 terms g(I) * T_k on distinct tensors."""
    def coef() -> str:
        value = 0.0
        while abs(value) < 0.005:
            value = round(rng.uniform(-0.1, 0.1), 3)
        return f"({value})" if value < 0 else f"{value}"

    def denom() -> str:
        return f"{round(rng.uniform(0.05, 1.0), 3)}"

    forms = (
        lambda: coef(),
        lambda: f"{coef()} * I1",
        lambda: f"{coef()} * I2",
        lambda: f"{coef()} * I1 * I2",
        lambda: f"{coef()} * tanh(I1)",
        lambda: f"{coef()} * tanh(I2)",
        lambda: f"div({coef()}, {denom()} + I1)",
        lambda: f"div({coef()}, {denom()} + I2)",
        lambda: f"{coef()} * exp(-I1)",
    )
    from flowforge.dsl.parser import validate_candidate

    while True:  # resample until it passes the parser (e.g. the 25-node cap)
        tensors = rng.sample(["T1", "T2", "T3"], rng.randint(1, 3))
        text = " + ".join(f"({rng.choice(forms)()}) * {t}" for t in tensors)
        try:
            validate_candidate(text)
        except ValueError:
            continue
        return text


def make_dispatch(control: str, original, mock, schemas, seed: int, state: dict):
    """Wrap ``dispatch_role`` for one control arm and seed."""
    def dispatch(role, runtime, context=None, *args, **kwargs):
        if role in STUBBED_ROLES:
            return mock(role)
        if role == "theorist":
            if control == "random_grammar":
                state["calls"] += 1
                rng = random.Random(f"{seed}-{state['calls']}")
                return schemas["theorist"].model_validate({
                    "risk_audit": "random_grammar control: no LLM, seeded random DSL expressions",
                    "expressions": [random_expression(rng) for _ in range(3)],
                    "mechanisms": ["random"],
                })
            context = dict(context or {})
            context.update({"mechanisms": [], "group_history": [], "previous_results": {}})
        return original(role, runtime, context, *args, **kwargs)
    return dispatch


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", choices=CONTROLS, required=True)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--groups", type=int, default=2)
    parser.add_argument("--seeds", default="42,43,44,45,46")
    parser.add_argument("--budget-usd", type=float, default=6.0, dest="budget_usd")
    parser.add_argument("--reference", default="runs/arms/decision-2026-11-02.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    seeds = run_arms.parse_seed_list(args.seeds)

    from flowforge.agents import dispatcher as dispatcher_module
    from flowforge.agents.dispatcher import ROLE_SCHEMAS, dispatch_role_mock

    from flowforge.orchestrator import round as round_module

    original = dispatcher_module.dispatch_role
    original_ratio, original_attacks = round_module.REDTEAM_BREAK_RATIO, round_module.ATTACKS_DIR
    spent, incomplete = [0.0], [False]
    rows: list[dict] = []
    try:
        if args.control == "swarm_sam_rt110":
            run_arms.SAM[0] = True
            round_module.REDTEAM_BREAK_RATIO = RT110_BREAK_RATIO
            round_module.ATTACKS_DIR = RT110_ATTACKS_DIR
        for seed in seeds:
            if args.control != "swarm_sam_rt110":
                state = {"calls": 0}
                dispatcher_module.dispatch_role = make_dispatch(
                    args.control, original, dispatch_role_mock, ROLE_SCHEMAS, seed, state)
            arm = run_arms.collect_swarm_arm(
                args.control, [seed], args.rounds, args.groups,
                args.budget_usd, False, spent, incomplete)
            rows.extend(arm["seeds"])
    finally:
        dispatcher_module.dispatch_role = original
        round_module.REDTEAM_BREAK_RATIO, round_module.ATTACKS_DIR = original_ratio, original_attacks
        run_arms.SAM[0] = False

    metrics = [row["metric"] for row in rows if row["metric"] is not None]
    arms_output = {args.control: {"seeds": rows, "summary": run_arms.summarize_or_none(metrics, len(rows))}}
    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    for name, info in reference["arms"].items():
        arms_output[name] = info
    comparisons = {
        f"{args.control}_vs_{other}": run_arms.build_comparison(args.control, other, arms_output)
        for other in ("swarm", "swarm_no_redteam", "sparse_baseline")
    }
    output = {
        "label": "exploratory", "mode": "frozen", "control": args.control,
        "rounds": args.rounds, "groups": args.groups, "seeds": seeds,
        "spent_usd": spent[0], "incomplete": incomplete[0],
        "reference": args.reference, "arms": {args.control: arms_output[args.control]},
        "comparisons": comparisons,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    summary = arms_output[args.control]["summary"]
    print(f"{args.control}: summary={summary and {k: round(summary[k], 4) for k in ('mean', 'stdev')}} "
          f"metrics={[r['metric'] for r in rows]} spent=${spent[0]:.2f}")
    return output


if __name__ == "__main__":
    main()

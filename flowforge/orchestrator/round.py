"""Unattended round loop (S5.4).

Board -> Theorist -> Coder -> Rungs -> Analyst/Skeptic -> RedTeam -> Composer.
Deterministic scoring only (flowforge.ladder). Agents never self-grade.
Mock mode (--mock-llm) runs rungs 0-3 on synthetic fields without API
credits or Docker, so CI exercises the real ladder code path. The short
rung-2 evaluator is the first-points a priori error; production swaps in
the capped coarse-solver evaluator behind the same callable.
"""

from __future__ import annotations

import argparse

import numpy as np

MOCK_CANDIDATES = ("0", "I1", "tanh(I1)", "I1 + I2")


def synthetic_fields(n: int = 8, seed: int = 42):
    from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis

    rng = np.random.default_rng(seed)
    grad = rng.standard_normal((n, 3, 3))
    omega = np.full(n, 2.0)
    s, w = normalized_tensors(grad, omega)
    inv = invariants(s, w)
    basis = tensor_basis(s, w)
    target = 0.5 * basis["T1"]  # known ground truth: g = 0.5
    return inv, basis, target


def run_round(round_no: int, mock: bool = False,
              candidates: tuple[str, ...] = MOCK_CANDIDATES) -> dict:
    from flowforge.dsl.parser import complexity, validate_candidate
    from flowforge.elegance.engine import description_length, pick_champion
    from flowforge.ladder.ladder import apriori_mse, run_ladder

    inv, basis, target = synthetic_fields()

    def short_eval(expr: str) -> float:
        from flowforge.dsl.evaluate import candidate_anisotropy

        k = max(1, len(target) // 2)
        sub_inv = {name: arr[:k] for name, arr in inv.items()}
        sub_basis = {name: arr[:k] for name, arr in basis.items()}
        return apriori_mse(candidate_anisotropy(expr, sub_inv, sub_basis), target[:k])

    ladder = run_ladder(list(candidates), inv, basis, target, short_eval=short_eval)
    survivors = ladder["rung1"]
    final = ladder["rung3"]
    champion_pool = final if final else []
    champion = None
    if champion_pool:
        enriched = []
        for s in champion_pool:
            expr = validate_candidate(s["expression"])
            enriched.append({
                "id": s["expression"], "worst_error": s["score"],
                "dl": description_length(complexity(expr), []),
            })
        best = pick_champion(enriched)
        champion = {"expression": best["id"], "dl": best["dl"],
                    "worst_error": best["worst_error"]}
    return {
        "round": round_no,
        "mock": mock,
        "proposed": len(candidates),
        "survivors_rung1": survivors,
        "survivors_rung2": ladder["rung2"],
        "final_rung3": final,
        "champion": champion,
        "status": "ok" if final else "all_rejected",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--round", type=int, default=1)
    args = parser.parse_args()
    print(run_round(args.round, mock=args.mock_llm))


if __name__ == "__main__":
    main()

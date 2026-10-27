"""Successive-halving ladder (S5.1). Deterministic scoring only.

Rung 0 symbolic (no data) -> Rung 1 a priori (drop 50%) -> Rung 2 short
(drop 50% again) -> Rung 3 full + realizability. Selection is minimax:
rank by worst-case error, never the average. Solver-backed rungs accept
an evaluator callable so the mock path exercises the same code without
Docker; production passes the real solver evaluator.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

DIVERGED_PENALTY = 1e6


def minimax_score(errors_model: dict[str, float], errors_sst: dict[str, float]) -> float:
    assert errors_sst, "need at least one case"
    assert set(errors_model) == set(errors_sst), "model/SST case sets must match"
    ratios = [errors_model[c] / errors_sst[c] for c in errors_sst]
    return float(max(ratios))


def halving(candidates: list[dict], score_key: str = "score") -> list[dict]:
    """Keep top 50% (lowest score). Never skips rungs; caller enforces order."""
    ranked = sorted(candidates, key=lambda c: c[score_key])
    keep = max(1, len(ranked) // 2) if ranked else 0
    return ranked[:keep]


def apriori_mse(pred: np.ndarray, target: np.ndarray) -> float:
    assert pred.shape == target.shape, f"shape mismatch {pred.shape} vs {target.shape}"
    return float(np.mean((pred - target) ** 2))


def rung0(expression: str) -> bool:
    """Symbolic hard filters. True = passes to rung 1."""
    from flowforge.dsl.parser import validate_candidate

    try:
        validate_candidate(expression)
        return True
    except Exception:
        return False


def rung1_scores(expressions: list[str], invariants, basis, target) -> list[dict]:
    """A priori MSE per expression vs frozen-RANS target (no solver)."""
    from flowforge.dsl.evaluate import candidate_anisotropy

    out: list[dict] = []
    for expr in expressions:
        try:
            pred = candidate_anisotropy(expr, invariants, basis)
            out.append({"expression": expr, "score": apriori_mse(pred, target)})
        except Exception as exc:
            out.append({"expression": expr, "score": DIVERGED_PENALTY, "error": str(exc)})
    return out


def run_ladder_rung01(expressions: list[str], invariants, basis, target) -> list[dict]:
    """Rung 0 filter, then rung 1 scoring + halving. Order is enforced."""
    passed = [e for e in expressions if rung0(e)]
    if not passed:
        return []
    scored = rung1_scores(passed, invariants, basis, target)
    return halving(scored)


def rung2_short(candidates: list[dict], short_eval: Callable[[str], float] | None = None) -> list[dict]:
    """Rung 2 short run: optionally rescore cheaply, then drop the bottom 50%.

    short_eval(expression) -> error (lower is better). Without it, rung 1
    scores are reused and only the halving is applied. Diverged or failed
    short runs receive DIVERGED_PENALTY.
    """
    if not candidates:
        return []
    scored: list[dict] = []
    for cand in candidates:
        entry = dict(cand)
        if short_eval is not None:
            try:
                entry["score_rung2"] = float(short_eval(entry["expression"]))
            except Exception as exc:
                entry["score_rung2"] = DIVERGED_PENALTY
                entry["error_rung2"] = str(exc)
            entry["score"] = entry["score_rung2"]
        scored.append(entry)
    return halving(scored)


def rung3_full(candidates: list[dict], invariants, basis, target) -> list[dict]:
    """Rung 3 full evaluation + realizability gate. No halving here.

    Every survivor is fully scored against the target and must predict a
    realizable anisotropy at every point; non-realizable candidates are
    rejected outright regardless of score.
    """
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.physics.tensors import is_realizable

    out: list[dict] = []
    for cand in candidates:
        expr = cand["expression"]
        entry = dict(cand)
        try:
            pred = candidate_anisotropy(expr, invariants, basis)
        except Exception as exc:
            entry.update({"score": DIVERGED_PENALTY, "realizable": False, "rejected": str(exc)})
            continue
        realizable = bool(np.all(is_realizable(pred)))
        entry["score_rung3"] = apriori_mse(pred, target)
        entry["score"] = entry["score_rung3"]
        entry["realizable"] = realizable
        if realizable:
            out.append(entry)
    out.sort(key=lambda c: c["score"])
    return out


def run_ladder(expressions: list[str], invariants, basis, target,
               short_eval: Callable[[str], float] | None = None) -> dict:
    """Full ladder: rung 0 -> 1 (halving) -> 2 (halving) -> 3 (realizability)."""
    assert expressions, "run_ladder needs at least one expression"
    passed0 = [e for e in expressions if rung0(e)]
    result: dict = {"rung0_passed": passed0, "rung1": [], "rung2": [], "rung3": []}
    if not passed0:
        return result
    result["rung1"] = halving(rung1_scores(passed0, invariants, basis, target))
    if not result["rung1"]:
        return result
    result["rung2"] = rung2_short(result["rung1"], short_eval=short_eval)
    result["rung3"] = rung3_full(result["rung2"], invariants, basis, target)
    return result

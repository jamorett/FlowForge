"""Successive-halving ladder (S5.1). Deterministic scoring only.

Rung 0 symbolic (no data) -> Rung 1 a priori (drop 50%) -> realizability
filter -> Rung 2 short (drop 50% again) -> Rung 3 full + realizability. Selection is minimax:
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
    """Symbolic hard filters. True = passes to rung 1.

    A genuinely invalid candidate returns False.  A broken environment
    (``ImportError``/``ModuleNotFoundError``, e.g. missing sympy raised
    either by the import above or inside validation) propagates so it
    is not masked as "candidate rejected" (CH-09).
    """
    from flowforge.dsl.parser import validate_candidate

    try:
        validate_candidate(expression)
        return True
    except ImportError:
        raise
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
        except ImportError:
            raise
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


def rung2_short(candidates: list[dict], short_eval: Callable[[str], float] | None = None,
                score_key: str = "score") -> list[dict]:
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
            except ImportError:
                raise
            except Exception as exc:
                entry["score_rung2"] = DIVERGED_PENALTY
                entry["error_rung2"] = str(exc)
            entry["score"] = entry["score_rung2"]
        scored.append(entry)
    return halving(scored, score_key=score_key)


def _realizability(pred, b_rans=None) -> tuple[bool, float]:
    """Return (realizable everywhere, fraction of checked points that pass).

    With ``b_rans`` the total anisotropy ``b_rans + pred`` is checked at
    every point where both are finite; otherwise ``pred`` alone is checked.
    """
    from flowforge.physics.tensors import is_realizable

    pred_arr = np.asarray(pred)
    if b_rans is None:
        flags = is_realizable(pred_arr)
        n_total = int(flags.size)
        passed = int(np.count_nonzero(flags))
        return bool(np.all(flags)), (float(passed / n_total) if n_total else 0.0)
    baseline = np.asarray(b_rans)
    total_field = baseline + pred_arr
    if pred_arr.ndim >= 2:
        finite_pred = np.isfinite(pred_arr).reshape(pred_arr.shape[0], -1).all(axis=1)
    else:
        finite_pred = np.isfinite(pred_arr)
    if baseline.ndim >= 2:
        finite_base = np.isfinite(baseline).reshape(baseline.shape[0], -1).all(axis=1)
    else:
        finite_base = np.isfinite(baseline)
    checked = finite_pred & finite_base
    n_checked = int(np.count_nonzero(checked))
    if n_checked == 0:
        return False, 0.0
    flags = is_realizable(total_field[checked])
    passed = int(np.count_nonzero(flags))
    return bool(np.all(flags)), float(passed / n_checked)


def realizable_only(candidates: list[dict], invariants, basis, b_rans=None) -> list[dict]:
    """Drop non-realizable candidates before the rung-2 halving.

    Realizability is a hard gate that is cheap a priori, so it runs before
    halving: otherwise the halving can keep only a non-realizable leader and
    rung 3 then rejects the whole round although realizable candidates were
    in the pool. Same check as :func:`rung3_full`; rung 3 still re-checks.
    """
    from flowforge.dsl.evaluate import candidate_anisotropy

    kept: list[dict] = []
    for cand in candidates:
        try:
            pred = candidate_anisotropy(cand["expression"], invariants, basis)
        except ImportError:
            raise
        except Exception:
            continue
        if _realizability(pred, b_rans)[0]:
            kept.append(cand)
    return kept


def rung3_full(candidates: list[dict], invariants, basis, target, b_rans=None) -> list[dict]:
    """Rung 3 full evaluation + realizability gate. No halving here.

    Every survivor is fully scored against the target and must predict a
    realizable anisotropy at every point; non-realizable candidates are
    rejected outright regardless of score.

    Args:
        candidates: Rung-2 survivors with ``expression`` keys.
        invariants: Mapping ``I1..I5`` to ``(N,)`` arrays.
        basis: Mapping ``T1..T4`` to ``(N, 3, 3)`` arrays.
        target: ``(N, 3, 3)`` correction target.
        b_rans: Optional ``(N, 3, 3)`` frozen-RANS baseline anisotropy.
            When given, realizability is checked on the total anisotropy
            ``b_rans + pred`` at every point where both are finite
            (non-finite rows are ignored, like the scoring); otherwise
            the correction ``pred`` alone is checked at every point
            (legacy behavior).

    Returns:
        Accepted entries sorted by score. Each entry carries ``score``,
        ``score_rung3``, ``realizable`` and ``realizable_fraction``
        (fraction of checked points that pass).
    """
    from flowforge.dsl.evaluate import candidate_anisotropy

    out: list[dict] = []
    for cand in candidates:
        expr = cand["expression"]
        entry = dict(cand)
        try:
            pred = candidate_anisotropy(expr, invariants, basis)
        except ImportError:
            raise
        except Exception as exc:
            entry.update({"score": DIVERGED_PENALTY, "realizable": False, "realizable_fraction": 0.0, "rejected": str(exc)})
            continue
        realizable, fraction = _realizability(pred, b_rans)
        entry["score_rung3"] = apriori_mse(pred, target)
        entry["score"] = entry["score_rung3"]
        entry["realizable"] = realizable
        entry["realizable_fraction"] = fraction
        if realizable:
            out.append(entry)
    out.sort(key=lambda c: c["score"])
    return out


def run_ladder(expressions: list[str], invariants, basis, target,
               short_eval: Callable[[str], float] | None = None, b_rans=None) -> dict:
    """Full ladder: rung 0 -> 1 (halving) -> realizable -> 2 (halving) -> 3 (realizability).

    Args:
        expressions: Candidate expressions.
        invariants: Mapping ``I1..I5`` to ``(N,)`` arrays.
        basis: Mapping ``T1..T4`` to ``(N, 3, 3)`` arrays.
        target: ``(N, 3, 3)`` correction target.
        short_eval: Optional rung-2 scorer.
        b_rans: Optional baseline anisotropy forwarded to rung 3; when
            given, realizability is checked on the total anisotropy.
    """
    assert expressions, "run_ladder needs at least one expression"
    passed0 = [e for e in expressions if rung0(e)]
    result: dict = {"rung0_passed": passed0, "rung1": [], "rung2": [], "rung3": []}
    if not passed0:
        return result
    result["rung1"] = halving(rung1_scores(passed0, invariants, basis, target))
    if not result["rung1"]:
        return result
    advanced = realizable_only(result["rung1"], invariants, basis, b_rans=b_rans)
    result["rung2"] = rung2_short(advanced, short_eval=short_eval)
    result["rung3"] = rung3_full(result["rung2"], invariants, basis, target, b_rans=b_rans)
    return result

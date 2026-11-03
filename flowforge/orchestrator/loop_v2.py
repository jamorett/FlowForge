"""Loop v2: diagnose -> propose -> fit/score -> revise -> population -> champion.

Opt-in alternative to ``round.run_round`` (decisions.md 2026-11-03). Same
deterministic pieces (fitter, frozen scorer, realizability, champion rule,
event log, session budget); different wiring:

1. diagnostician (LLM) reads the population's per-case scores and names
   where it fails (replaces Board + Analyst, and runs BEFORE proposal);
2. theorist_v2 x G (LLM) proposes 3 candidates per group from that diagnosis;
3. fit + score (deterministic, one node): constants fitted on train only,
   per-case train ratios, held-out ratios (attack hills + redteam split),
   realizability;
4. reviser (LLM, same group) sees its own per-case scores and revises once;
5. population (deterministic): top-K with tensor-set diversity, carried
   across rounds in the append-only event log;
6. champion (deterministic) from the population, same elegance rule.

Red team = a score column (held-out ratios), not a mid-pipeline gate: the
champion avoids broken candidates when any unbroken one exists. Validation
is computed for the champion only, for reporting; no LLM ever sees it.
Coder, Composer, Skeptic and the LLM red team are not dispatched.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

POP_K = 8
PER_TENSOR_SET = 2  # diversity: at most this many per tensor signature before filling by rank
ROUND_STEPS_V2 = ("diagnostician", "theorist", "score", "revise", "score_revised",
                  "population", "champion")
_CASES: dict[str, tuple] = {}  # case id -> (inv, basis, target), loaded once per process


def _case(cid: str):
    from flowforge.data.frozen_fields import load_frozen_fields

    if cid not in _CASES:  # same subset as score_on_cases (4000 points, seed 0)
        _CASES[cid] = load_frozen_fields([cid], max_points_per_case=4000)
    return _CASES[cid]


def _ratio(expr: str, cid: str) -> float:
    from flowforge.data.frozen_fields import score_expression

    try:
        value = float(score_expression(expr, *_case(cid))["ratio"])
    except (ValueError, KeyError, AssertionError, FileNotFoundError):
        return float("inf")
    return value if np.isfinite(value) else float("inf")


def evaluate(expr: str, train, train_ids: list[str], heldout_ids: list[str],
             break_ratio: float) -> dict:
    """Fit on train, then score per case. Never touches validation or locked."""
    from flowforge.data.frozen_fields import score_expression
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.dsl.expr_fit import fit_expression
    from flowforge.dsl.parser import complexity, validate_candidate
    from flowforge.ladder.ladder import _realizability

    inv, basis, target, b_rans = train
    fit = fit_expression(expr, inv, basis, target, snap=True, b_rans=b_rans)
    status = fit.get("status")
    if status in ("invalid", "fit_failed", "fit_rejected"):
        return {"expression": expr, "status": status, "reason": fit.get("reason", status)}
    text = str(fit["expression"])
    try:
        nodes = complexity(validate_candidate(text))
        realizable = bool(_realizability(candidate_anisotropy(text, inv, basis), b_rans)[0])
        train_ratio = float(score_expression(text, inv, basis, target)["ratio"])
    except (ValueError, KeyError, AssertionError, TypeError) as exc:
        return {"expression": expr, "status": "score_failed", "reason": str(exc)}
    if not np.isfinite(train_ratio):
        train_ratio = float("inf")
    per_train = {c: round(_ratio(text, c), 4) for c in train_ids}
    held = {c: round(_ratio(text, c), 4) for c in heldout_ids}
    selection = max([train_ratio, *held.values()])
    return {"expression": text, "original": expr, "status": "ok", "nodes": nodes,
            "realizable": realizable, "train_ratio": round(train_ratio, 4),
            "train_cases": per_train, "heldout_cases": held,
            "selection": round(selection, 4) if np.isfinite(selection) else float("inf"),
            "broken": any(v > break_ratio for v in held.values())}


def update_population(population: list[dict], new: list[dict], k: int = POP_K) -> list[dict]:
    """Top-k usable candidates (realizable, finite), unbroken first, with tensor-set diversity."""
    from flowforge.orchestrator.history import tensors_in

    pool = {p["expression"]: p for p in population}
    for item in new:
        if item.get("status") == "ok" and item.get("realizable") and np.isfinite(item.get("selection", np.inf)):
            prev = pool.get(item["expression"])
            if prev is None or item["selection"] < prev["selection"]:
                pool[item["expression"]] = item
    ranked = sorted(pool.values(), key=lambda p: (p["broken"], p["selection"], p["nodes"]))
    kept, per_sig = [], {}
    for p in ranked:  # first pass: diversity cap per tensor signature
        sig = tuple(tensors_in(p["expression"]))
        if per_sig.get(sig, 0) < PER_TENSOR_SET and len(kept) < k:
            kept.append(p)
            per_sig[sig] = per_sig.get(sig, 0) + 1
    for p in ranked:  # then fill by rank
        if len(kept) >= k:
            break
        if p not in kept:
            kept.append(p)
    return sorted(kept, key=lambda p: (p["broken"], p["selection"], p["nodes"]))


def pick_champion_v2(population: list[dict], redteam: bool) -> dict | None:
    """Same elegance rule as v1: within 3% of the best score, lowest DL."""
    from flowforge.elegance.engine import description_length, pick_champion

    pool = [p for p in population if not (redteam and p["broken"])] or list(population)
    if not pool:
        return None
    key = "selection" if redteam else "train_ratio"
    best = pick_champion([{"id": p["expression"], "worst_error": float(p[key]),
                           "dl": description_length(p["nodes"], [])} for p in pool])
    return next(p for p in pool if p["expression"] == best["id"])


def _brief(p: dict) -> dict:
    """What an LLM may see about a candidate: train and held-out scores, never validation."""
    return {k: p[k] for k in ("expression", "selection", "broken", "train_ratio",
                              "train_cases", "heldout_cases") if k in p}


def _clean(value):
    """Non-finite floats -> None, so events stay strict JSON for the UI."""
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _last_event(events_path: Path, kind: str) -> dict | None:
    if not events_path.exists():
        return None
    last = None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == kind:
            last = event
    return last


def _dispatch(role: str, runtime, context: dict):
    """Live LLM call; returns the validated model or None (logged by the caller)."""
    from flowforge.agents import dispatcher
    from flowforge.agents.runtime.client import BudgetExceededError

    try:
        return dispatcher.dispatch_role(role, runtime, context)
    except BudgetExceededError:
        raise
    except dispatcher.RoleDispatchError as exc:
        logger.warning("loop_v2 %s dispatch failed: %s", role, exc)
        return None


def run_round(round_no: int, mock: bool = False, session: str | None = None,
              session_dir=None, runs_root=None, groups: int = 1, redteam: bool = True,
              sam: bool = False, **_ignored) -> dict:
    """One v2 round; returns the same result shape as ``round.run_round``."""
    from flowforge.agents.runtime.client import BudgetExceededError, ModelRuntime
    from flowforge.agents.runtime.event_logger import session_spent
    from flowforge.data.frozen_fields import (
        load_frozen_fields, score_on_cases, selection_case_ids, train_case_ids,
        validation_case_ids, worst_ratio)
    from flowforge.orchestrator.round import (
        GROUP_MECHANISMS, REDTEAM_BREAK_RATIO, _make_logger, _prompt_hash_for,
        _resolve_session_dir)

    if mock:
        raise ValueError("loop_v2 has no mock mode; tests patch its dispatch instead")
    if not isinstance(groups, int) or groups < 1:
        raise ValueError(f"groups must be a positive int, got {groups!r}")
    resolved_dir, session_name = _resolve_session_dir(round_no, session_dir, session, runs_root)
    event_logger = _make_logger(resolved_dir)
    events_path = Path(event_logger.path)
    runtime = ModelRuntime(logger=event_logger)
    spent_before = session_spent(events_path)
    runtime.spent = spent_before

    def log(step: str, role: str, **fields) -> None:
        event_logger.log({"type": step, "step": step, "role": role, "round": round_no,
                          "session": session_name, "loop": "v2", "mode": "frozen",
                          "source": "live", "mock": False, "synthetic": False,
                          "prompt_hash": _prompt_hash_for(f"flowforge:v2:round:{round_no}:{step}"),
                          **_clean(fields)})

    def result(status: str, champion: dict | None, proposed: int, **extra) -> dict:
        return {"round": round_no, "mock": False, "loop": "v2", "groups": groups,
                "proposed": proposed, "champion": champion, "status": status,
                "session": session_name, "session_dir": str(resolved_dir),
                "events_path": str(events_path), "steps": list(ROUND_STEPS_V2),
                "tokens_used": runtime.tokens,
                "dollars_spent": round(runtime.spent - spent_before, 4), **extra}

    try:
        train_ids = train_case_ids()
        heldout_ids = selection_case_ids() if redteam else []
        train = load_frozen_fields(train_ids, max_points_per_case=4000, return_b_rans=True)
        prev = _last_event(events_path, "population")
        population = list(prev.get("population", [])) if prev else []
        rejected = list(prev.get("rejected", []))[-10:] if prev else []

        diag = _dispatch("diagnostician", runtime, {
            "round": round_no, "population": [_brief(p) for p in population[:5]],
            "rejected": rejected})
        diagnosis = diag.model_dump() if diag else {"failure_regions": [], "next_hypothesis": ""}
        log("diagnostician", "diagnostician", fallback=diag is None, **diagnosis)

        evaluated: list[dict] = []
        proposed = 0
        for g in range(groups):
            gid, mech = f"g{g}", GROUP_MECHANISMS[g % len(GROUP_MECHANISMS)]
            prop = _dispatch("theorist_v2", runtime, {
                "mechanism": mech, "diagnosis": diagnosis,
                "population": [_brief(p) for p in population], "rejected": rejected})
            exprs = list(prop.expressions) if prop else []
            proposed += len(exprs)
            log("theorist", "theorist", group=gid, mechanism=mech, fallback=prop is None,
                expressions=exprs, mechanisms=list(prop.mechanisms) if prop else [])
            first = [evaluate(e, train, train_ids, heldout_ids, REDTEAM_BREAK_RATIO) for e in exprs]
            log("score", "fitter", group=gid, candidates=first)

            rev = _dispatch("reviser", runtime, {
                "your_candidates": [_brief(c) if c.get("status") == "ok" else c for c in first],
                "population_best": [_brief(p) for p in population[:3]],
                "diagnosis": diagnosis}) if first else None
            revised = list(rev.expressions) if rev else []
            proposed += len(revised)
            log("revise", "reviser", group=gid, fallback=bool(first) and rev is None,
                expressions=revised)
            second = [evaluate(e, train, train_ids, heldout_ids, REDTEAM_BREAK_RATIO) for e in revised]
            log("score_revised", "fitter", group=gid, candidates=second)
            evaluated += [{**c, "group": gid} for c in first + second]

        population = update_population(population, evaluated)
        new_rejected = [{"expression": c["expression"], "reason": c.get("reason") or
                         ("non_realizable" if not c.get("realizable") else "unscorable")}
                        for c in evaluated if c.get("status") != "ok" or not c.get("realizable")]
        log("population", "population", population=population,
            rejected=(rejected + new_rejected)[-20:])

        best = pick_champion_v2(population, redteam)
        champion = None
        if best is not None:  # validation for reporting only: no LLM and no selection reads it
            expr = best["expression"]
            validation = score_on_cases(expr, validation_case_ids())
            from flowforge.elegance.engine import description_length

            champion = {"expression": expr, "dl": description_length(best["nodes"], []),
                        "selection_ratio": best["selection"],
                        "worst_error": best["selection"] if redteam else best["train_ratio"],
                        "train": {"ratio": best["train_ratio"]}, "attack_ratios": best["heldout_cases"],
                        "validation": validation, "worst_validation_ratio": worst_ratio(validation),
                        "validation_mode": "frozen", "loop": "v2"}
        log("champion", "champion", champion=champion, status="ok" if champion else "all_rejected")
        return result("ok" if champion else "all_rejected", champion, proposed)
    except BudgetExceededError as exc:
        log("error", "orchestrator", error_type=type(exc).__name__, error=str(exc))
        return result("error", None, 0, error=str(exc), error_type=type(exc).__name__)
    except Exception as exc:
        logger.error("loop_v2 round failed: %s", exc)
        log("error", "orchestrator", error_type=type(exc).__name__, error=str(exc))
        return result("error", None, 0, error=str(exc), error_type=type(exc).__name__)

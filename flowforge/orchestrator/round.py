"""Unattended round loop (S5.4).

Board -> Theorist -> Coder -> Rungs -> Analyst/Skeptic -> RedTeam -> Composer.
Deterministic scoring only (flowforge.ladder). Agents never self-grade.
Mock mode (--mock-llm) runs rungs 0-3 on synthetic fields without API
credits or Docker, so CI exercises the real ladder code path. The short
rung-2 evaluator is the first-points a priori error; production swaps in
the capped coarse-solver evaluator behind the same callable.

Live mode dispatches each role through the prompt loader -> ModelRuntime
pipeline, validates structured outputs with Pydantic schemas, and logs
every step to ``runs/<session>/events.jsonl``.

Every run appends one JSONL event per pipeline step to
``runs/<session>/events.jsonl`` (or ``<session_dir>/events.jsonl``) via
``flowforge.agents.runtime.event_logger.EventLogger`` when importable,
so the API in ``flowforge.api.server`` can replay/stream the same file.
Each event carries a ``prompt_hash`` (SHA-256 of a canonical prompt label)
so it is compatible with ``EventLogger.log``'s hash requirement for
response-bearing events and with replay lookups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MOCK_CANDIDATES = ("0", "I1", "tanh(I1)", "I1 + I2")

ROUND_STEPS = (
    "board", "theorist", "coder",
    "rung0", "rung1", "rung2", "rung3",
    "analyst", "skeptic", "redteam", "composer", "champion",
)


def synthetic_fields(n: int = 8, seed: int = 42):
    from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis

    rng = np.random.default_rng(seed)
    grad = 0.1 * rng.standard_normal((n, 3, 3))
    omega = np.full(n, 2.0)
    s, w = normalized_tensors(grad, omega)
    inv = invariants(s, w)
    basis = tensor_basis(s, w)
    target = 0.5 * basis["T1"]  # known ground truth: g = 0.5
    return inv, basis, target



class _AppendOnlyWriter:
    """Minimal append-only fallback if EventLogger cannot be imported."""

    def __init__(self, session_dir: Path):
        self.session_dir = Path(session_dir)
        self.path = self.session_dir / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: dict) -> None:
        assert isinstance(event, dict), "event must be a dict"
        if "response" in event:
            h = event.get("prompt_hash")
            if not isinstance(h, str) or not h.strip():
                raise ValueError("missing prompt_hash on response event; hash is required")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    def read_events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _make_logger(session_dir: Path):
    try:
        from flowforge.agents.runtime.event_logger import EventLogger

        return EventLogger(session_dir)
    except Exception:
        return _AppendOnlyWriter(session_dir)


def _prompt_hash_for(text: str) -> str:
    try:
        from flowforge.agents.runtime.event_logger import prompt_hash

        return prompt_hash(text)
    except Exception:
        assert isinstance(text, str) and text, "prompt must be a non-empty string"
        return hashlib.sha256(text.encode()).hexdigest()


def _resolve_session_dir(round_no: int, session_dir, session, runs_root):
    """Return (session_dir_path, session_name)."""
    if session_dir is not None:
        p = Path(session_dir)
        if p.name == "events.jsonl":
            p = p.parent
        return p, (str(session) if session else p.name)
    if session is not None:
        root = Path(runs_root) if runs_root is not None else Path("runs")
        return root / str(session), str(session)
    name = f"round-{round_no}"
    if runs_root is not None:
        return Path(runs_root) / name, name
    return Path("runs") / name, name


def _build_library_context() -> dict:
    """Read the on-disk library to build context for the board."""
    lib_root = Path("library")
    context: dict = {"modules": [], "findings": [], "attacks": [], "rejected": []}
    for key, subdir in [("modules", "modules"), ("findings", "findings"),
                        ("attacks", "attacks"), ("rejected", "rejected")]:
        d = lib_root / subdir
        if d.exists():
            for f in sorted(d.glob("*.json")):
                try:
                    context[key].append(json.loads(f.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    pass
    return context


def _run_round_live(round_no: int, candidates: tuple[str, ...],
                    session_name: str, resolved_dir: Path,
                    event_logger, events_path: Path) -> dict:
    """Execute a live round with actual LLM calls via the dispatcher.

    Each role is dispatched through the prompt loader -> ModelRuntime
    pipeline with structured output validation.
    """
    from flowforge.agents.dispatcher import dispatch_role, RoleDispatchError
    from flowforge.agents.runtime.client import ModelRuntime, BudgetExceededError
    from flowforge.dsl.parser import complexity, validate_candidate
    from flowforge.elegance.engine import description_length, pick_champion
    from flowforge.ladder.ladder import apriori_mse, run_ladder

    runtime = ModelRuntime(logger=event_logger)
    inv, basis, target = synthetic_fields()

    # --- Step 1: Board ---
    lib_context = _build_library_context()
    board_context = {
        "findings": lib_context.get("findings", []),
        "scores": [],
        "budget_left": f"${runtime.spent:.2f} / $50.00",
        "round": round_no,
        "library_modules": lib_context.get("modules", []),
    }

    try:
        board_result = dispatch_role("board", runtime, board_context)
        board_data = board_result.model_dump()
    except (RoleDispatchError, BudgetExceededError) as exc:
        logger.warning("Board dispatch failed: %s; using mock fallback", exc)
        from flowforge.agents.dispatcher import dispatch_role_mock
        board_result = dispatch_role_mock("board")
        board_data = board_result.model_dump()

    event_logger.log({
        "type": "board", "step": "board", "role": "board",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:board"),
        **board_data,
    })

    # --- Step 2: Theorist ---
    theorist_context = {
        "mechanisms": board_data.get("mechanisms", []),
        "closure_cards": lib_context.get("modules", []),
        "group_history": lib_context.get("findings", []),
    }
    try:
        theorist_result = dispatch_role("theorist", runtime, theorist_context)
        proposed = theorist_result.model_dump()
        expressions = proposed.get("expressions", list(candidates))
    except (RoleDispatchError, BudgetExceededError) as exc:
        logger.warning("Theorist dispatch failed: %s; using default candidates", exc)
        expressions = list(candidates)
        proposed = {"expressions": expressions, "mechanisms": ["fallback"],
                     "risk_audit": f"Theorist fallback: {exc}"}

    event_logger.log({
        "type": "theorist", "step": "theorist", "role": "theorist",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:theorist"),
        **proposed,
    })

    # --- Step 3: Coder (fit constants) ---
    coder_context = {"candidates": expressions}
    try:
        coder_result = dispatch_role("coder", runtime, coder_context)
        coder_data = coder_result.model_dump()
    except (RoleDispatchError, BudgetExceededError) as exc:
        logger.warning("Coder dispatch failed: %s; using defaults", exc)
        coder_data = {"constants": [], "apriori_mse": 999.0,
                       "risk_audit": f"Coder fallback: {exc}"}

    event_logger.log({
        "type": "coder", "step": "coder", "role": "coder",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:coder"),
        **coder_data,
    })

    # --- Steps 4-7: Rungs (deterministic, same as mock) ---
    def short_eval(expr: str) -> float:
        from flowforge.dsl.evaluate import candidate_anisotropy
        k = max(1, len(target) // 2)
        sub_inv = {name: arr[:k] for name, arr in inv.items()}
        sub_basis = {name: arr[:k] for name, arr in basis.items()}
        return apriori_mse(candidate_anisotropy(expr, sub_inv, sub_basis), target[:k])

    ladder = run_ladder(expressions, inv, basis, target, short_eval=short_eval)
    survivors = ladder["rung1"]
    final = ladder["rung3"]

    for rung in ("rung0", "rung1", "rung2", "rung3"):
        rung_data = ladder.get(rung, ladder.get(f"{rung}_passed", []))
        event_logger.log({
            "type": rung, "step": rung, "role": rung,
            "round": round_no, "mock": False, "synthetic": True,
            "source": "ladder", "mode": "live", "session": session_name,
            "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:{rung}"),
            "survivors": json.loads(json.dumps(rung_data, default=float)) if isinstance(rung_data, list) else [],
        })

    # --- Step 8: Analyst ---
    analyst_context = {
        "final_candidates": [s.get("expression") for s in final],
        "error_summary": {s.get("expression"): s.get("score") for s in final},
    }
    try:
        analyst_result = dispatch_role("analyst", runtime, analyst_context)
        analyst_data = analyst_result.model_dump()
    except (RoleDispatchError, BudgetExceededError) as exc:
        logger.warning("Analyst dispatch failed: %s", exc)
        analyst_data = {"failure_regions": [], "next_hypothesis": f"Fallback: {exc}",
                         "risk_audit": f"Analyst fallback: {exc}"}

    event_logger.log({
        "type": "analyst", "step": "analyst", "role": "analyst",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:analyst"),
        **analyst_data,
    })

    # --- Step 9: Skeptic ---
    skeptic_context = {
        "candidates": [s.get("expression") for s in final],
        "evidence": analyst_data,
    }
    try:
        skeptic_result = dispatch_role("skeptic", runtime, skeptic_context)
        skeptic_data = skeptic_result.model_dump()
    except (RoleDispatchError, BudgetExceededError) as exc:
        logger.warning("Skeptic dispatch failed: %s", exc)
        skeptic_data = {"objections": [], "requested_tests": [],
                         "risk_audit": f"Skeptic fallback: {exc}"}

    event_logger.log({
        "type": "skeptic", "step": "skeptic", "role": "skeptic",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:skeptic"),
        **skeptic_data,
    })

    # --- Step 10: Red Team ---
    redteam_context = {
        "champions": [s.get("expression") for s in final],
        "attack_suite": lib_context.get("attacks", []),
    }
    try:
        redteam_result = dispatch_role("redteam", runtime, redteam_context)
        redteam_data = redteam_result.model_dump()
    except (RoleDispatchError, BudgetExceededError) as exc:
        logger.warning("RedTeam dispatch failed: %s", exc)
        redteam_data = {"flows": [{"kind": "fallback"}],
                         "risk_audit": f"RedTeam fallback: {exc}"}

    event_logger.log({
        "type": "redteam", "step": "redteam", "role": "redteam",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:redteam"),
        **redteam_data,
    })

    # --- Step 11: Composer ---
    composer_context = {
        "modules": [s.get("expression") for s in final],
        "regime_features": ["I1", "I2"],
    }
    try:
        composer_result = dispatch_role("composer", runtime, composer_context)
        composer_data = composer_result.model_dump()
    except (RoleDispatchError, BudgetExceededError) as exc:
        logger.warning("Composer dispatch failed: %s", exc)
        composer_data = {"modules": [s.get("expression", "0") for s in final] or ["0"],
                          "gates": [],
                          "risk_audit": f"Composer fallback: {exc}"}

    # --- Champion selection ---
    champion = None
    champion_pool = final if final else []
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

    event_logger.log({
        "type": "composer", "step": "composer", "role": "composer",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:composer"),
        "champion": champion,
        **composer_data,
    })

    event_logger.log({
        "type": "champion", "step": "champion", "role": "champion",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "live", "mode": "live", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:champion"),
        "champion": champion,
        "status": "ok" if final else "all_rejected",
    })

    return {
        "round": round_no,
        "mock": False,
        "proposed": len(expressions),
        "survivors_rung1": survivors,
        "survivors_rung2": ladder["rung2"],
        "final_rung3": final,
        "champion": champion,
        "status": "ok" if final else "all_rejected",
        "session": session_name,
        "session_dir": str(resolved_dir),
        "events_path": str(events_path),
        "event_count": len(ROUND_STEPS),
        "steps": list(ROUND_STEPS),
        "tokens_used": runtime.tokens,
        "dollars_spent": round(runtime.spent, 4),
    }


def run_round(round_no: int, mock: bool = False,
              candidates: tuple[str, ...] = MOCK_CANDIDATES,
              session_dir=None, session: str | None = None,
              runs_root=None, **kwargs) -> dict:
    # Tolerated aliases from callers that name the session differently.
    if session_dir is None:
        session_dir = kwargs.pop("output_dir", kwargs.pop("session_path", None))
    if session is None:
        session = kwargs.pop("session_id", kwargs.pop("session_name", None))
    if kwargs:
        raise TypeError(f"run_round got unexpected arguments: {sorted(kwargs)}")

    # Resolve the event log FIRST: the chain must be observable even when
    # the DSL stack (sympy) is unavailable in this environment.
    resolved_dir, session_name = _resolve_session_dir(round_no, session_dir, session, runs_root)
    event_logger = _make_logger(resolved_dir)
    events_path = Path(event_logger.path) if hasattr(event_logger, "path") else resolved_dir / "events.jsonl"

    try:
        from flowforge.dsl.parser import complexity, validate_candidate
        from flowforge.elegance.engine import description_length, pick_champion
        from flowforge.ladder.ladder import apriori_mse, run_ladder
    except ModuleNotFoundError as exc:
        for step in ROUND_STEPS:
            event_logger.log({
                "type": step, "step": step, "role": step, "round": round_no,
                "mock": bool(mock), "synthetic": True, "source": "synthetic",
                "mode": "mock" if mock else "synthetic", "session": session_name,
                "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:{step}"),
                "status": "unavailable",
            })
        event_logger.log({
            "type": "error", "step": "error", "role": "orchestrator",
            "round": round_no, "session": session_name,
            "error_type": type(exc).__name__, "error": str(exc),
            "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:error"),
        })
        return {
            "round": round_no, "mock": mock, "proposed": len(candidates),
            "survivors_rung1": [], "survivors_rung2": [], "final_rung3": [],
            "champion": None, "status": "error",
            "error_type": type(exc).__name__, "error": str(exc),
            "session": session_name, "session_dir": str(resolved_dir),
            "events_path": str(events_path),
            "event_count": len(ROUND_STEPS) + 1, "steps": list(ROUND_STEPS),
        }

    # --- Live mode: dispatch through LLM pipeline ---
    if not mock:
        try:
            return _run_round_live(
                round_no, candidates, session_name,
                resolved_dir, event_logger, events_path,
            )
        except Exception as exc:
            logger.error("Live round failed: %s; falling back to mock", exc)
            # Fall through to mock path so the round always completes.

    # --- Mock mode: deterministic scoring on synthetic fields ---
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

    result: dict = {
        "round": round_no,
        "mock": mock,
        "proposed": len(candidates),
        "survivors_rung1": survivors,
        "survivors_rung2": ladder["rung2"],
        "final_rung3": final,
        "champion": champion,
        "status": "ok" if final else "all_rejected",
    }

    def _clean(value):
        return json.loads(json.dumps(value, default=float))

    step_details: dict[str, dict] = {
        "board": {"candidates": list(candidates), "proposed": len(candidates)},
        "theorist": {"candidates": list(candidates), "expressions": list(candidates)},
        "coder": {"candidates": list(candidates)},
        "rung0": {"passed": list(ladder.get("rung0_passed", [])), "candidates": list(candidates)},
        "rung1": {"survivors": _clean(survivors)},
        "rung2": {"survivors": _clean(ladder["rung2"])},
        "rung3": {"survivors": _clean(final), "final": _clean(final)},
        "analyst": {"final_count": len(final), "candidates": [s.get("expression") for s in final]},
        "skeptic": {"final_count": len(final), "candidates": [s.get("expression") for s in final]},
        "redteam": {"flows": [], "final_count": len(final)},
        "composer": {"champion": champion, "final_count": len(final)},
        "champion": {"champion": champion, "status": result["status"]},
    }

    for step in ROUND_STEPS:
        prompt_label = f"flowforge:round:{round_no}:step:{step}"
        event = {
            "type": step,
            "step": step,
            "role": step,
            "round": round_no,
            "mock": bool(mock),
            # Fields are synthetic in this path (see synthetic_fields);
            # label them as such, in mock mode and otherwise.
            "synthetic": True,
            "source": "synthetic",
            "mode": "mock" if mock else "synthetic",
            "session": session_name,
            "prompt_hash": _prompt_hash_for(prompt_label),
            **step_details[step],
        }
        event_logger.log(event)

    result["session"] = session_name
    result["session_dir"] = str(resolved_dir)
    result["events_path"] = str(events_path)
    result["event_count"] = len(ROUND_STEPS)
    result["steps"] = list(ROUND_STEPS)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--session", default=None)
    parser.add_argument("--session-dir", default=None)
    args = parser.parse_args()
    print(run_round(args.round, mock=args.mock_llm,
                    session=args.session, session_dir=args.session_dir))


if __name__ == "__main__":
    main()

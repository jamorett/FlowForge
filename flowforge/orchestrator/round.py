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
import datetime
import hashlib
import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

ATTACKS_DIR = Path("library/attacks")
# Frozen red-team break rule: a candidate worse than SST (ratio > 1.0) on
# ANY unseen flow is broken. SST is the "do nothing" baseline, so losing
# to it off-training is an objective failure, not a tunable threshold.
REDTEAM_BREAK_RATIO = 1.0

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


def _analyst_regions(expressions: list[str], session_dir: Path,
                     round_no: int = 1) -> list[dict]:
    """Render error maps + segment regions for finalists.

    Returns evidence dicts folded into the analyst step event, so the
    12-step chain keeps its exact shape. Tries the real case via the
    analyst tools; without ingested data it falls back to an explicitly
    labeled illustrative synthetic slice (never measured evidence).
    Failures yield [] and never break the round.
    """
    from flowforge.render.sam_client import segment_error_regions

    out: list[dict] = []
    for i, expr in enumerate(list(expressions)[:2]):
        if not expr:
            continue
        image: str | None = None
        illustrative = False
        try:
            from flowforge.agents.tools.registry import TOOLS

            image = TOOLS["render_error_map"](
                expr, case_id="periodic_hill_re5600",
                out_png=str(Path(session_dir) / f"err_r{round_no}_{i}.png"))
        except Exception as exc:
            logger.warning("analyst render (real case) failed: %s", exc)
            image = None
        if image is None:
            try:
                import numpy as np

                from flowforge.dsl.evaluate import candidate_anisotropy
                from flowforge.render.error_map import render_png

                inv, basis, target = synthetic_fields(n=64)
                pred = candidate_anisotropy(expr, inv, basis)
                err = np.linalg.norm(
                    (pred - target).reshape(64, -1), axis=1)
                side = 8
                out_png = Path(session_dir) / f"err_synth_{i}.png"
                render_png(err.reshape(side, side), out_png)
                image = str(out_png)
                illustrative = True
            except Exception as exc:
                logger.warning("analyst render (synthetic) failed: %s", exc)
                continue
        try:
            seg = segment_error_regions(image, use_api=False)
        except Exception as exc:
            logger.warning("analyst segment failed: %s", exc)
            continue
        out.append({"candidate": expr, "image": image,
                    "illustrative": illustrative,
                    "source": seg["source"], "regions": seg["regions"]})
    return out


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


def _frozen_attack_stem(case_id: str, expression: str) -> str:
    """Return the stable attack file stem for a break."""
    digest = hashlib.sha256(f"{case_id}|{expression}".encode()).hexdigest()[:10]
    return f"attack_{digest}"


def _save_frozen_break(case_id: str, expression: str, ratio: float, flow: dict | None) -> None:
    """Persist one frozen-mode break under ATTACKS_DIR (append-only)."""
    stem = _frozen_attack_stem(case_id, expression)
    path = ATTACKS_DIR / f"{stem}.json"
    if path.exists():
        return
    alpha = flow.get("alpha") if isinstance(flow, dict) else None
    reynolds = flow.get("reynolds") if isinstance(flow, dict) else None
    payload = {"id": stem, "name": f"Frozen attack {case_id} breaks {expression}", "role": "redteam", "base_case": case_id, "parameter_sweeps": {"slope_steepness_alpha": alpha, "reynolds_number": reynolds}, "broken_expression": expression, "ratio": float(ratio), "mode": "frozen", "status": "active", "created_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")}
    try:
        ATTACKS_DIR.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("persist frozen attack failed: %s", exc)


def select_champion_by_train_attack(
    finalists: list[dict],
    invariants: dict[str, np.ndarray],
    basis: dict[str, np.ndarray],
    target: np.ndarray,
    attack_cases: list[str] | None = None,
) -> dict | None:
    """Pick the round champion by train + attack worst-case ratio.

    Selection uses ``max(train_ratio, attack_ratios)`` only; validation is
    never consulted so it stays held-out for reporting. Within 3% of the
    best selection ratio, :func:`pick_champion` applies the elegance /
    description-length tie-break. Candidates that cannot be scored get
    ``inf`` so they lose to any scored finalist. Returns
    ``{"expression", "dl", "worst_error", "selection_ratio",
    "selection_metric"}`` or ``None`` when the pool is empty.
    """
    from flowforge.data.frozen_fields import score_expression, score_on_cases
    from flowforge.dsl.parser import complexity, validate_candidate
    from flowforge.elegance.engine import description_length, pick_champion

    if not finalists:
        return None
    attack_ids = list(attack_cases) if attack_cases else []
    enriched: list[dict] = []
    for item in finalists:
        expression = str(item.get("expression", ""))
        validate_candidate(expression)
        try:
            train_payload = score_expression(expression, invariants, basis, target)
            train_ratio = float(train_payload.get("ratio"))
            if np.isnan(train_ratio):
                raise ValueError("NaN train ratio")
        except (TypeError, ValueError, KeyError, AssertionError) as exc:
            logger.warning("champion train scoring failed for %s: %s", expression, exc)
            train_ratio = float("inf")
        selection = float(train_ratio)
        if attack_ids and np.isfinite(selection):
            attack_scores = score_on_cases(expression, attack_ids, max_points_per_case=4000)
            for case_id in attack_ids:
                payload = attack_scores.get(case_id, {})
                if not isinstance(payload, dict) or "error" in payload:
                    continue
                try:
                    attack_ratio = float(payload.get("ratio"))
                except (TypeError, ValueError):
                    logger.warning("champion attack bad ratio %s on %s", expression, case_id)
                    continue
                if np.isnan(attack_ratio):
                    logger.warning("champion attack NaN ratio %s on %s", expression, case_id)
                    selection = float("inf")
                    break
                if attack_ratio > selection:
                    selection = float(attack_ratio)
        enriched.append({
            "id": expression,
            "worst_error": float(selection),
            "dl": description_length(complexity(validate_candidate(expression)), []),
        })
    best = pick_champion(enriched)
    return {"expression": best["id"], "dl": best["dl"],
            "worst_error": float(best["worst_error"]),
            "selection_ratio": float(best["worst_error"]),
            "selection_metric": "max(train_ratio, attack_ratios)"}


def _run_round_live(round_no: int, candidates: tuple[str, ...],
                    session_name: str, resolved_dir: Path,
                    event_logger, events_path: Path,
                    groups: int = 1, group_ids: list | None = None,
                    mechanisms: list | None = None,
                    redteam: bool = True) -> dict:
    """Execute a live round with actual LLM calls via the dispatcher.

    Each role is dispatched through the prompt loader -> ModelRuntime
    pipeline with structured output validation. With groups > 1, one
    theorist is dispatched per group (each with its mechanism brief);
    rungs score the merged pool and the remaining roles merge across
    groups.
    """
    from flowforge.agents.dispatcher import dispatch_role, RoleDispatchError
    from flowforge.agents.runtime.client import ModelRuntime, BudgetExceededError
    from flowforge.ladder.ladder import (
        apriori_mse, halving, rung0 as rung0_pass, rung1_scores,
        realizable_only, rung2_short, rung3_full,
    )

    from flowforge.orchestrator.history import session_history

    previous_results = session_history(events_path)
    runtime = ModelRuntime(logger=event_logger)
    from flowforge.data.frozen_fields import (
        attack_case_for,
        available_attack_flows,
        load_frozen_fields,
        redteam_case_ids,
        score_expression,
        score_on_cases,
        train_case_ids,
        validation_case_ids,
        worst_ratio,
    )

    _train_cases = train_case_ids()
    try:
        loaded = load_frozen_fields(_train_cases, max_points_per_case=4000, return_b_rans=True)
    except TypeError as exc:
        if "return_b_rans" not in str(exc):
            raise
        inv, basis, target = load_frozen_fields(_train_cases, max_points_per_case=4000)
        b_rans = None
    else:
        if isinstance(loaded, tuple) and len(loaded) == 4:
            inv, basis, target, b_rans = loaded
        else:
            inv, basis, target = loaded
            b_rans = None

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

    # --- Step 2: Theorist(s), one per group ---
    group_ids = group_ids or ["g0"]
    mechanisms = mechanisms or [""]
    from flowforge.literature.library_cards import load_literature_cards

    raw_cards = load_literature_cards()
    literature_cards = [
        {"id": card.get("id"), "reference": card.get("reference"),
         "dsl_expression": card.get("dsl_expression"),
         "mechanism": card.get("mechanism")}
        for card in raw_cards if isinstance(card, dict)
    ]
    group_exprs: dict[str, list[str]] = {}
    for gid, mech in zip(group_ids, mechanisms):
        theorist_context = {
            "mechanisms": ([mech] if mech else [])
            + list(board_data.get("mechanisms", [])),
            "closure_cards": lib_context.get("modules", []),
            "literature_cards": literature_cards,
            "group_history": lib_context.get("findings", []),
            "previous_results": previous_results,
        }
        try:
            theorist_result = dispatch_role("theorist", runtime, theorist_context)
            proposed = theorist_result.model_dump()
            gexprs = proposed.get("expressions", list(candidates))
        except (RoleDispatchError, BudgetExceededError) as exc:
            logger.warning("Theorist dispatch failed for %s: %s; using defaults", gid, exc)
            gexprs = list(candidates)
            proposed = {"expressions": gexprs, "mechanisms": ["fallback"],
                         "risk_audit": f"Theorist fallback: {exc}"}
        group_exprs[gid] = list(gexprs)
        event_logger.log({
            "type": "theorist", "step": "theorist", "role": "theorist",
            "round": round_no, "group": gid, "mechanism": mech,
            "mock": False, "synthetic": False,
            "source": "live", "mode": "live", "session": session_name,
            "prompt_hash": _prompt_hash_for(
                f"flowforge:round:{round_no}:step:theorist"
                + (f":{gid}" if len(group_ids) > 1 else "")),
            **proposed,
        })
    expressions = [e for gid in group_ids for e in group_exprs[gid]]

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

    # --- Step 3b: Fit numeric constants (deterministic, before ladder) ---
    from flowforge.dsl.expr_fit import fit_expression

    fits: list[dict] = []
    fitted_flat: list[str] = []
    for expr in expressions:
        fit = fit_expression(expr, inv, basis, target, snap=True, b_rans=b_rans)
        fits.append(json.loads(json.dumps(fit, default=float)))
        fitted_flat.append(str(fits[-1].get("expression", expr)))
    idx = 0
    for gid in group_ids:
        count = len(group_exprs.get(gid, []))
        group_exprs[gid] = fitted_flat[idx:idx + count]
        idx += count
    expressions = list(fitted_flat)

    event_logger.log({
        "type": "fit", "step": "fit", "role": "fitter",
        "round": round_no, "mock": False, "synthetic": False,
        "source": "frozen-rans", "mode": "frozen", "session": session_name,
        "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:fit"),
        "fits": json.loads(json.dumps(fits, default=float)),
    })

    # --- Steps 4-5: Rungs 0-1 (deterministic, same as mock) ---
    def short_eval(expr: str) -> float:
        from flowforge.dsl.evaluate import candidate_anisotropy
        k = max(1, len(target) // 2)
        sub_inv = {name: arr[:k] for name, arr in inv.items()}
        sub_basis = {name: arr[:k] for name, arr in basis.items()}
        return apriori_mse(candidate_anisotropy(expr, sub_inv, sub_basis), target[:k])

    def _log_rung(rung: str, rung_data: list, **extra) -> None:
        event_logger.log({
            "type": rung, "step": rung, "role": rung,
            "round": round_no, "mock": False, "synthetic": False,
            "source": "frozen-rans", "mode": "frozen", "session": session_name,
            "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:{rung}"),
            "cases": list(_train_cases),
            "n_points": int(target.shape[0]),
            "survivors": json.loads(json.dumps(rung_data, default=float)) if isinstance(rung_data, list) else [],
            **extra,
        })

    passed0 = [e for e in expressions if rung0_pass(e)]
    rung1 = halving(rung1_scores(passed0, inv, basis, target)) if passed0 else []
    _log_rung("rung0", passed0)
    _log_rung("rung1", rung1)
    survivors = rung1

    # --- Step 6: Red Team screens the rung-1 pool (frozen mode) ---
    # A candidate worse than SST on ANY unseen flow is broken: excluded
    # before rung 2, with an attack report. Post-hoc annotation of
    # rung-3 survivors alone never applied pressure (30 pilot rounds,
    # 0 breaks) because the filter upstream only ever saw robust
    # candidates. This is the RP1 treatment: exclusion, not annotation.
    attack_cases: list[str] = []
    redteam_breaks: list[dict] = []
    broken_exprs: set[str] = set()
    case_flow: dict[str, dict] = {}
    all_broken = False
    if redteam:
        redteam_context = {
            "champions": [s.get("expression") for s in rung1],
            "attack_suite": lib_context.get("attacks", []),
            "available_frozen_flows": available_attack_flows(),
        }
        try:
            redteam_result = dispatch_role("redteam", runtime, redteam_context)
            redteam_data = redteam_result.model_dump()
        except (RoleDispatchError, BudgetExceededError) as exc:
            logger.warning("RedTeam dispatch failed: %s", exc)
            redteam_data = {"flows": [{"kind": "fallback"}],
                             "risk_audit": f"RedTeam fallback: {exc}"}
        flows = redteam_data.get("flows", [])
        if not isinstance(flows, list):
            flows = []
        attacks: list[dict] = []
        seen: set[str] = set()
        for spec in flows:
            cid = attack_case_for(spec) if isinstance(spec, dict) else None
            ok = cid is not None
            attacks.append({"flow": spec, "case_id": cid, "available": ok})
            if ok and cid not in seen:
                seen.add(cid)
                attack_cases.append(cid)
                if isinstance(spec, dict):
                    case_flow[cid] = spec
        # Probe set: red-team attack hills plus the redteam split
        # (never train/validation/locked). Break = worse than SST anywhere.
        from flowforge.config import EXPECTED_LOCKED_CASES

        excluded = set(_train_cases) | set(validation_case_ids()) | set(EXPECTED_LOCKED_CASES)
        probe_cases: list[str] = []
        for cid in list(attack_cases) + list(redteam_case_ids()):
            if cid not in probe_cases and cid not in excluded:
                probe_cases.append(cid)
        for item in rung1:
            expr = item.get("expression", "")
            if not expr:
                continue
            scores = score_on_cases(expr, probe_cases, max_points_per_case=4000)
            for cid, payload in scores.items():
                if not isinstance(payload, dict) or "error" in payload:
                    logger.warning("frozen attack error %s on %s: %s", expr, cid, payload.get("error") if isinstance(payload, dict) else payload)
                    continue
                try:
                    ratio = float(payload.get("ratio"))
                except (TypeError, ValueError):
                    logger.warning("frozen attack bad ratio %s on %s", expr, cid)
                    continue
                if ratio > REDTEAM_BREAK_RATIO:
                    redteam_breaks.append({"expression": expr, "case_id": cid, "ratio": ratio})
        broken_exprs = {b["expression"] for b in redteam_breaks}
        for b in redteam_breaks:
            _save_frozen_break(b["case_id"], b["expression"], b["ratio"], case_flow.get(b["case_id"]))
        event_logger.log({
            "type": "redteam", "step": "redteam", "role": "redteam",
            "round": round_no, "mock": False, "synthetic": False,
            "source": "live", "session": session_name,
            "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:redteam"),
            **redteam_data,
            "mode": "frozen",
            "attacks": attacks,
            "probe_cases": probe_cases,
            "breaks": redteam_breaks,
            "n_broken": len(redteam_breaks),
            "excluded": sorted(broken_exprs),
            "pool": "rung1",
        })
    else:
        redteam_data = {"skipped": True, "flows": [],
                         "risk_audit": "Red-team disabled (ablation)."}
        event_logger.log({
            "type": "redteam", "step": "redteam", "role": "redteam",
            "round": round_no, "mock": False, "synthetic": False,
            "source": "live", "mode": "live", "session": session_name,
            "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:redteam"),
            "skipped": True,
            **redteam_data,
        })

    # --- Steps 7: Rungs 2-3 on unbroken survivors only ---
    advanced = [s for s in rung1 if s.get("expression") not in broken_exprs]
    # Realizability (hard gate, cheap a priori) before halving, so a
    # non-realizable leader cannot crowd out realizable candidates.
    realizable = realizable_only(advanced, inv, basis, b_rans=b_rans)
    kept = {s.get("expression") for s in realizable}
    dropped = [s.get("expression") for s in advanced if s.get("expression") not in kept]
    rung2 = rung2_short(realizable, short_eval=short_eval)
    _log_rung("rung2", rung2, non_realizable=dropped)
    rung3 = rung3_full(rung2, inv, basis, target, b_rans=b_rans)
    _log_rung("rung3", rung3)
    final = rung3
    if not final and redteam_breaks:
        all_broken = True

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
        "regions": _analyst_regions(
            [s.get("expression", "") for s in (final or [])],
            resolved_dir, round_no),
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

    # --- Step 11: Composer ---
    # (Red team already ran at Step 6 on the rung-1 pool; broken
    # expressions were excluded before rungs 2-3. The safety filter in
    # champion selection below is a second net for the same set.)
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
    if redteam and broken_exprs and champion_pool:
        kept = [s for s in champion_pool if s.get("expression") not in broken_exprs]
        if kept:
            champion_pool = kept
        else:
            all_broken = True
    if champion_pool:
        # Selection uses train + attack only; validation stays held-out
        # (reported below but never read for selection to avoid leakage).
        champion = select_champion_by_train_attack(
            champion_pool, inv, basis, target,
            attack_cases=attack_cases if redteam else [],
        )
    if champion is not None:
        # Validation is held-out: computed for reporting only, never for selection.
        champion_expression = str(champion.get("expression", ""))
        train_score = score_expression(champion_expression, inv, basis, target)
        validation_scores = score_on_cases(champion_expression, validation_case_ids())
        worst_validation = worst_ratio(validation_scores)
        champion.update({
            "train": train_score,
            "validation": validation_scores,
            "worst_validation_ratio": worst_validation,
            "validation_mode": "frozen",
        })
        if redteam:
            ratios: dict[str, float] = {}
            for cid in attack_cases:
                sc = score_on_cases(champion_expression, [cid], max_points_per_case=4000)
                pl = sc.get(cid, {})
                if "error" in pl:
                    logger.warning("frozen champion error %s on %s: %s", champion_expression, cid, pl.get("error"))
                    continue
                try:
                    ratios[cid] = float(pl.get("ratio"))
                except (TypeError, ValueError):
                    logger.warning("frozen champion bad ratio %s on %s", champion_expression, cid)
                    continue
            champion["attack_ratios"] = ratios
            if all_broken:
                champion["all_broken"] = True

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
        "groups": groups,
        "staffing": [{"group": gid, "mechanism": mech,
                      "candidates": group_exprs[gid]}
                     for gid, mech in zip(group_ids, mechanisms)],
        "survivors_rung1": survivors,
        "survivors_rung2": rung2,
        "final_rung3": final,
        "champion": champion,
        "status": "ok" if final else "all_rejected",
        "redteam_excluded": sorted(broken_exprs),
        "session": session_name,
        "session_dir": str(resolved_dir),
        "events_path": str(events_path),
        "event_count": len(ROUND_STEPS) + max(0, len(group_ids) - 1) + 1,
        "steps": list(ROUND_STEPS),
        "tokens_used": runtime.tokens,
        "dollars_spent": round(runtime.spent, 4),
    }


GROUP_MECHANISMS = (
    "streamline_curvature",
    "pressure_gradient_sensitization",
    "secondary_flow_anisotropy",
    "non_equilibrium_lag",
)


def run_round(round_no: int, mock: bool = False,
              candidates: tuple[str, ...] = MOCK_CANDIDATES,
              session_dir=None, session: str | None = None,
              runs_root=None, groups: int = 1, redteam: bool = True,
              **kwargs) -> dict:
    """Run one round. ``groups`` staffs parallel research groups (default 1).

    With one group the event chain is exactly the 12 classic steps.
    With N groups, theorist/coder/rung/analyst steps repeat per group
    (tagged ``group: g<i>`` with a mechanism brief) and skeptic/redteam/
    composer/champion merge across groups. ``groups`` must be >= 1.
    When ``redteam`` is False the red-team role is not dispatched and the
    redteam event is logged with ``"skipped": True``.
    """
    # Tolerated aliases from callers that name the session differently.
    if session_dir is None:
        session_dir = kwargs.pop("output_dir", kwargs.pop("session_path", None))
    if session is None:
        session = kwargs.pop("session_id", kwargs.pop("session_name", None))
    if kwargs:
        raise TypeError(f"run_round got unexpected arguments: {sorted(kwargs)}")

    if not isinstance(groups, int) or groups < 1:
        raise ValueError(f"groups must be a positive int, got {groups!r}")
    group_ids = [f"g{i}" for i in range(groups)]
    mechanisms = [GROUP_MECHANISMS[i % len(GROUP_MECHANISMS)] for i in range(groups)]
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
                groups=groups, group_ids=group_ids, mechanisms=mechanisms,
                redteam=redteam,
            )
        except Exception as exc:
            logger.error("Live round failed: %s", exc)
            event_logger.log({
                "type": "error", "step": "error", "role": "orchestrator",
                "round": round_no, "session": session_name,
                "error_type": type(exc).__name__, "error": str(exc),
                "prompt_hash": _prompt_hash_for(f"flowforge:round:{round_no}:step:error"),
            })
            return {
                "round": round_no, "mock": False, "proposed": len(candidates),
                "survivors_rung1": [], "survivors_rung2": [], "final_rung3": [],
                "champion": None, "status": "error",
                "error_type": type(exc).__name__, "error": str(exc),
                "session": session_name, "session_dir": str(resolved_dir),
                "events_path": str(events_path),
                "event_count": 1, "steps": list(ROUND_STEPS),
            }

    # --- Mock mode: deterministic scoring on synthetic fields ---
    inv, basis, target = synthetic_fields()

    def short_eval(expr: str) -> float:
        from flowforge.dsl.evaluate import candidate_anisotropy

        k = max(1, len(target) // 2)
        sub_inv = {name: arr[:k] for name, arr in inv.items()}
        sub_basis = {name: arr[:k] for name, arr in basis.items()}
        return apriori_mse(candidate_anisotropy(expr, sub_inv, sub_basis), target[:k])

    def _clean(value):
        return json.loads(json.dumps(value, default=float))

    # Staffing: split candidates round-robin across groups (group 0 keeps
    # the full list when groups == 1, preserving the classic chain).
    grouped: list[tuple[str, str, list[str]]] = []
    for i, gid in enumerate(group_ids):
        if groups == 1:
            gcands = list(candidates)
        else:
            gcands = [c for j, c in enumerate(candidates) if j % groups == i]
        grouped.append((gid, mechanisms[i], gcands))

    group_ladders: dict[str, dict] = {}
    merged_final: list[dict] = []
    for gid, _mech, gcands in grouped:
        if gcands:
            gl = run_ladder(gcands, inv, basis, target, short_eval=short_eval)
        else:
            gl = {"rung1": [], "rung2": [], "rung3": []}
        group_ladders[gid] = gl
        for s in gl["rung3"]:
            merged_final.append({**s, "group": gid})

    final = merged_final
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

    staffing = [{"group": gid, "mechanism": mech,
                 "candidates": list(gc)} for gid, mech, gc in grouped]
    result: dict = {
        "round": round_no,
        "mock": mock,
        "proposed": len(candidates),
        "groups": groups,
        "staffing": staffing,
        "survivors_rung1": [s for gid, _, _ in grouped
                             for s in group_ladders[gid]["rung1"]],
        "survivors_rung2": [s for gid, _, _ in grouped
                             for s in group_ladders[gid]["rung2"]],
        "final_rung3": final,
        "champion": champion,
        "status": "ok" if final else "all_rejected",
    }

    def _step_event(step: str, role: str, group: str, mechanism: str | None,
                    details: dict) -> None:
        prompt_label = (f"flowforge:round:{round_no}:step:{step}"
                        + (f":{group}" if groups > 1 else ""))
        event = {
            "type": step,
            "step": step,
            "role": role,
            "round": round_no,
            "group": group,
            "mock": bool(mock),
            # Fields are synthetic in this path (see synthetic_fields);
            # label them as such, in mock mode and otherwise.
            "synthetic": True,
            "source": "synthetic",
            "mode": "mock" if mock else "synthetic",
            "session": session_name,
            "prompt_hash": _prompt_hash_for(prompt_label),
            **details,
        }
        if mechanism is not None:
            event["mechanism"] = mechanism
        event_logger.log(event)

    _step_event("board", "board", "all", None,
                {"candidates": list(candidates), "proposed": len(candidates),
                 "groups": groups, "staffing": staffing})
    for gid, mech, gcands in grouped:
        gl = group_ladders[gid]
        gfinal = [s for s in final if s.get("group") == gid]
        _step_event("theorist", "theorist", gid, mech,
                    {"candidates": list(gcands), "expressions": list(gcands)})
        _step_event("coder", "coder", gid, mech, {"candidates": list(gcands)})
        _step_event("rung0", "rung0", gid, mech,
                    {"passed": list(gl.get("rung0_passed", [])),
                     "candidates": list(gcands)})
        _step_event("rung1", "rung1", gid, mech, {"survivors": _clean(gl["rung1"])})
        _step_event("rung2", "rung2", gid, mech, {"survivors": _clean(gl["rung2"])})
        _step_event("rung3", "rung3", gid, mech,
                    {"survivors": _clean(gl["rung3"]),
                     "final": _clean([s for s in gl["rung3"]])})
        _step_event("analyst", "analyst", gid, mech,
                    {"final_count": len(gfinal),
                     "candidates": [s.get("expression") for s in gfinal],
                     "regions": _analyst_regions(
                         [s.get("expression", "") for s in gfinal],
                         resolved_dir, round_no)})
    _step_event("skeptic", "skeptic", "all", None,
                {"final_count": len(final),
                 "candidates": [s.get("expression") for s in final]})
    redteam_details: dict = {"flows": [], "final_count": len(final)}
    if not redteam:
        redteam_details["skipped"] = True
    _step_event("redteam", "redteam", "all", None, redteam_details)
    _step_event("composer", "composer", "all", None,
                {"champion": champion, "final_count": len(final)})
    _step_event("champion", "champion", "all", None,
                {"champion": champion, "status": result["status"]})

    result["session"] = session_name
    result["session_dir"] = str(resolved_dir)
    result["events_path"] = str(events_path)
    result["event_count"] = 1 + 7 * groups + 4
    result["steps"] = list(ROUND_STEPS)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--session", default=None)
    parser.add_argument("--session-dir", default=None)
    parser.add_argument("--groups", type=int, default=1)
    args = parser.parse_args()
    print(run_round(args.round, mock=args.mock_llm,
                    session=args.session, session_dir=args.session_dir,
                    groups=args.groups))


if __name__ == "__main__":
    main()

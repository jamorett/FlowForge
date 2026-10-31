"""Session history for the Theorist (Task 12).

Reads the current session's ``events.jsonl`` so later rounds can improve on
what earlier rounds of the same session already tried, scored, and broke.
Malformed lines are skipped and a missing file yields an empty history;
this helper never raises for bad *input* content.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

TENSORS = ("T1", "T2", "T3")


def empty_history() -> dict:
    """Return the canonical empty history payload."""
    return {
        "rounds_seen": 0,
        "best_candidates": [],
        "champions": [],
        "broken": [],
        "hints": [],
    }


def parse_float(value: Any) -> float | None:
    """Try to coerce ``value`` to float, else return None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def tensors_in(expression: str) -> list[str]:
    """Return the T1..T3 symbols appearing as substrings."""
    found: list[str] = []
    text = str(expression)
    for name in TENSORS:
        if name in text and name not in found:
            found.append(name)
    return found


def fit_record(raw: dict) -> dict | None:
    """Normalize one raw fit entry to expression/mse_after/mse_before."""
    expr = raw.get("expression", raw.get("expr", raw.get("candidate", raw.get("id"))))
    if not isinstance(expr, str) or not expr.strip():
        return None
    expression = expr.strip()
    after_raw = raw.get("mse_after", raw.get("mse", raw.get("score", raw.get("mse_fitted", raw.get("mse_fit")))))
    before_raw = raw.get(
        "mse_before",
        raw.get("mse0", raw.get("mse_initial", raw.get("mse_before_fit", raw.get("mse_unfitted", raw.get("mse_zero", raw.get("score_before")))))),
    )
    mse_after = parse_float(after_raw)
    mse_before = parse_float(before_raw)
    return {"expression": expression, "mse_after": mse_after, "mse_before": mse_before}


def champion_record(event: dict) -> dict | None:
    """Normalize one champion event to the public champion payload."""
    payload = event.get("champion")
    if payload is None or not isinstance(payload, dict):
        return None
    round_raw = event.get("round")
    round_no: int | None = None
    if isinstance(round_raw, int) and not isinstance(round_raw, bool):
        round_no = round_raw
    elif isinstance(round_raw, float) and round_raw.is_integer():
        round_no = int(round_raw)
    expr_raw = payload.get("expression")
    expression: str | None = None
    if isinstance(expr_raw, str) and expr_raw.strip():
        expression = expr_raw.strip()
    train_ratio: float | None = None
    train = payload.get("train")
    if isinstance(train, dict) and train.get("ratio") is not None:
        train_ratio = parse_float(train.get("ratio"))
    elif payload.get("train_ratio") is not None:
        train_ratio = parse_float(payload.get("train_ratio"))
    worst_raw = payload.get("worst_validation_ratio")
    worst_validation = parse_float(worst_raw) if worst_raw is not None else None
    attack_raw = payload.get("attack_ratios")
    attack_ratios: dict | None = attack_raw if isinstance(attack_raw, dict) else None
    return {
        "round": round_no,
        "expression": expression,
        "train_ratio": train_ratio,
        "worst_validation_ratio": worst_validation,
        "attack_ratios": attack_ratios,
    }


def build_hints(rounds_seen: int, best: list[dict], champions: list[dict], broken: list[dict]) -> list[str]:
    """Derive short plain-language hints only from the parsed numbers."""
    hints: list[str] = []
    if rounds_seen:
        hints.append(f"Seen {rounds_seen} previous round(s) in this session.")
    if best:
        counts: dict[str, int] = {}
        for item in best:
            for name in tensors_in(str(item.get("expression", ""))):
                counts[name] = counts.get(name, 0) + 1
        if counts:
            ordered = ", ".join(f"{name} in {counts[name]}/{len(best)}" for name in sorted(counts))
            hints.append(
                f"Useful tensors from best candidates: {ordered}. "
                "Vary the functions multiplying the most useful tensors."
            )
        top = best[0]
        if top.get("mse_after") is not None:
            hints.append(
                f"Improve on best candidate '{top.get('expression')}' "
                f"(mse_after {top.get('mse_after')}); add a missing tensor term."
            )
        else:
            hints.append(f"Improve on best candidate '{top.get('expression')}'; add a missing tensor term.")
        tried = ", ".join(f"'{item.get('expression')}'" for item in best[:5])
        hints.append(f"Never re-propose an already-tried expression: {tried}.")
    if champions:
        summaries: list[str] = []
        for champ in champions[:5]:
            summaries.append(f"round {champ.get('round')}: '{champ.get('expression')}'")
        hints.append(f"Previous champion(s): {', '.join(summaries)}.")
    if broken:
        unique = sorted({str(item["expression"]) for item in broken if item.get("expression")})
        joined = ", ".join(f"'{name}'" for name in unique[:5])
        hints.append(f"Do not re-propose broken expression(s): {joined}.")
    return hints


def session_history(events_path: str | Path, k: int = 5) -> dict:
    """Summarize previous rounds from the session ``events.jsonl``.

    Args:
        events_path: path to the session ``events.jsonl`` file.
        k: maximum number of distinct best candidates to return.

    Returns:
        Dict with ``rounds_seen``, ``best_candidates``, ``champions``,
        ``broken``, and ``hints``. Missing files yield an empty history;
        malformed JSONL lines are skipped and never raise.
    """
    try:
        limit = int(k)
    except (TypeError, ValueError):
        limit = 5
    limit = max(limit, 0)
    try:
        path = Path(events_path)
    except (TypeError, ValueError):
        return empty_history()
    try:
        if not path.exists() or not path.is_file():
            return empty_history()
    except OSError:
        return empty_history()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return empty_history()
    rounds: set[int] = set()
    collected_fits: list[dict] = []
    champions: list[dict] = []
    broken: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "champion":
            round_raw = event.get("round")
            if isinstance(round_raw, int) and not isinstance(round_raw, bool):
                rounds.add(round_raw)
            elif isinstance(round_raw, float) and round_raw.is_integer():
                rounds.add(int(round_raw))
            record = champion_record(event)
            if record is not None:
                champions.append(record)
        elif kind == "fit":
            fits = event.get("fits")
            if not isinstance(fits, list):
                continue
            for raw in fits:
                if not isinstance(raw, dict):
                    continue
                record = fit_record(raw)
                if record is not None:
                    collected_fits.append(record)
        elif kind == "redteam":
            breaks = event.get("breaks")
            if not isinstance(breaks, list):
                continue
            for raw in breaks:
                if not isinstance(raw, dict):
                    continue
                expr_raw = raw.get("expression")
                if not isinstance(expr_raw, str) or not expr_raw.strip():
                    continue
                case_raw = raw.get("case_id")
                case_id = case_raw if isinstance(case_raw, str) else None
                ratio_raw = raw.get("ratio")
                ratio = parse_float(ratio_raw) if ratio_raw is not None else None
                broken.append({
                    "expression": expr_raw.strip(),
                    "case_id": case_id,
                    "ratio": ratio,
                })
    best_by_expr: dict[str, dict] = {}
    for item in collected_fits:
        expression = str(item["expression"])
        prev = best_by_expr.get(expression)
        if prev is None:
            best_by_expr[expression] = item
            continue
        current_key = float("inf") if item.get("mse_after") is None else float(item["mse_after"])
        prev_key = float("inf") if prev.get("mse_after") is None else float(prev["mse_after"])
        if current_key < prev_key:
            best_by_expr[expression] = item
    ranked = sorted(
        best_by_expr.values(),
        key=lambda r: (r.get("mse_after") is None, r.get("mse_after") if r.get("mse_after") is not None else 0),
    )
    best_candidates = ranked[:limit]
    champions = sorted(champions, key=lambda r: (r.get("round") is None, r.get("round") if isinstance(r.get("round"), int) else 0))
    hints = build_hints(len(rounds), best_candidates, champions, broken)
    return {
        "rounds_seen": len(rounds),
        "best_candidates": best_candidates,
        "champions": champions,
        "broken": broken,
        "hints": hints,
    }

"""Config loaders for FlowForge (A5).

Single source of truth for budgets, case splits and frozen tolerances.
Loaders read YAML from ``configs/`` under the repo root, validate required
keys, and raise :class:`ValueError` with a clear message on any
missing/invalid value. ``root=None`` resolves to the repo root derived
from this file (``Path(__file__).parents[1]``); an explicit ``root`` may
be the repo root, a ``configs/`` directory, or the YAML file itself
(which makes tampered-copy tests in a temp dir straightforward).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "BudgetExceeded",
    "EXPECTED_LOCKED_CASES",
    "check_session_budget",
    "enforce_solver_caps",
    "load_budgets",
    "load_cases",
    "load_tolerances",
]

EXPECTED_LOCKED_CASES = frozenset({"square_duct", "nasa_wall_mounted_hump"})

_ALLOWED_SPLITS = frozenset({"train", "validation", "locked"})
_ALLOWED_MODES = frozenset({"short", "full"})

_TOLERANCE_KEYS = (
    "elegance_margin",
    "snapping_tolerance",
    "identity_tolerance",
    "oracle_ratio",
    "baseline_epsilon",
    "realizability_tolerance",
    "mesh_tolerance",
    "gate_penalty_bits",
)


class BudgetExceeded(ValueError):
    """Raised when a solver-run or dollar budget cap would be exceeded."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_config(root: Path | str | None, filename: str) -> Path:
    """Resolve ``filename`` under configs/, honouring an explicit root."""
    if root is None:
        return _repo_root() / "configs" / filename
    p = Path(root)
    if p.is_file():
        return p
    for candidate in (p / "configs" / filename, p / filename):
        if candidate.is_file():
            return candidate
    # Nothing exists yet: return the canonical location for the error msg.
    return p / "configs" / filename


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} config not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{label} config is not valid YAML ({path}): {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{label} config must be a YAML mapping, got {type(data).__name__}: {path}"
        )
    return data


def _require_keys(data: dict[str, Any], keys: Any, label: str, path: Path) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError(
            f"{label} config {path} is missing required key(s): "
            + ", ".join(repr(k) for k in missing)
        )


def _require_number(data: dict[str, Any], key: str, label: str, path: Path) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{label} config {path}: {key!r} must be a number, "
            f"got {type(value).__name__} {value!r}"
        )
    if not math.isfinite(float(value)):
        raise ValueError(f"{label} config {path}: {key!r} must be finite, got {value!r}")
    return float(value)


def load_budgets(root: Path | str | None = None) -> dict[str, Any]:
    """Load and validate ``configs/budgets.yaml``."""
    path = _resolve_config(root, "budgets.yaml")
    data = _load_yaml(path, "budgets")
    _require_keys(data, ("session_dollar_limit", "roles", "solver_caps"), "budgets", path)
    limit = _require_number(data, "session_dollar_limit", "budgets", path)
    if limit <= 0:
        raise ValueError(
            f"budgets config {path}: 'session_dollar_limit' must be > 0, got {limit}"
        )
    roles = data["roles"]
    if not isinstance(roles, dict) or not roles:
        raise ValueError(f"budgets config {path}: 'roles' must be a non-empty mapping")
    for role, cfg in roles.items():
        if not isinstance(cfg, dict) or not cfg.get("model"):
            raise ValueError(
                f"budgets config {path}: roles[{role!r}] must be a mapping "
                "with a non-empty 'model'"
            )
    caps = data["solver_caps"]
    if not isinstance(caps, dict):
        raise ValueError(f"budgets config {path}: 'solver_caps' must be a mapping")
    _require_keys(
        caps,
        ("max_solver_runs_per_round", "short_run_timeout_seconds", "full_run_timeout_seconds"),
        "budgets solver_caps",
        path,
    )
    for key in (
        "max_solver_runs_per_round",
        "short_run_timeout_seconds",
        "full_run_timeout_seconds",
    ):
        value = caps[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"budgets config {path}: solver_caps[{key!r}] must be a number, "
                f"got {type(value).__name__} {value!r}"
            )
        if float(value) <= 0:
            raise ValueError(
                f"budgets config {path}: solver_caps[{key!r}] must be > 0, got {value!r}"
            )
    if int(caps["max_solver_runs_per_round"]) != caps["max_solver_runs_per_round"]:
        raise ValueError(
            f"budgets config {path}: solver_caps['max_solver_runs_per_round'] "
            f"must be an integer, got {caps['max_solver_runs_per_round']!r}"
        )
    return data


def load_cases(root: Path | str | None = None) -> dict[str, Any]:
    """Load and validate ``configs/cases.yaml`` including the frozen split guard.

    The locked split must be exactly ``square_duct`` +
    ``nasa_wall_mounted_hump``; either case appearing under any other
    split (in particular ``train``) raises :class:`ValueError`.
    """
    path = _resolve_config(root, "cases.yaml")
    data = _load_yaml(path, "cases")
    _require_keys(data, ("cases",), "cases", path)
    cases = data["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"cases config {path}: 'cases' must be a non-empty list")
    seen: set[str] = set()
    for i, entry in enumerate(cases):
        if not isinstance(entry, dict):
            raise ValueError(f"cases config {path}: cases[{i}] must be a mapping")
        _require_keys(entry, ("id", "split", "source"), f"cases[{i}]", path)
        case_id, split, source = entry["id"], entry["split"], entry["source"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"cases config {path}: cases[{i}]['id'] must be a non-empty string")
        if case_id in seen:
            raise ValueError(f"cases config {path}: duplicate case id {case_id!r}")
        seen.add(case_id)
        if split not in _ALLOWED_SPLITS:
            raise ValueError(
                f"cases config {path}: case {case_id!r} has invalid split {split!r}; "
                f"expected one of {sorted(_ALLOWED_SPLITS)}"
            )
        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                f"cases config {path}: case {case_id!r} 'source' must be a non-empty string"
            )
        if case_id in EXPECTED_LOCKED_CASES and split != "locked":
            raise ValueError(
                f"cases config {path}: frozen split violation: locked case "
                f"{case_id!r} appears as split={split!r} (must stay 'locked'; "
                "locked cases must never be train/validation)"
            )
    locked = {e["id"] for e in cases if e["split"] == "locked"}
    if locked != EXPECTED_LOCKED_CASES:
        raise ValueError(
            f"cases config {path}: frozen split violation: locked cases must be "
            f"exactly {sorted(EXPECTED_LOCKED_CASES)}, got {sorted(locked)}"
        )
    return data


def load_tolerances(root: Path | str | None = None) -> dict[str, Any]:
    """Load and validate ``configs/tolerances.yaml`` (frozen values)."""
    path = _resolve_config(root, "tolerances.yaml")
    data = _load_yaml(path, "tolerances")
    _require_keys(data, _TOLERANCE_KEYS, "tolerances", path)
    for key in _TOLERANCE_KEYS:
        _require_number(data, key, "tolerances", path)
    for key in (
        "elegance_margin",
        "snapping_tolerance",
        "identity_tolerance",
        "oracle_ratio",
        "baseline_epsilon",
        "mesh_tolerance",
    ):
        if not 0 < float(data[key]) < 1:
            raise ValueError(
                f"tolerances config {path}: {key!r} must be in (0, 1), got {data[key]!r}"
            )
    # realizability_tolerance is a signed eigenvalue floor (-1e-4): finite only.
    if float(data["gate_penalty_bits"]) <= 0:
        raise ValueError(
            f"tolerances config {path}: 'gate_penalty_bits' must be > 0, "
            f"got {data['gate_penalty_bits']!r}"
        )
    return data


def enforce_solver_caps(
    runs_used: int,
    mode: str = "short",
    root: Path | str | None = None,
) -> int:
    """Enforce ``max_solver_runs_per_round`` from budgets before a new run.

    Boundary semantics: ``runs_used`` is the number of solver runs
    *already consumed* in this round, checked before launching the next
    one. With the frozen cap of 10, ``runs_used=9`` is allowed (that
    launches the 10th run) and ``runs_used=10`` raises
    :class:`BudgetExceeded` (that would launch the 11th run), i.e. the
    check is ``runs_used >= max_solver_runs_per_round``.

    Returns the cap so callers can log it.
    """
    if mode not in _ALLOWED_MODES:
        raise ValueError(f"unknown run mode: {mode!r} (expected 'short' or 'full')")
    if isinstance(runs_used, bool) or not isinstance(runs_used, int):
        raise ValueError(f"runs_used must be an int, got {type(runs_used).__name__} {runs_used!r}")
    if runs_used < 0:
        raise ValueError(f"runs_used must be >= 0, got {runs_used}")
    cap = int(load_budgets(root)["solver_caps"]["max_solver_runs_per_round"])
    if runs_used >= cap:
        raise BudgetExceeded(
            f"solver run cap exceeded for mode={mode!r}: {runs_used} run(s) already "
            f"used in this round, cap is {cap} (max_solver_runs_per_round); "
            "refusing to launch another run"
        )
    return cap


def check_session_budget(
    spent: float,
    root: Path | str | None = None,
) -> float:
    """Enforce ``session_dollar_limit`` from budgets.

    Spending exactly at the limit is allowed; ``spent`` strictly above
    the limit raises :class:`BudgetExceeded`. Returns the limit.
    """
    if isinstance(spent, bool) or not isinstance(spent, (int, float)):
        raise ValueError(f"spent must be a number, got {type(spent).__name__} {spent!r}")
    if not math.isfinite(float(spent)) or float(spent) < 0:
        raise ValueError(f"spent must be a finite number >= 0, got {spent!r}")
    limit = float(load_budgets(root)["session_dollar_limit"])
    if float(spent) > limit:
        raise BudgetExceeded(
            f"session dollar budget exceeded: spent ${float(spent):.2f} "
            f"> session_dollar_limit ${limit:.2f}"
        )
    return limit

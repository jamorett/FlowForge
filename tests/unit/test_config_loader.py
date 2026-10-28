"""A5 config-loader tests. No pytest dependency: plain asserts so the
file also runs as ``python tests/unit/test_config_loader.py`` (pytest
collects the same ``test_*`` functions unchanged)."""

from __future__ import annotations

import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flowforge.config import (
    BudgetExceeded,
    check_session_budget,
    enforce_solver_caps,
    load_budgets,
    load_cases,
    load_tolerances,
)

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TOLERANCES = {
    "elegance_margin": 0.03,
    "snapping_tolerance": 0.01,
    "identity_tolerance": 1.0e-6,
    "oracle_ratio": 0.70,
    "baseline_epsilon": 0.05,
    "realizability_tolerance": -1.0e-4,
    "mesh_tolerance": 0.02,
    "gate_penalty_bits": 16,
}


@contextmanager
def _raises(exc_type, needle=""):
    try:
        yield
    except exc_type as exc:
        assert needle.lower() in str(exc).lower(), f"{needle!r} not in: {exc}"
        return
    raise AssertionError(f"expected {exc_type.__name__} to be raised")


def _temp_root_with(config_name: str, data) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="flowforge-config-"))
    cfg = tmp / "configs"
    cfg.mkdir(parents=True)
    (cfg / config_name).write_text(yaml.safe_dump(data), encoding="utf-8")
    return tmp


def test_load_budgets_parses_real_config():
    budgets = load_budgets()
    assert budgets["session_dollar_limit"] == 50.00
    assert budgets["solver_caps"]["max_solver_runs_per_round"] == 10
    assert budgets["solver_caps"]["short_run_timeout_seconds"] == 60
    assert budgets["solver_caps"]["full_run_timeout_seconds"] == 300
    assert budgets["roles"]["coder"]["model"]


def test_load_cases_parses_real_config():
    data = load_cases()
    by_id = {c["id"]: c["split"] for c in data["cases"]}
    assert by_id["square_duct"] == "locked"
    assert by_id["nasa_wall_mounted_hump"] == "locked"
    assert by_id["periodic_hill_re5600"] == "train"


def test_load_tolerances_exact_values():
    assert load_tolerances() == EXPECTED_TOLERANCES


def test_enforce_solver_caps_boundary():
    # runs_used = runs already consumed: 9 -> 10th run allowed, 10 -> 11th blocked.
    assert enforce_solver_caps(9, "short") == 10
    assert enforce_solver_caps(9, "full") == 10
    assert enforce_solver_caps(0, "short") == 10
    with _raises(BudgetExceeded, "cap"):
        enforce_solver_caps(10, "short")
    with _raises(BudgetExceeded):
        enforce_solver_caps(11, "full")
    # BudgetExceeded must be catchable as ValueError.
    with _raises(ValueError):
        enforce_solver_caps(10, "short")


def test_enforce_solver_caps_invalid_mode():
    with _raises(ValueError, "mode"):
        enforce_solver_caps(0, "medium")


def test_check_session_budget():
    assert check_session_budget(0) == 50.00
    assert check_session_budget(50.00) == 50.00
    with _raises(BudgetExceeded, "budget"):
        check_session_budget(50.01)
    with _raises(ValueError):
        check_session_budget(100)


def test_load_cases_locked_as_train_raises():
    data = load_cases()
    for entry in data["cases"]:
        if entry["id"] == "square_duct":
            entry["split"] = "train"
    tmp = _temp_root_with("cases.yaml", data)
    try:
        with _raises(ValueError, "locked"):
            load_cases(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_cases_extra_locked_raises():
    data = load_cases()
    for entry in data["cases"]:
        if entry["id"] == "curved_step":
            entry["split"] = "locked"
    tmp = _temp_root_with("cases.yaml", data)
    try:
        with _raises(ValueError, "locked"):
            load_cases(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_tolerances_missing_key_raises():
    data = load_tolerances()
    del data["oracle_ratio"]
    tmp = _temp_root_with("tolerances.yaml", data)
    try:
        with _raises(ValueError, "oracle_ratio"):
            load_tolerances(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_budgets_missing_key_raises():
    data = load_budgets()
    del data["solver_caps"]
    tmp = _temp_root_with("budgets.yaml", data)
    try:
        with _raises(ValueError, "solver_caps"):
            load_budgets(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    _tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for _name, _fn in _tests:
        _fn()
        print(f"PASS {_name}")
    print(f"OK {len(_tests)} tests")

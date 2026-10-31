"""Unit tests for honest scoring with non-finite targets (no silent NaN)."""

from __future__ import annotations

import math

import numpy as np
import pytest


def _tiny_fields(n: int = 3) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], np.ndarray]:
    invariants = {f"I{i}": np.full((n,), float(i), dtype=float) for i in range(1, 6)}
    basis = {f"T{i}": np.zeros((n, 3, 3), dtype=float) for i in range(1, 5)}
    target = np.ones((n, 3, 3), dtype=float)
    return invariants, basis, target


def test_excluded_rows_counted_and_ignored() -> None:
    from flowforge.data.frozen_fields import score_expression

    inv, basis, target = _tiny_fields(n=3)
    target[1, 0, 0] = float("nan")
    out = score_expression("0", inv, basis, target)
    assert out["n_excluded"] == 1
    assert out["n_used"] == 2
    assert isinstance(out["n_excluded"], int)
    assert isinstance(out["n_used"], int)
    assert out["mse"] == pytest.approx(1.0)
    assert out["mse_zero"] == pytest.approx(1.0)
    assert out["ratio"] == pytest.approx(1.0)
    assert not math.isnan(float(out["ratio"]))


def test_inf_target_row_excluded() -> None:
    from flowforge.data.frozen_fields import score_expression

    inv, basis, target = _tiny_fields(n=3)
    target[0] = float("inf")
    out = score_expression("0", inv, basis, target)
    assert out["n_excluded"] == 1
    assert out["n_used"] == 2
    assert out["mse"] == pytest.approx(1.0)
    assert out["ratio"] == pytest.approx(1.0)


def test_all_nan_target_raises() -> None:
    from flowforge.data.frozen_fields import score_expression

    inv, basis, target = _tiny_fields(n=3)
    target[:] = float("nan")
    with pytest.raises(ValueError):
        score_expression("0", inv, basis, target)


def test_nonfinite_prediction_gives_inf(monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.data import frozen_fields
    from flowforge.dsl import evaluate

    inv, basis, target = _tiny_fields(n=3)

    def fake_pred(expression: str, invariants: dict, basis_map: dict) -> np.ndarray:
        result = np.zeros_like(target)
        result[0, 0, 0] = float("inf")
        return result

    monkeypatch.setattr(evaluate, "candidate_anisotropy", fake_pred)
    out = frozen_fields.score_expression("0", inv, basis, target)
    assert out["mse"] == float("inf")
    assert out["ratio"] == float("inf")
    assert math.isinf(float(out["mse"]))
    assert math.isinf(float(out["ratio"]))
    assert not math.isnan(float(out["ratio"]))
    assert out["n_used"] == 3
    assert out["n_excluded"] == 0


def test_worst_ratio_ignores_error_cases() -> None:
    from flowforge.data.frozen_fields import worst_ratio

    scores = {
        "good": {"mse": 0.5, "mse_zero": 1.0, "ratio": 0.5, "n_used": 2, "n_excluded": 0},
        "broken": {"error": "missing store"},
        "worse": {"mse": 2.0, "mse_zero": 1.0, "ratio": 2.0, "n_used": 2, "n_excluded": 1},
    }
    assert worst_ratio(scores) == pytest.approx(2.0)


def test_worst_ratio_raises_on_nan() -> None:
    from flowforge.data.frozen_fields import worst_ratio

    scores = {
        "good": {"mse": 1.0, "mse_zero": 1.0, "ratio": 1.0, "n_used": 1, "n_excluded": 0},
        "bad": {"mse": float("nan"), "mse_zero": 1.0, "ratio": float("nan"), "n_used": 1, "n_excluded": 0},
        "broken": {"error": "boom"},
    }
    with pytest.raises(ValueError):
        worst_ratio(scores)


def test_worst_ratio_returns_none_when_empty() -> None:
    from flowforge.data.frozen_fields import worst_ratio

    assert worst_ratio({}) is None
    assert worst_ratio({"a": {"error": "boom"}}) is None
    assert worst_ratio({"a": {"mse": 1.0, "mse_zero": 1.0}}) is None

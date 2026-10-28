"""CH-09 exception honesty: broken env must not look like diverged candidates.

- ``ModuleNotFoundError``/``ImportError`` from an evaluator propagates out
  of every ladder rung (fail loudly); only genuine candidate-evaluation
  errors (e.g. ``ValueError``) become ``DIVERGED_PENALTY``.
- ``read_fields`` never silently returns ``{}``: missing case, missing
  foamlib with no sidecars, and unreadable cases raise / are logged.
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from flowforge.ladder.ladder import (
    DIVERGED_PENALTY,
    rung0,
    rung1_scores,
    rung2_short,
    rung3_full,
    run_ladder,
)
from flowforge.solver.field_io import read_fields


def _fake_evaluate(monkeypatch: pytest.MonkeyPatch, fn) -> None:
    fake = types.ModuleType("flowforge.dsl.evaluate")
    fake.candidate_anisotropy = fn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "flowforge.dsl.evaluate", fake)


def _raise_module_not_found(*args, **kwargs):
    raise ModuleNotFoundError("No module named 'sympy'")


def _raise_value_error(*args, **kwargs):
    raise ValueError("candidate diverged numerically")


# --- ladder: rung 2 (callable evaluator) ------------------------------------


def test_rung2_module_not_found_propagates() -> None:
    with pytest.raises(ModuleNotFoundError):
        rung2_short([{"expression": "I1", "score": 1.0}],
                    short_eval=_raise_module_not_found)


def test_rung2_import_error_propagates() -> None:
    def bad(_expr: str) -> float:
        raise ImportError("broken dependency")

    with pytest.raises(ImportError):
        rung2_short([{"expression": "I1", "score": 1.0}], short_eval=bad)


def test_rung2_value_error_becomes_penalty() -> None:
    result = rung2_short([{"expression": "I1", "score": 1.0}],
                         short_eval=_raise_value_error)
    assert len(result) == 1
    assert result[0]["score"] == DIVERGED_PENALTY
    assert result[0]["score_rung2"] == DIVERGED_PENALTY
    assert "diverged" in result[0]["error_rung2"]


def test_rung2_genuine_score_still_used() -> None:
    result = rung2_short([{"expression": "I1", "score": 9.0}],
                         short_eval=lambda _e: 0.25)
    assert result[0]["score"] == 0.25


# --- ladder: rung 0 / 1 / 3 (stubbed DSL evaluator) -------------------------


def test_rung0_module_not_found_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("flowforge.dsl.parser")
    fake.validate_candidate = _raise_module_not_found  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "flowforge.dsl.parser", fake)
    with pytest.raises(ModuleNotFoundError):
        rung0("I1")


def test_rung0_invalid_candidate_still_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("flowforge.dsl.parser")
    fake.validate_candidate = _raise_value_error  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "flowforge.dsl.parser", fake)
    assert rung0("not a candidate") is False


def test_rung1_module_not_found_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_evaluate(monkeypatch, _raise_module_not_found)
    target = np.zeros((2, 3, 3))
    with pytest.raises(ModuleNotFoundError):
        rung1_scores(["I1"], {}, {}, target)


def test_rung1_value_error_becomes_penalty(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_evaluate(monkeypatch, _raise_value_error)
    target = np.zeros((2, 3, 3))
    result = rung1_scores(["I1"], {}, {}, target)
    assert result[0]["score"] == DIVERGED_PENALTY
    assert "diverged" in result[0]["error"]


def test_rung3_module_not_found_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_evaluate(monkeypatch, _raise_module_not_found)
    target = np.zeros((2, 3, 3))
    with pytest.raises(ModuleNotFoundError):
        rung3_full([{"expression": "I1", "score": 1.0}], {}, {}, target)


def test_rung3_value_error_is_rejected_not_scored(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_evaluate(monkeypatch, _raise_value_error)
    target = np.zeros((2, 3, 3))
    # Genuine candidate failure: rejected (empty result), not an exception.
    assert rung3_full([{"expression": "I1", "score": 1.0}], {}, {}, target) == []


def test_run_ladder_propagates_module_not_found_from_rung2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_parser = types.ModuleType("flowforge.dsl.parser")
    fake_parser.validate_candidate = lambda _e: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "flowforge.dsl.parser", fake_parser)
    _fake_evaluate(monkeypatch, lambda *a, **k: np.zeros((2, 3, 3)))
    target = np.zeros((2, 3, 3))
    with pytest.raises(ModuleNotFoundError):
        run_ladder(["I1"], {}, {}, target, short_eval=_raise_module_not_found)


# --- field_io ---------------------------------------------------------------


def test_read_fields_nonexistent_case_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_fields(tmp_path / "does-not-exist")


def test_read_fields_missing_foamlib_no_sidecars_raises_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setitem(sys.modules, "foamlib", None)
    with caplog.at_level(logging.ERROR, logger="flowforge.solver.field_io"):
        with pytest.raises(ImportError):
            read_fields(tmp_path)
    assert any(
        "foamlib" in rec.message and ("ImportError" in rec.message
                                       or "ModuleNotFoundError" in rec.message)
        for rec in caplog.records
    )


def test_read_fields_sidecar_fallback_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "foamlib", None)
    np.save(tmp_path / "U.npy", np.ones((2, 3)))
    fields = read_fields(tmp_path)
    assert set(fields) == {"U"}
    assert np.allclose(fields["U"], np.ones((2, 3)))


def test_read_fields_empty_case_does_not_pretend_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "foamlib", None)
    with pytest.raises((ImportError, RuntimeError)):
        read_fields(tmp_path)

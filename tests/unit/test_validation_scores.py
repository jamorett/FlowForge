"""Unit tests for a priori validation (generalization) scores."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


def _make_arrays(n: int, fill: float = 0.0) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {"coordinates": np.zeros((n, 3), dtype=np.float64)}
    for i in range(1, 6):
        arrays[f"invariants/I{i}"] = np.full((n,), fill + float(i), dtype=np.float64)
    for i in range(1, 5):
        arrays[f"tensor_basis/T{i}"] = np.full((n, 3, 3), fill, dtype=np.float64)
    arrays["targets/a_delta"] = np.full((n, 3, 3), fill + 10.0, dtype=np.float64)
    arrays["targets/Pk_delta"] = np.full((n,), fill, dtype=np.float64)
    return arrays


def _write(proc: Path, case_id: str, arrays: dict[str, np.ndarray]) -> Path:
    from flowforge.data.zarr_store import write_case

    path = proc / case_id
    write_case(path, arrays)
    return path


def test_validation_case_ids_matches_config() -> None:
    from flowforge.config import load_cases
    from flowforge.data.frozen_fields import validation_case_ids

    expected = [e["id"] for e in load_cases()["cases"] if e["split"] == "validation"]
    assert validation_case_ids() == expected
    assert expected, "expected at least one validation case"


def test_score_expression_zero_gives_ratio_one() -> None:
    from flowforge.data.frozen_fields import score_expression
    from flowforge.orchestrator.round import synthetic_fields

    inv, basis, target = synthetic_fields(n=8)
    out = score_expression("0", inv, basis, target)
    assert set(out) == {"mse", "mse_zero", "ratio", "n_used", "n_excluded"}
    assert all(isinstance(out[k], float) for k in ("mse", "mse_zero", "ratio"))
    assert out["n_used"] == 8
    assert out["n_excluded"] == 0
    expected_zero = float(np.mean(np.asarray(target, dtype=float) ** 2))
    assert out["mse_zero"] == pytest.approx(expected_zero)
    assert out["mse"] == pytest.approx(expected_zero)
    assert out["ratio"] == pytest.approx(1.0)


def test_score_expression_ratio_definition() -> None:
    from flowforge.data.frozen_fields import score_expression
    from flowforge.orchestrator.round import synthetic_fields

    inv, basis, target = synthetic_fields(n=8, seed=7)
    out = score_expression("0.5", inv, basis, target)
    assert out["mse"] >= 0.0
    assert out["mse_zero"] > 0.0
    assert out["ratio"] == pytest.approx(out["mse"] / out["mse_zero"])


def test_score_on_cases_per_case(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import score_on_cases

    proc = tmp_path / "processed"
    _write(proc, "case_a", _make_arrays(4, fill=0.0))
    _write(proc, "case_b", _make_arrays(3, fill=100.0))
    scores = score_on_cases("0", ["case_a", "case_b"], processed_dir=proc)
    assert set(scores) == {"case_a", "case_b"}
    for payload in scores.values():
        assert set(payload) == {"mse", "mse_zero", "ratio", "n_used", "n_excluded"}
        assert payload["ratio"] == pytest.approx(1.0)
    # Targets are 10.0 and 110.0 so per-case MSE differs.
    assert scores["case_a"]["mse"] == pytest.approx(100.0)
    assert scores["case_b"]["mse"] == pytest.approx(12100.0)
    assert scores["case_a"]["mse_zero"] == pytest.approx(100.0)
    assert scores["case_b"]["mse_zero"] == pytest.approx(12100.0)


def test_score_on_cases_missing_yields_error(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import score_on_cases

    proc = tmp_path / "processed"
    _write(proc, "case_a", _make_arrays(2, fill=1.0))
    scores = score_on_cases("0", ["case_a", "ghost_case"], processed_dir=proc)
    assert set(scores["case_a"]) == {"mse", "mse_zero", "ratio", "n_used", "n_excluded"}
    assert "error" in scores["ghost_case"]
    assert "ghost_case" in scores["ghost_case"]["error"]


def test_score_on_cases_bad_expression_yields_error(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import score_on_cases

    proc = tmp_path / "processed"
    _write(proc, "case_a", _make_arrays(2, fill=0.0))
    scores = score_on_cases("bogus_fn(I1)", ["case_a"], processed_dir=proc)
    assert "error" in scores["case_a"]
    assert isinstance(scores["case_a"]["error"], str)
    assert scores["case_a"]["error"].strip() != ""


def test_score_on_cases_permission_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.data import frozen_fields

    def boom(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        raise PermissionError("locked")

    monkeypatch.setattr(frozen_fields, "load_frozen_fields", boom)
    with pytest.raises(PermissionError):
        frozen_fields.score_on_cases("0", ["any_case"], processed_dir="data/processed")


def test_champion_prefers_validation_over_train(monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.data import frozen_fields
    from flowforge.orchestrator.round import select_champion_by_validation

    def fake_ids(root=None) -> list[str]:
        return ["val_a"]

    def fake_scores(expression, case_ids, processed_dir="data/processed",
                    max_points_per_case=None, seed=0):
        # "0.9" wins on train (score 0.1) but loses on validation.
        ratio = 2.0 if expression == "0.9" else 0.5
        return {cid: {"mse": ratio, "mse_zero": 1.0, "ratio": ratio,
                      "n_used": 8, "n_excluded": 0} for cid in case_ids}

    monkeypatch.setattr(frozen_fields, "validation_case_ids", fake_ids)
    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_scores)
    champ = select_champion_by_validation([
        {"expression": "0.9", "score": 0.1},
        {"expression": "0.5", "score": 0.9},
    ])
    assert champ is not None
    assert champ["expression"] == "0.5"
    assert champ["worst_error"] == pytest.approx(0.5)
    assert champ["selection_metric"] == "worst_validation_ratio"
    assert champ["dl"] > 0


def test_champion_all_validation_errors_still_picks(monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.data import frozen_fields
    from flowforge.orchestrator.round import select_champion_by_validation

    def fake_ids(root=None) -> list[str]:
        return ["val_a"]

    def fake_scores(expression, case_ids, **kwargs):
        return {cid: {"error": "boom"} for cid in case_ids}

    monkeypatch.setattr(frozen_fields, "validation_case_ids", fake_ids)
    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_scores)
    champ = select_champion_by_validation([
        {"expression": "0.5 * I1 + 0.25 * I2", "score": 0.1},
        {"expression": "0.5", "score": 0.9},
    ])
    assert champ is not None
    assert champ["worst_error"] == float("inf")
    # All unscored: falls back to simplest (min DL), never crashes.
    assert champ["expression"] == "0.5"


def test_select_champion_empty_pool() -> None:
    from flowforge.orchestrator.round import select_champion_by_validation
    assert select_champion_by_validation([]) is None


def test_live_champion_gets_validation_scores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.orchestrator.round import run_round, synthetic_fields

    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)

    def fake_train_ids(root=None) -> list[str]:
        return ["train_stub"]

    def fake_validation_ids(root=None) -> list[str]:
        return ["val_a", "val_b"]

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        return inv0, basis0, target0

    monkeypatch.setattr(frozen_fields, "train_case_ids", fake_train_ids)
    monkeypatch.setattr(frozen_fields, "validation_case_ids", fake_validation_ids)
    monkeypatch.setattr(frozen_fields, "load_frozen_fields", fake_load)

    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload: dict):
                self.payload = dict(payload)

            def model_dump(self) -> dict:
                return dict(self.payload)

        if role == "board":
            return Res({"mechanisms": []})
        if role == "theorist":
            return Res({"expressions": ["0.5"], "mechanisms": [], "risk_audit": "fake"})
        if role == "coder":
            return Res({"constants": [], "apriori_mse": 0.0})
        if role == "analyst":
            return Res({"failure_regions": [], "next_hypothesis": "fake"})
        if role == "skeptic":
            return Res({"objections": [], "requested_tests": []})
        if role == "redteam":
            return Res({"flows": []})
        if role == "composer":
            return Res({"modules": ["0.5"], "gates": []})
        return Res({})

    monkeypatch.setattr(dispatcher, "dispatch_role", fake_dispatch)

    session_dir = tmp_path / "sess"
    result = run_round(1, mock=False, session_dir=session_dir)
    assert result["status"] == "ok"
    champion = result["champion"]
    assert champion is not None
    assert champion["validation_mode"] == "frozen"
    assert set(champion["train"]) == {"mse", "mse_zero", "ratio", "n_used", "n_excluded"}
    assert set(champion["validation"]) == {"val_a", "val_b"}
    for payload in champion["validation"].values():
        assert set(payload) == {"mse", "mse_zero", "ratio", "n_used", "n_excluded"}
    ratios = [payload["ratio"] for payload in champion["validation"].values()]
    assert champion["worst_validation_ratio"] == pytest.approx(max(ratios))
    events_path = Path(result["events_path"])
    assert events_path.is_file()
    text = events_path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in text.splitlines() if line.strip()]
    champ_events = [e for e in events if e.get("type") == "champion"]
    assert champ_events, "missing champion event"
    logged = champ_events[-1]["champion"]
    assert logged["validation_mode"] == "frozen"
    assert logged["train"] == pytest.approx(champion["train"])
    assert set(logged["validation"]) == {"val_a", "val_b"}
    assert logged["worst_validation_ratio"] == pytest.approx(champion["worst_validation_ratio"])

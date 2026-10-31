"""Unit tests for curated literature cards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

EXPECTED_IDS = ["cls1996", "pope1975", "sdc2020", "ss1997", "wj2000", "ws2016"]


def test_shipped_cards_validate() -> None:
    from flowforge.dsl.parser import validate_candidate
    from flowforge.literature.library_cards import load_literature_cards

    cards = load_literature_cards()
    assert [card["id"] for card in cards] == EXPECTED_IDS
    for card in cards:
        assert card["fidelity"] == "approximate"
        assert card["verified_by_human"] is False
        assert isinstance(card["dsl_expression"], str)
        validate_candidate(card["dsl_expression"])


def test_loader_skips_bad_card(tmp_path: Path) -> None:
    from flowforge.literature.library_cards import load_literature_cards

    good = {
        "id": "good",
        "reference": "good ref",
        "doi": "10.1/good",
        "model_form": "good form",
        "dsl_expression": "0.09 * T1",
        "fidelity": "approximate",
        "mechanism": "linear_eddy_viscosity",
        "verified_by_human": False,
    }
    (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")
    bad_expr = dict(good)
    bad_expr["id"] = "bad_expr"
    bad_expr["dsl_expression"] = "C1 * T1"
    (tmp_path / "bad_expr.json").write_text(json.dumps(bad_expr), encoding="utf-8")
    cards = load_literature_cards(directory=tmp_path)
    assert [card["id"] for card in cards] == ["good"]


def test_theorist_context_contains_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.literature.library_cards import load_literature_cards
    from flowforge.orchestrator.round import run_round, synthetic_fields

    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)

    def fake_train_ids(root=None) -> list[str]:
        return ["train_stub"]

    def fake_validation_ids(root=None) -> list[str]:
        return ["val_stub"]

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0, **kwargs):
        return inv0, basis0, target0

    monkeypatch.setattr(frozen_fields, "train_case_ids", fake_train_ids)
    monkeypatch.setattr(frozen_fields, "validation_case_ids", fake_validation_ids)
    monkeypatch.setattr(frozen_fields, "load_frozen_fields", fake_load)

    captured: dict = {}

    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload: dict):
                self.payload = dict(payload)

            def model_dump(self) -> dict:
                return dict(self.payload)

        if role == "theorist":
            captured["literature_cards"] = list(context.get("literature_cards", []))
            return Res({"expressions": ["0.1 * T1"], "mechanisms": [], "risk_audit": "fake"})
        if role == "board":
            return Res({"mechanisms": []})
        if role == "coder":
            return Res({"constants": [], "apriori_mse": 0.0})
        if role == "analyst":
            return Res({"failure_regions": [], "next_hypothesis": "fake"})
        if role == "skeptic":
            return Res({"objections": [], "requested_tests": []})
        if role == "redteam":
            return Res({"flows": []})
        if role == "composer":
            return Res({"modules": ["0.1 * T1"], "gates": []})
        return Res({})

    monkeypatch.setattr(dispatcher, "dispatch_role", fake_dispatch)

    result = run_round(1, mock=False, session_dir=tmp_path / "sess")
    assert result["status"] == "ok"
    assert "literature_cards" in captured
    expected = [
        {
            "id": card["id"],
            "reference": card["reference"],
            "dsl_expression": card["dsl_expression"],
            "mechanism": card["mechanism"],
        }
        for card in load_literature_cards()
    ]
    assert captured["literature_cards"] == expected
    assert [entry["id"] for entry in captured["literature_cards"]] == EXPECTED_IDS

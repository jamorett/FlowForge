"""Red-team split: probe set never contains validation cases (Task 17)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_redteam_split_disjoint_from_validation_and_train() -> None:
    from flowforge.data.frozen_fields import (
        redteam_case_ids,
        train_case_ids,
        validation_case_ids,
    )

    red = set(redteam_case_ids())
    val = set(validation_case_ids())
    train = set(train_case_ids())
    assert "converging_diverging_channel" in red
    assert "converging_diverging_channel" not in val
    assert red.isdisjoint(val)
    assert red.isdisjoint(train)
    assert val.isdisjoint(train)


def test_probe_set_uses_redteam_not_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.orchestrator import round as round_mod
    from flowforge.orchestrator.round import run_round, synthetic_fields

    monkeypatch.setattr(round_mod, "ATTACKS_DIR", tmp_path / "attacks")
    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)

    monkeypatch.setattr(frozen_fields, "train_case_ids", lambda root=None: ["train_stub"])
    monkeypatch.setattr(frozen_fields, "validation_case_ids", lambda root=None: ["val_a"])
    monkeypatch.setattr(frozen_fields, "redteam_case_ids", lambda root=None: ["rt_a"])
    monkeypatch.setattr(
        frozen_fields, "load_frozen_fields",
        lambda case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0: (inv0, basis0, target0),
    )
    monkeypatch.setattr(frozen_fields, "attack_case_for", lambda spec: None)

    calls: list[list[str]] = []

    def fake_score_cases(expression, case_ids, processed_dir="data/processed",
                         max_points_per_case=None, seed=0):
        calls.append(list(case_ids))
        return {cid: {"mse": 0.5, "mse_zero": 1.0, "ratio": 0.5,
                      "n_used": 8, "n_excluded": 0} for cid in case_ids}

    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_score_cases)

    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload):
                self.payload = dict(payload)

            def model_dump(self):
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
            # No attack flows available; probe set must still be redteam-only.
            return Res({"flows": []})
        if role == "composer":
            return Res({"modules": ["0.5"], "gates": []})
        return Res({})

    monkeypatch.setattr(dispatcher, "dispatch_role", fake_dispatch)

    session_dir = tmp_path / "sess"
    result = run_round(1, mock=False, session_dir=session_dir)
    assert result["status"] == "ok"
    events = [json.loads(line) for line in (session_dir / "events.jsonl").read_text().splitlines() if line.strip()]
    rt = [e for e in events if e.get("type") == "redteam"]
    assert len(rt) == 1
    assert rt[0]["probe_cases"] == ["rt_a"]
    assert "val_a" not in rt[0]["probe_cases"]
    # The screen scored the redteam flow; validation was never probed there.
    assert any(set(call) == {"rt_a"} for call in calls)
    assert not any(set(call) == {"val_a", "rt_a"} for call in calls)


def test_locked_case_under_redteam_raises(tmp_path: Path) -> None:
    from flowforge.config import load_cases

    text = """cases:
  - id: square_duct
    split: redteam
    source: x
  - id: nasa_wall_mounted_hump
    split: locked
    source: y
"""
    path = tmp_path / "cases.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)

"""Redteam split probe separation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_real_config_redteam_split() -> None:
    from flowforge.data.frozen_fields import redteam_case_ids, train_case_ids, validation_case_ids

    rt = redteam_case_ids()
    va = validation_case_ids()
    tr = train_case_ids()
    assert "converging_diverging_channel" in rt
    assert "converging_diverging_channel" not in va
    assert set(rt).isdisjoint(set(va))
    assert set(rt).isdisjoint(set(tr))
    assert set(va).isdisjoint(set(tr))


def _fake_dispatch_factory(exprs):
    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload: dict):
                self.payload = dict(payload)

            def model_dump(self) -> dict:
                return dict(self.payload)

        if role == "board":
            return Res({"mechanisms": []})
        if role == "theorist":
            return Res({"expressions": list(exprs), "mechanisms": [], "risk_audit": "fake"})
        if role == "coder":
            return Res({"constants": [], "apriori_mse": 0.0})
        if role == "analyst":
            return Res({"failure_regions": [], "next_hypothesis": "fake"})
        if role == "skeptic":
            return Res({"objections": [], "requested_tests": []})
        if role == "redteam":
            return Res({"flows": [{"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}]})
        if role == "composer":
            return Res({"modules": list(exprs), "gates": []})
        return Res({})

    return fake_dispatch


def test_probe_uses_redteam_not_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.orchestrator import round as round_mod
    from flowforge.orchestrator.round import run_round, synthetic_fields

    monkeypatch.setattr(round_mod, "ATTACKS_DIR", tmp_path / "attacks")
    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)
    monkeypatch.setattr(frozen_fields, "train_case_ids", lambda root=None: ["train_stub"])
    monkeypatch.setattr(frozen_fields, "validation_case_ids", lambda root=None: ["val_a"])
    monkeypatch.setattr(frozen_fields, "redteam_case_ids", lambda root=None: ["rt_a"])
    monkeypatch.setattr(frozen_fields, "load_frozen_fields", lambda c, processed_dir="data/processed", max_points_per_case=None, seed=0: (inv0, basis0, target0))
    monkeypatch.setattr(frozen_fields, "attack_case_for", lambda spec, processed_dir="data/processed": "attack_a")
    seen: list[list[str]] = []

    def fake_score(expression, case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        ids = list(case_ids)
        seen.append(ids)
        if "val_a" in ids:
            assert ids == ["val_a"]
        return {cid: {"mse": 0.5, "mse_zero": 1.0, "ratio": 0.5, "n_used": 8, "n_excluded": 0} for cid in ids}

    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_score)
    monkeypatch.setattr(dispatcher, "dispatch_role", _fake_dispatch_factory(["0.5"]))
    session_dir = tmp_path / "sess"
    result = run_round(1, mock=False, session_dir=session_dir)
    assert result["status"] == "ok"
    probe_calls = [ids for ids in seen if "rt_a" in ids or "attack_a" in ids]
    assert probe_calls
    for ids in probe_calls:
        assert "val_a" not in ids
    assert any("rt_a" in ids for ids in seen)
    events = [json.loads(line) for line in (session_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rt = [e for e in events if e.get("type") == "redteam"]
    assert len(rt) == 1
    assert "rt_a" in rt[0]["probe_cases"]
    assert "val_a" not in rt[0]["probe_cases"]


def test_locked_case_cannot_move_to_redteam(tmp_path: Path) -> None:
    from flowforge.config import load_cases

    p = tmp_path / "cases.yaml"
    p.write_text("cases:\n  - id: periodic_hill_re5600\n    split: train\n    source: curated\n  - id: curved_step\n    split: validation\n    source: curated\n  - id: converging_diverging_channel\n    split: redteam\n    source: curated\n  - id: square_duct\n    split: redteam\n    source: closure_challenge\n  - id: nasa_wall_mounted_hump\n    split: locked\n    source: closure_challenge\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(p)

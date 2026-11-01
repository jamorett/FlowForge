"""Red-team rung-1 screen: weak candidates are excluded before rung 2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _fake_dispatch_factory(theorist_exprs):
    from flowforge.agents import dispatcher

    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload: dict):
                self.payload = dict(payload)

            def model_dump(self) -> dict:
                return dict(self.payload)

        if role == "board":
            return Res({"mechanisms": []})
        if role == "theorist":
            return Res({"expressions": list(theorist_exprs), "mechanisms": [], "risk_audit": "fake"})
        if role == "coder":
            return Res({"constants": [], "apriori_mse": 0.0})
        if role == "analyst":
            return Res({"failure_regions": [], "next_hypothesis": "fake"})
        if role == "skeptic":
            return Res({"objections": [], "requested_tests": []})
        if role == "redteam":
            return Res({"flows": [{"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}]})
        if role == "composer":
            return Res({"modules": list(theorist_exprs), "gates": []})
        return Res({})

    return fake_dispatch


def test_redteam_excludes_broken_rung1_survivor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.orchestrator import round as round_mod
    from flowforge.orchestrator.round import run_round, synthetic_fields

    # Never touch the real attack library with fake breaks.
    monkeypatch.setattr(round_mod, "ATTACKS_DIR", tmp_path / "attacks")
    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)

    def fake_train_ids(root=None) -> list[str]:
        return ["train_stub"]

    def fake_validation_ids(root=None) -> list[str]:
        return ["val_a", "val_b"]

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        return inv0, basis0, target0

    def fake_attack_case_for(spec):
        return "val_a"

    def fake_score_cases(expression, case_ids, processed_dir="data/processed",
                         max_points_per_case=None, seed=0):
        # Mechanism test: "0.5 * T1" is a fitted rung-1 survivor here;
        # the fake attack collapses it off-training (ratio > 1 = broken).
        # Physical separation of weak vs strong forms on real stores was
        # verified separately (probe_break: 2*T2 -> 1.63, div-form -> 0.77).
        ratio = 2.0 if expression == "0.5 * T1" else 0.5
        return {cid: {"mse": ratio, "mse_zero": 1.0, "ratio": ratio,
                      "n_used": 8, "n_excluded": 0} for cid in case_ids}

    monkeypatch.setattr(frozen_fields, "train_case_ids", fake_train_ids)
    monkeypatch.setattr(frozen_fields, "validation_case_ids", fake_validation_ids)
    monkeypatch.setattr(frozen_fields, "load_frozen_fields", fake_load)
    monkeypatch.setattr(frozen_fields, "attack_case_for", fake_attack_case_for)
    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_score_cases)
    monkeypatch.setattr(dispatcher, "dispatch_role",
                        _fake_dispatch_factory(["0.5", "0.5 * T1", "2 * T2", "5 * T3"]))

    session_dir = tmp_path / "sess"
    result = run_round(1, mock=False, session_dir=session_dir)
    assert result["status"] == "ok"
    assert "0.5 * T1" in result["redteam_excluded"]
    assert all(s.get("expression") != "0.5 * T1" for s in result["final_rung3"])
    assert result["champion"] is not None
    assert result["champion"]["expression"] == "0.5"

    events = [json.loads(line) for line in (session_dir / "events.jsonl").read_text().splitlines() if line.strip()]
    rt = [e for e in events if e.get("type") == "redteam"]
    assert len(rt) == 1
    assert rt[0]["n_broken"] >= 1
    assert "0.5 * T1" in rt[0]["excluded"]
    assert rt[0]["pool"] == "rung1"
    order = [e.get("type") for e in events]
    assert order.index("redteam") < order.index("rung2")


def test_redteam_ablation_skips_exclusion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.agents import dispatcher
    from flowforge.data import frozen_fields
    from flowforge.orchestrator import round as round_mod
    from flowforge.orchestrator.round import run_round, synthetic_fields

    monkeypatch.setattr(round_mod, "ATTACKS_DIR", tmp_path / "attacks")
    inv0, basis0, target0 = synthetic_fields(n=8, seed=123)

    def fake_train_ids(root=None) -> list[str]:
        return ["train_stub"]

    def fake_validation_ids(root=None) -> list[str]:
        return ["val_a", "val_b"]

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        return inv0, basis0, target0

    def fake_score_cases(expression, case_ids, processed_dir="data/processed",
                         max_points_per_case=None, seed=0):
        return {cid: {"mse": 0.5, "mse_zero": 1.0, "ratio": 0.5,
                      "n_used": 8, "n_excluded": 0} for cid in case_ids}

    monkeypatch.setattr(frozen_fields, "train_case_ids", fake_train_ids)
    monkeypatch.setattr(frozen_fields, "validation_case_ids", fake_validation_ids)
    monkeypatch.setattr(frozen_fields, "load_frozen_fields", fake_load)
    monkeypatch.setattr(frozen_fields, "score_on_cases", fake_score_cases)
    monkeypatch.setattr(dispatcher, "dispatch_role",
                        _fake_dispatch_factory(["0.5", "0.5 * T1", "2 * T2", "5 * T3"]))

    session_dir = tmp_path / "sess"
    result = run_round(1, mock=False, session_dir=session_dir, redteam=False)
    assert result["redteam_excluded"] == []
    events = [json.loads(line) for line in (session_dir / "events.jsonl").read_text().splitlines() if line.strip()]
    rt = [e for e in events if e.get("type") == "redteam"]
    assert len(rt) == 1 and rt[0].get("skipped") is True

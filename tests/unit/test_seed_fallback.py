"""Seed fallback tests (no API, no data/processed)."""
from __future__ import annotations

import json


def test_last_round_empty_falls_back_to_best_train(tmp_path, monkeypatch) -> None:
    from flowforge.baselines import sparse as sparse_module
    from flowforge.orchestrator import round as round_module
    from scripts import run_arms

    def fake_run_round(round_no, mock=False, groups=1, session=None, redteam=True, **kwargs):
        number = int(round_no)
        if number == 1:
            champion = {
                "expression": "T1",
                "worst_validation_ratio": 0.5,
                "train": {"ratio": 0.2},
            }
            return {"status": "ok", "champion": champion, "dollars_spent": 1.0, "round": number}
        if number == 2:
            champion = {
                "expression": "T2",
                "worst_validation_ratio": 0.1,
                "train_ratio": 0.8,
            }
            return {"status": "ok", "champion": champion, "dollars_spent": 1.0, "round": number}
        return {"status": "ok", "champion": None, "dollars_spent": 0.5, "round": number}

    def fake_baseline(seed=42, **kwargs):
        return {"expression": "I1", "worst_validation_ratio": 0.9}

    monkeypatch.setattr(round_module, "run_round", fake_run_round)
    monkeypatch.setattr(sparse_module, "evaluate_sparse_baseline", fake_baseline)

    out_path = tmp_path / "arms.json"
    output = run_arms.main([
        "--dry-run", "--rounds", "3", "--groups", "1",
        "--budget-usd", "100.0", "--out", str(out_path),
    ])
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    for arm in ("swarm", "swarm_no_redteam"):
        info = payload["arms"][arm]
        assert info["complete"] is True
        assert len(info["seeds"]) == 3
        for row in info["seeds"]:
            assert row["metric"] == 0.5
            assert row["expression"] == "T1"
            assert row["champion"] == "T1"
            assert row["champion_round"] == 1
            assert row["fallback"] is True
        assert info["summary"] is not None
        assert info["summary"]["mean"] == 0.5
    assert output is not None
    assert output["arms"]["swarm"]["complete"] is True


def test_all_rounds_empty_keeps_none_and_incomplete(tmp_path, monkeypatch) -> None:
    from flowforge.baselines import sparse as sparse_module
    from flowforge.orchestrator import round as round_module
    from scripts import run_arms

    def fake_run_round(round_no, mock=False, groups=1, session=None, redteam=True, **kwargs):
        return {"status": "ok", "champion": None, "dollars_spent": 0.5, "round": int(round_no)}

    def fake_baseline(seed=42, **kwargs):
        return {"expression": "I1", "worst_validation_ratio": 0.9}

    monkeypatch.setattr(round_module, "run_round", fake_run_round)
    monkeypatch.setattr(sparse_module, "evaluate_sparse_baseline", fake_baseline)

    out_path = tmp_path / "arms.json"
    output = run_arms.main([
        "--dry-run", "--rounds", "3", "--groups", "1",
        "--budget-usd", "100.0", "--out", str(out_path),
    ])
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    for arm in ("swarm", "swarm_no_redteam"):
        info = payload["arms"][arm]
        assert info["complete"] is False
        assert info["summary"] is None
        assert len(info["seeds"]) == 3
        for row in info["seeds"]:
            assert row["metric"] is None
            assert row["champion_round"] is None
            assert row["fallback"] is False
    assert output is not None
    assert output["arms"]["swarm"]["complete"] is False

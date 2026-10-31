"""Runner infrastructure tests (no API, no data/processed)."""
from __future__ import annotations

import json


def test_mock_redteam_skipped(tmp_path) -> None:
    from flowforge.orchestrator.round import run_round

    session_dir = tmp_path / "mock-nort"
    run_round(1, mock=True, session_dir=str(session_dir), redteam=False)
    events = [json.loads(line) for line in (session_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    red = [entry for entry in events if entry.get("step") == "redteam"]
    assert len(red) == 1
    assert red[0].get("skipped") is True


def test_live_redteam_false_skips_dispatch(tmp_path, monkeypatch) -> None:
    import numpy as np

    from flowforge.agents import dispatcher as dispatcher_module
    from flowforge.data import frozen_fields as frozen_module
    from flowforge.orchestrator import round as round_module

    calls: list[str] = []

    def fake_dispatch(role, runtime=None, context=None, **kwargs):
        calls.append(str(role))
        from flowforge.agents.dispatcher import dispatch_role_mock

        active = context if isinstance(context, dict) else {}
        if isinstance(runtime, dict) and not isinstance(context, dict):
            active = runtime
        return dispatch_role_mock(role, active)

    monkeypatch.setattr(dispatcher_module, "dispatch_role", fake_dispatch)

    def fake_train_ids(root=None):
        return ["case_a"]

    def fake_valid_ids(root=None):
        return ["case_b"]

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        ids = list(case_ids)
        if ids == ["case_a"]:
            inv = {f"I{i}": np.zeros(4) for i in (1, 2, 3, 4, 5)}
            basis = {f"T{i}": np.zeros((4, 3, 3)) for i in (1, 2, 3, 4)}
            target = np.zeros((4, 3, 3))
            return inv, basis, target
        inv = {f"I{i}": np.zeros(2) for i in (1, 2, 3, 4, 5)}
        basis = {f"T{i}": np.zeros((2, 3, 3)) for i in (1, 2, 3, 4)}
        target = np.zeros((2, 3, 3))
        return inv, basis, target

    def fake_score(expression, inv, basis, target):
        return {"mse": 0.1, "mse_zero": 1.0, "ratio": 0.1}

    def fake_score_cases(expression, case_ids, processed_dir="data/processed", max_points_per_case=4000, seed=0):
        return {cid: {"mse": 0.1, "mse_zero": 1.0, "ratio": 0.5} for cid in list(case_ids)}

    monkeypatch.setattr(frozen_module, "train_case_ids", fake_train_ids)
    monkeypatch.setattr(frozen_module, "validation_case_ids", fake_valid_ids)
    monkeypatch.setattr(frozen_module, "load_frozen_fields", fake_load)
    monkeypatch.setattr(frozen_module, "score_expression", fake_score)
    monkeypatch.setattr(frozen_module, "score_on_cases", fake_score_cases)

    session_dir = tmp_path / "live-nort"
    result = round_module.run_round(1, mock=False, session_dir=str(session_dir), groups=1, redteam=False)
    assert result["status"] in ("ok", "all_rejected", "error")
    assert "redteam" not in calls
    events = [json.loads(line) for line in (session_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    red = [entry for entry in events if entry.get("step") == "redteam"]
    assert len(red) == 1
    assert red[0].get("skipped") is True


def test_runner_dry_run_shape_and_budget(tmp_path, monkeypatch, capsys) -> None:
    from flowforge.baselines import sparse as sparse_module
    from flowforge.orchestrator import round as round_module
    from scripts import run_arms

    seen: list[tuple] = []

    def fake_run_round(round_no, mock=False, groups=1, session=None, redteam=True, **kwargs):
        seen.append((round_no, session, redteam))
        assert mock is False
        champion = {"expression": "I1", "worst_validation_ratio": 0.4 + 0.01 * float(round_no)}
        return {"status": "ok", "champion": champion, "dollars_spent": 1.0, "round": round_no}

    def fake_baseline(seed=42, **kwargs):
        return {"expression": "I1", "worst_validation_ratio": 0.9}

    monkeypatch.setattr(round_module, "run_round", fake_run_round)
    monkeypatch.setattr(sparse_module, "evaluate_sparse_baseline", fake_baseline)

    out_path = tmp_path / "arms.json"
    output = run_arms.main(["--dry-run", "--rounds", "2", "--groups", "1", "--budget-usd", "10.0", "--out", str(out_path)])
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "frozen"
    assert payload["metric"] == "worst_validation_ratio (lower is better)"
    assert payload["dry_run"] is True
    assert payload["incomplete"] is True
    assert set(payload["arms"].keys()) == {"swarm", "swarm_no_redteam", "sparse_baseline"}
    for arm in ("swarm", "swarm_no_redteam", "sparse_baseline"):
        info = payload["arms"][arm]
        assert len(info["seeds"]) == 3
        for row in info["seeds"]:
            assert "metric" in row
            assert ("expression" in row) or ("champion" in row)
            assert "session" in row
            assert ("cost" in row) or ("cost_usd" in row) or ("dollars_spent" in row)
    # Budget stopped further dispatches: full run would need 2 arms * 3 seeds * 2 rounds = 12 calls.
    assert len(seen) < 12
    # Ablation arm must disable redteam.
    ablation = [entry for entry in seen if entry[1] is not None and "swarm_no_redteam" in str(entry[1])]
    assert ablation
    assert all(entry[2] is False for entry in ablation)
    swarm_calls = [entry for entry in seen if entry[1] is not None and "arms-swarm-s" in str(entry[1])]
    assert swarm_calls
    assert all(entry[2] is True for entry in swarm_calls)
    assert output["incomplete"] is True
    text = capsys.readouterr().out
    assert "swarm" in text

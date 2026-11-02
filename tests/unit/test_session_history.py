"""Unit tests for session history (Theorist learns from previous rounds)."""

from __future__ import annotations

import json
from pathlib import Path


def read_events(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    from flowforge.orchestrator.history import session_history

    out = session_history(tmp_path / "nope" / "events.jsonl")
    assert out["rounds_seen"] == 0
    assert out["best_candidates"] == []
    assert out["champions"] == []
    assert out["broken"] == []
    assert out["hints"] == []


def test_empty_file_returns_empty(tmp_path: Path) -> None:
    from flowforge.orchestrator.history import session_history

    path = tmp_path / "events.jsonl"
    path.write_text("", encoding="utf-8")
    out = session_history(path)
    assert out["rounds_seen"] == 0
    assert out["best_candidates"] == []
    assert out["champions"] == []
    assert out["broken"] == []
    assert out["hints"] == []


def test_malformed_lines_skipped(tmp_path: Path) -> None:
    from flowforge.orchestrator.history import session_history

    path = tmp_path / "events.jsonl"
    good_fit = {
        "type": "fit", "step": "fit", "round": 1,
        "fits": [{"expression": "-3.1 * T2", "mse_after": 0.64, "mse_before": 1.0}],
    }
    with path.open("w", encoding="utf-8") as fh:
        fh.write("not json at all\n")
        fh.write(json.dumps(good_fit) + "\n")
        fh.write("{\"incomplete\": \n")
        fh.write("\n")
        fh.write("[1, 2, 3]\n")
        fh.write("42\n")
    out = session_history(path)
    assert out["rounds_seen"] == 0
    assert len(out["best_candidates"]) == 1
    assert out["best_candidates"][0]["expression"] == "-3.1 * T2"
    assert out["best_candidates"][0]["mse_after"] == 0.64
    assert out["best_candidates"][0]["mse_before"] == 1.0


def test_two_rounds_history(tmp_path: Path) -> None:
    from flowforge.orchestrator.history import session_history

    path = tmp_path / "events.jsonl"
    events = [
        {
            "type": "fit", "step": "fit", "round": 1,
            "fits": [
                {"expression": "tanh(I3) * T2", "mse_after": 0.9, "mse_before": 1.0},
                {"expression": "-3.1 * T2", "mse_after": 0.64, "mse_before": 1.0},
            ],
        },
        {
            "type": "champion", "step": "champion", "round": 1,
            "champion": {
                "expression": "-3.1 * T2",
                "train": {"mse": 0.64, "mse_zero": 1.0, "ratio": 0.64},
                "worst_validation_ratio": 0.7,
                "attack_ratios": {"case_x": 1.2},
            },
        },
        {
            "type": "redteam", "step": "redteam", "round": 1,
            "breaks": [{"expression": "tanh(I3) * T2", "case_id": "case_x", "ratio": 1.5}],
        },
        {
            "type": "fit", "step": "fit", "round": 2,
            "fits": [{"expression": "0.5 * T1", "mse_after": 0.2, "mse_before": 1.0}],
        },
        {
            "type": "champion", "step": "champion", "round": 2,
            "champion": {"expression": "0.5 * T1", "train": {"ratio": 0.2}},
        },
        {
            "type": "redteam", "step": "redteam", "round": 2,
            "breaks": [],
        },
    ]
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")
    out = session_history(path)
    assert out["rounds_seen"] == 2
    exprs = [c["expression"] for c in out["best_candidates"]]
    assert exprs == ["0.5 * T1", "-3.1 * T2", "tanh(I3) * T2"]
    assert out["best_candidates"][0]["mse_after"] == 0.2
    assert set(out["best_candidates"][0]) == {"expression", "mse_after", "mse_before"}
    limited = session_history(path, k=2)
    assert len(limited["best_candidates"]) == 2
    assert limited["best_candidates"][0]["expression"] == "0.5 * T1"
    assert len(out["champions"]) == 2
    first = out["champions"][0]
    assert first["round"] == 1
    assert first["expression"] == "-3.1 * T2"
    assert first["train_ratio"] == 0.64
    assert first["worst_validation_ratio"] == 0.7
    assert first["attack_ratios"] == {"case_x": 1.2}
    second = out["champions"][1]
    assert second["round"] == 2
    assert second["expression"] == "0.5 * T1"
    assert second["train_ratio"] == 0.2
    assert second["worst_validation_ratio"] is None
    assert second["attack_ratios"] is None
    assert out["broken"] == [{"expression": "tanh(I3) * T2", "case_id": "case_x", "ratio": 1.5}]
    blob = " ".join(out["hints"])
    assert "T1" in blob and "T2" in blob
    assert "tanh(I3) * T2" in blob
    assert "broken" in blob.lower()


def test_second_round_theorist_sees_first_best(tmp_path: Path, monkeypatch) -> None:
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

    seen: list[dict] = []

    def fake_dispatch(role, runtime, context):
        class Res:
            def __init__(self, payload: dict):
                self.payload = dict(payload)

            def model_dump(self) -> dict:
                return dict(self.payload)

        if role == "theorist":
            seen.append(json.loads(json.dumps(context, default=str)))
            return Res({"expressions": ["-3.1 * T2"], "mechanisms": [], "risk_audit": "fake"})
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
            return Res({"modules": ["-3.1 * T2"], "gates": []})
        return Res({})

    monkeypatch.setattr(dispatcher, "dispatch_role", fake_dispatch)

    session_dir = tmp_path / "sess"
    first = run_round(1, mock=False, session_dir=session_dir)
    assert first["status"] == "ok"
    events_path = Path(first["events_path"])
    first_fits: list[str] = []
    for event in read_events(events_path):
        if event.get("type") == "fit":
            for item in event.get("fits", []):
                if isinstance(item, dict) and isinstance(item.get("expression"), str):
                    first_fits.append(item["expression"])
    assert first_fits, "expected first round to log fits"
    second = run_round(2, mock=False, session_dir=session_dir)
    assert second["status"] == "ok"
    assert len(seen) == 2
    assert "previous_results" not in seen[0] or seen[0]["previous_results"]["rounds_seen"] == 0
    prev = seen[1].get("previous_results")
    assert isinstance(prev, dict)
    assert prev["rounds_seen"] == 1
    assert prev["best_candidates"], "second round should see first round fits"
    prev_exprs = [c["expression"] for c in prev["best_candidates"]]
    assert any(expr in first_fits for expr in prev_exprs)


def test_rung3_rejections_reported_as_non_realizable(tmp_path: Path) -> None:
    from flowforge.orchestrator.history import session_history

    events = [
        {"type": "fit", "round": 1, "fits": [
            {"expression": "A*T1", "mse_after": 0.001, "status": "ok"},
            {"expression": "B*T1", "mse_after": 0.002, "status": "ok"}]},
        {"type": "rung2", "round": 1, "survivors": [{"expression": "A*T1"}, {"expression": "B*T1"}]},
        {"type": "rung3", "round": 1, "survivors": [{"expression": "B*T1"}]},
        {"type": "champion", "round": 1, "champion": None},
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    hist = session_history(path)
    assert [b["expression"] for b in hist["broken"] if b.get("reason") == "non_realizable"] == ["A*T1"]
    assert [b["expression"] for b in hist["best_candidates"]] == ["B*T1"]  # rejected one never ranked "best"
    assert any("non-realizable" in h for h in hist["hints"])


def test_pre_rung2_realizability_drops_reported_as_non_realizable(tmp_path: Path) -> None:
    from flowforge.orchestrator.history import session_history

    events = [
        {"type": "fit", "round": 1, "fits": [
            {"expression": "A*T1", "mse_after": 0.001, "status": "ok"},
            {"expression": "B*T1", "mse_after": 0.002, "status": "ok"}]},
        {"type": "rung2", "round": 1, "survivors": [{"expression": "B*T1"}], "non_realizable": ["A*T1"]},
        {"type": "rung3", "round": 1, "survivors": [{"expression": "B*T1"}]},
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    hist = session_history(path)
    assert [b["expression"] for b in hist["broken"] if b.get("reason") == "non_realizable"] == ["A*T1"]
    assert [b["expression"] for b in hist["best_candidates"]] == ["B*T1"]

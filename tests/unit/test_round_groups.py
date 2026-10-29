"""Parallel research groups: staffing, per-group steps, merged champion."""
import json

import pytest


def _events(session_dir):
    path = session_dir / "events.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_two_groups_staff_and_merge(tmp_path) -> None:
    from flowforge.orchestrator.round import run_round

    session_dir = tmp_path / "sess"
    res = run_round(1, mock=True, session_dir=str(session_dir), groups=2)
    assert res["groups"] == 2
    assert [s["group"] for s in res["staffing"]] == ["g0", "g1"]
    assert res["staffing"][0]["mechanism"] != res["staffing"][1]["mechanism"]
    assert res["event_count"] == 1 + 7 * 2 + 4 == 19

    events = _events(session_dir)
    steps = [(e.get("step"), e.get("group")) for e in events]
    assert steps[0] == ("board", "all")
    assert steps[1][0] == "theorist" and steps[1][1] == "g0"
    assert steps[8][0] == "theorist" and steps[8][1] == "g1"
    assert [s for s, _ in steps[-4:]] == ["skeptic", "redteam", "composer", "champion"]
    mechs = {e.get("mechanism") for e in events if e.get("step") == "theorist"}
    assert len(mechs) == 2
    assert res["status"] == "ok"
    assert res["champion"]["expression"] in ("0", "I1", "tanh(I1)", "I1 + I2")


def test_single_group_chain_unchanged(tmp_path) -> None:
    from flowforge.orchestrator.round import run_round

    session_dir = tmp_path / "sess"
    res = run_round(1, mock=True, session_dir=str(session_dir))
    assert res["event_count"] == 12
    events = _events(session_dir)
    assert [e.get("step") for e in events] == [
        "board", "theorist", "coder", "rung0", "rung1", "rung2", "rung3",
        "analyst", "skeptic", "redteam", "composer", "champion",
    ]


def test_groups_must_be_positive() -> None:
    from flowforge.orchestrator.round import run_round

    with pytest.raises(ValueError):
        run_round(1, mock=True, session="x", groups=0)

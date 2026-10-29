"""Analyst region evidence: every round renders maps + segments them (S6)."""
import json
from pathlib import Path


def test_mock_round_logs_analyst_regions_with_maps(tmp_path) -> None:
    from flowforge.orchestrator.round import run_round

    session_dir = tmp_path / "sess"
    res = run_round(1, mock=True, session_dir=str(session_dir))
    assert res["status"] == "ok"

    pngs = list(session_dir.glob("*.png"))
    assert len(pngs) > 0
    for png in pngs:
        assert png.with_suffix(".npy").exists()

    events = [json.loads(l) for l in
              (session_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
              if l.strip()]
    assert len(events) == 12  # regions fold into the analyst step event
    analyst = [e for e in events if e.get("type") == "analyst"][0]
    assert analyst["regions"]
    first = analyst["regions"][0]
    assert first["regions"] and "box" in first["regions"][0]
    assert isinstance(first["illustrative"], bool)
    assert Path(first["image"]).exists()

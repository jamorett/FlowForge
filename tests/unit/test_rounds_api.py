"""POST /api/rounds/start launches a mock round in the background (S5.5)."""
import json
import time
from pathlib import Path


def test_start_round_runs_mock_to_completion(tmp_path, monkeypatch) -> None:
    import flowforge.api.server as srv

    monkeypatch.chdir(tmp_path)
    res = srv.start_round(session="started", mock=True, round_no=1)
    assert res["status"] == "started"

    deadline = time.time() + 120
    path = Path("runs") / "started" / "events.jsonl"
    while time.time() < deadline:
        if path.exists():
            lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            if len(lines) >= 12:
                break
        time.sleep(0.5)
    events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [e.get("step", e.get("type")) for e in events][:12] == [
        "board", "theorist", "coder", "rung0", "rung1", "rung2", "rung3",
        "analyst", "skeptic", "redteam", "composer", "champion",
    ]


def test_start_round_rejects_bad_session() -> None:
    import flowforge.api.server as srv

    res = srv.start_round(session="../escape", mock=True)
    assert res["status"] == "rejected"

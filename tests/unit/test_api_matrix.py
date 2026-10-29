"""Matrix lists proposed candidates; cells need scored events (S5.5)."""
import json


def _write_events(root, session, events):
    d = root / "runs" / session
    d.mkdir(parents=True)
    with (d / "events.jsonl").open("w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def test_matrix_lists_step_candidates_without_inventing_cells(tmp_path, monkeypatch) -> None:
    from flowforge.api.server import matrix

    monkeypatch.chdir(tmp_path)
    _write_events(tmp_path, "s", [
        {"type": "theorist", "candidates": ["I1", "tanh(I1)"], "prompt_hash": "h"},
        {"type": "champion", "champion": {"expression": "I1"}, "prompt_hash": "h"},
    ])
    m = matrix("s")
    assert m["candidates"] == ["I1", "tanh(I1)"]
    assert m["cells"] == []
    assert m["locked_greyed"] is True


def test_latest_regions_empty_until_something_renders(tmp_path, monkeypatch) -> None:
    import numpy as np

    from flowforge.api.server import latest_regions
    from flowforge.render.error_map import render_png

    monkeypatch.chdir(tmp_path)
    assert latest_regions("s")["source"] == "none"

    d = tmp_path / "runs" / "s"
    d.mkdir(parents=True)
    render_png(np.abs(np.ones((8, 8))), d / "err.png")
    res = latest_regions("s")
    assert res["source"] == "local-fallback"
    assert len(res["regions"]) > 0


def test_matrix_fills_cells_from_scored_events(tmp_path, monkeypatch) -> None:
    from flowforge.api.server import matrix

    monkeypatch.chdir(tmp_path)
    _write_events(tmp_path, "s", [
        {"type": "theorist", "candidates": ["I1"], "prompt_hash": "h"},
        {"candidate": "I1", "flow": "periodic_hill_re5600",
         "error": 0.5, "split": "train"},
    ])
    m = matrix("s")
    assert "I1" in m["candidates"]
    assert m["cells"] == [{"candidate": "I1", "flow": "periodic_hill_re5600",
                           "error": 0.5, "split": "train"}]

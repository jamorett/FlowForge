"""Live Lab API helpers: spend meter, LaTeX, arms listing, artifact name guard."""
import json

import pytest

import flowforge.api.server as srv


def _session(tmp_path, monkeypatch, name="lab", events=()):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "runs" / name
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return d


def test_session_state_reports_tokens_spend_and_rounds(tmp_path, monkeypatch):
    _session(tmp_path, monkeypatch, events=[
        {"model": "m", "tokens": 1000}, {"type": "board", "step": "board", "round": 1},
        {"model": "m", "tokens": 3000}, {"type": "champion", "step": "champion", "round": 2}])
    st = srv.session_state("lab")
    assert st["tokens"] == 4000 and st["rounds"] == [1, 2] and st["last_step"] == "champion"
    assert st["dollars_upper"] == pytest.approx(4000 * 4.25 / 1e6)


def test_latex_renders_valid_and_flags_invalid():
    ok = srv.latex("2 * tanh(I1) * T1 + 1.5 * T3")
    assert "tanh" in ok["latex"] and "T^{(1)}" in ok["latex"]
    bad = srv.latex("import os")
    assert bad["latex"] is None and bad["error"]


def test_arms_listing_enriches_dl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs" / "arms").mkdir(parents=True)
    payload = {"mode": "frozen", "arms": {"swarm": {"seeds": [{"seed": 42, "metric": 0.8, "expression": "I1 * T1"},
                                                              {"seed": 43, "metric": None, "expression": None}]}}}
    (tmp_path / "runs" / "arms" / "r.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "runs" / "arms" / "junk.json").write_text("{not json", encoding="utf-8")
    out = srv.arms_results()
    assert [o["file"] for o in out] == ["r.json"]
    rows = out[0]["arms"]["swarm"]["seeds"]
    assert rows[0]["dl"] > 0 and rows[1]["dl"] is None


def test_artifact_rejects_traversal_and_serves_png(tmp_path, monkeypatch):
    from fastapi import HTTPException

    d = _session(tmp_path, monkeypatch)
    (d / "err_r1_0.png").write_bytes(b"\x89PNG\r\n")
    for session, name in (("lab", "../../secret.png"), ("..", "x.png"), ("lab", "events.jsonl")):
        with pytest.raises(HTTPException):
            srv.artifact(session, name)
    assert str(srv.artifact("lab", "err_r1_0.png").path).endswith("err_r1_0.png")

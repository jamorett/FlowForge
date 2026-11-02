"""UI run control: validation, budget cap, pause/stop between rounds, experiment archive guard."""
import time
from pathlib import Path

import pytest

from flowforge.api import run_control as rc


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rc, "_session_cap", lambda: 50.0)
    return rc.RunManager()


def _wait(run, timeout=10):
    end = time.time() + timeout
    while run.status in ("running", "paused", "stopping") and time.time() < end:
        time.sleep(0.05)


def test_validation_rejects_unsafe_requests(mgr):
    assert "confirm_live" in mgr.start_session("s", 1, 1, True, mock=False, budget_usd=1.0)["reason"]
    assert "budget" in mgr.start_session("s", 1, 1, True, mock=True, budget_usd=99.0)["reason"]
    assert "rounds" in mgr.start_session("s", 0, 1, True, mock=True, budget_usd=1.0)["reason"]
    assert "groups" in mgr.start_session("s", 1, 9, True, mock=True, budget_usd=1.0)["reason"]
    assert mgr.start_session("../x", 1, 1, True, mock=True, budget_usd=1.0)["status"] == "rejected"
    assert "3 distinct" in mgr.start_experiment(1, 1, [1, 1, 2], 1.0, dry_run=True)["reason"]


def test_session_run_stops_at_budget_cap(mgr, monkeypatch):
    calls = []

    def fake_round(r, **kw):
        calls.append((r, kw["groups"], kw["redteam"], kw["mock"]))
        return {"status": "ok", "dollars_spent": 0.4}

    monkeypatch.setattr("flowforge.orchestrator.round.run_round", fake_round)
    res = mgr.start_session("cap", rounds=5, groups=2, redteam=False, mock=False, budget_usd=1.0, confirm_live=True)
    run = mgr.runs[res["run"]["id"]]
    _wait(run)
    # spend checked before each round: 0 -> 0.4 -> 0.8 -> 1.2 >= 1.0 stops before round 4
    assert run.status == "budget" and run.rounds_done == 3 and [c[0] for c in calls] == [1, 2, 3]
    assert calls[0][1:] == (2, False, False)  # groups / red team / live passed through


def test_stop_and_pause_take_effect_between_rounds(mgr, monkeypatch):
    holder = {}

    def fake_round(r, **kw):
        if r == 1:
            while "id" not in holder:  # the thread can start before start_session returns
                time.sleep(0.01)
            mgr.control(holder["id"], "stop")  # user presses Stop during round 1
        return {"status": "ok", "dollars_spent": 0.0}

    monkeypatch.setattr("flowforge.orchestrator.round.run_round", fake_round)
    res = mgr.start_session("stopme", rounds=5, groups=1, redteam=True, mock=True, budget_usd=1.0)
    holder["id"] = res["run"]["id"]
    run = mgr.runs[holder["id"]]
    _wait(run)
    assert run.status == "stopped" and run.rounds_done == 1

    gate = {"n": 0}

    def counting_round(r, **kw):
        gate["n"] += 1
        return {"status": "ok", "dollars_spent": 0.0}

    monkeypatch.setattr("flowforge.orchestrator.round.run_round", counting_round)
    res = mgr.start_session("pauseme", rounds=3, groups=1, redteam=True, mock=True, budget_usd=1.0)
    rid = res["run"]["id"]
    mgr.control(rid, "pause")
    time.sleep(0.3)
    paused_at = gate["n"]
    time.sleep(0.6)
    assert gate["n"] == paused_at  # no new rounds while paused
    mgr.control(rid, "resume")
    _wait(mgr.runs[rid])
    assert mgr.runs[rid].status == "finished" and gate["n"] == 3


def test_experiment_refuses_reused_sessions_until_archived(mgr, monkeypatch):
    (Path("runs") / "arms-swarm-s42").mkdir(parents=True)
    res = mgr.start_experiment(1, 1, [42, 43, 44], 5.0, dry_run=False, confirm_live=True)
    assert res["status"] == "rejected" and res["needs_archive"] == ["arms-swarm-s42"]

    class FakeProc:
        def poll(self):
            return 0

        def terminate(self):
            pass

    launched = []
    monkeypatch.setattr(rc.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd) or FakeProc())
    res = mgr.start_experiment(1, 1, [42, 43, 44], 5.0, dry_run=False, archive_existing=True, confirm_live=True)
    assert res["status"] == "started" and not (Path("runs") / "arms-swarm-s42").exists()
    assert any(p.name.startswith("_archive-") for p in Path("runs").iterdir())
    assert "--control-dir" in launched[0] and "--dry-run" not in launched[0]
    runs = mgr.list()
    assert runs[0]["status"] == "finished" and runs[0]["message"] == "finished without a result file"

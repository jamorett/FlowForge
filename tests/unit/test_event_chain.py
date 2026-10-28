"""A4: run_round -> events.jsonl chain and /ws/events live tail."""

import json
from pathlib import Path

import flowforge.api.server as srv
from flowforge.agents.runtime.event_logger import EventLogger
from flowforge.orchestrator.round import ROUND_STEPS, run_round

EXPECTED_STEPS = [
    "board", "theorist", "coder", "rung0", "rung1", "rung2", "rung3",
    "analyst", "skeptic", "redteam", "composer", "champion",
]


def test_run_round_writes_events_jsonl_in_order(tmp_path):
    session_dir = tmp_path / "sess"
    result = run_round(1, mock=True, session_dir=session_dir)
    path = session_dir / "events.jsonl"
    assert path.exists()
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(events) >= 10
    steps = [e.get("step", e.get("type")) for e in events]
    # Full env (sympy present): exactly the 12 steps. Without sympy the
    # round logs the 12 steps as unavailable plus one explicit error event.
    assert steps[:len(EXPECTED_STEPS)] == EXPECTED_STEPS
    assert len(steps) in (len(EXPECTED_STEPS), len(EXPECTED_STEPS) + 1)
    if len(steps) > len(EXPECTED_STEPS):
        assert steps[-1] == "error"
        assert result["status"] == "error"
    assert list(ROUND_STEPS) == EXPECTED_STEPS
    for e in events[:len(EXPECTED_STEPS)]:
        assert isinstance(e.get("prompt_hash"), str) and e["prompt_hash"].strip()
        assert e["mock"] is True
        assert e["synthetic"] is True
    # Replay/readback through EventLogger returns the same events.
    readback = EventLogger(session_dir).read_events()
    assert [e["step"] for e in readback][:len(EXPECTED_STEPS)] == EXPECTED_STEPS
    assert result["events_path"] == str(path)


def test_run_round_default_runs_layout_in_temp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_round(2, mock=True, session="probe")
    path = tmp_path / "runs" / "probe" / "events.jsonl"
    assert path.exists()
    assert result["events_path"] == str(Path("runs") / "probe" / "events.jsonl")
    # API readback reads the same file the round wrote.
    events = srv._read_events("probe")
    assert [e["step"] for e in events][:len(EXPECTED_STEPS)] == EXPECTED_STEPS


class _Aw:
    """Awaitable that yields once -- lets tests drive the handler
    coroutine manually with ``coro.send(None)`` (no event loop, so no
    socketpair is needed in restricted sandboxes)."""

    def __init__(self, value=None):
        self.value = value

    def __await__(self):
        yield self
        return self.value


class _FakeWS:
    def __init__(self, timeline):
        self.timeline = timeline
        self.msgs = []

    def accept(self):
        return _Aw()

    def send_text(self, text):
        self.timeline.append(("send", text))
        self.msgs.append(text)
        return _Aw()


def _drive(coro):
    while True:
        try:
            coro.send(None)
        except StopIteration:
            return


def _run_ws(monkeypatch, tmp_path, session="probe", append_on_sleep=None):
    timeline = []
    sleeps = []
    appended = {"done": False}

    def fake_sleep(delay):
        sleeps.append(delay)
        timeline.append(("sleep", delay))
        if append_on_sleep is not None and not appended["done"] and len(sleeps) >= append_on_sleep:
            appended["done"] = True
            path = tmp_path / "runs" / session / "events.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "tail_tick", "i": 99}) + "\n")
        return _Aw()

    monkeypatch.setattr(srv.asyncio, "sleep", fake_sleep)
    monkeypatch.chdir(tmp_path)
    ws = _FakeWS(timeline)
    _drive(srv.ws_events(ws, session=session))
    return ws, timeline, sleeps


def test_ws_first_send_prompt_paced_and_tails_appended_line(tmp_path, monkeypatch):
    monkeypatch.delenv("FLOWFORGE_REPLAY", raising=False)
    p = tmp_path / "runs" / "probe"
    p.mkdir(parents=True)
    (p / "events.jsonl").write_text(
        "\n".join(json.dumps({"type": "tick", "i": i}) for i in range(3)) + "\n", encoding="utf-8"
    )
    # 3 snapshot events need 2 pacing sleeps; the next sleep is the first
    # tail poll -- append the new line during it.
    ws, timeline, sleeps = _run_ws(monkeypatch, tmp_path, append_on_sleep=3)

    assert timeline[0][0] == "send"  # first message before any sleep
    assert sleeps and all(d == srv.PACE_SECONDS for d in sleeps)
    payloads = [json.loads(m) for m in ws.msgs]
    ticks = [m for m in payloads if m.get("type") == "tick"]
    assert [t["i"] for t in ticks] == [0, 1, 2]
    # Line appended after connect is delivered by the tail, before end.
    assert any(m.get("type") == "tail_tick" and m.get("i") == 99 for m in payloads)
    assert payloads[-1]["type"] == "end"
    assert payloads[-1]["sent"] == 4
    tail_idx = next(i for i, m in enumerate(payloads) if m.get("type") == "tail_tick")
    assert tail_idx < len(payloads) - 1


def test_ws_replay_mode_ends_promptly_without_trailing_sleep(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWFORGE_REPLAY", "1")
    p = tmp_path / "runs" / "probe"
    p.mkdir(parents=True)
    (p / "events.jsonl").write_text(
        "\n".join(json.dumps({"type": "tick", "i": i}) for i in range(3)) + "\n", encoding="utf-8"
    )
    ws, timeline, sleeps = _run_ws(monkeypatch, tmp_path)
    payloads = [json.loads(m) for m in ws.msgs]
    assert [m.get("i") for m in payloads if m.get("type") == "tick"] == [0, 1, 2]
    assert payloads[-1] == {"type": "end", "sent": 3}
    # Only the inter-event pacing gaps: no tail polls, no trailing sleep.
    assert sleeps == [srv.PACE_SECONDS, srv.PACE_SECONDS]
    assert timeline[-1][0] == "send"

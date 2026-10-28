"""FastAPI event streamer (S5.5). Server-paced at ~20 events/s by default.

A bare subscribe (no pacing, no count) still gets paced delivery:
first event promptly, then ~50 ms apart. The client cannot burst it.
Zero physics here: endpoints only read runs/<session>/events.jsonl and the
red-team sweep definition; all computation lives in the Python services.

``/ws/events`` sends the existing snapshot first (paced), then tails
``events.jsonl``: it polls the file every ``PACE_SECONDS`` and delivers
lines appended after connect. It ends after a bounded idle limit
(``TAIL_IDLE_POLLS`` polls with no new data), on client disconnect, or
-- in replay/finite mode (``FLOWFORGE_REPLAY=1``) -- promptly at EOF
with no trailing sleep before the ``end`` message.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="FlowForge")
PACE_SECONDS = 0.05
TAIL_POLL_SECONDS = PACE_SECONDS
# Bounded live-tail: ~1 s (20 polls x 50 ms) without new data ends the stream.
TAIL_IDLE_POLLS = 20
TAIL_IDLE_SECONDS = TAIL_IDLE_POLLS * PACE_SECONDS
_SAFE_SESSION = re.compile(r"^[A-Za-z0-9_-]+$")


def _events_path(session: str) -> Path:
    assert _SAFE_SESSION.match(session), "invalid session id"
    return Path("runs") / session / "events.jsonl"


def _read_events(session: str) -> list[dict]:
    path = _events_path(session)
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "raw", "line": line})
    return events


def _read_new_lines(path: Path, offset: int, pending: str):
    """Return (complete_lines, new_offset, pending_partial)."""
    try:
        size = path.stat().st_size
    except OSError:
        return [], offset, pending
    if size < offset:  # truncated / replaced: restart
        offset, pending = 0, ""
    if size == offset:
        return [], offset, pending
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            fh.seek(offset)
            chunk = fh.read()
            offset = fh.tell()
    except OSError:
        return [], offset, pending
    text = pending + chunk
    parts = text.split("\n")
    pending = parts.pop()  # trailing partial line ("" if chunk ended with \n)
    lines = [p.rstrip("\r") for p in parts]
    return lines, offset, pending


def _client_gone(ws) -> bool:
    if getattr(ws, "disconnected", False) or getattr(ws, "closed", False):
        return True
    state = getattr(ws, "client_state", None)
    if state is not None:
        name = str(getattr(state, "name", state)).upper()
        if name.endswith("DISCONNECTED") or name == "CLOSED":
            return True
    return False


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/session/state")
def session_state(session: str = "default") -> dict:
    events = _read_events(session)
    types: dict[str, int] = {}
    for e in events:
        types[str(e.get("type", "unknown"))] = types.get(str(e.get("type", "unknown")), 0) + 1
    return {
        "session": session,
        "exists": _events_path(session).exists(),
        "event_count": len(events),
        "event_types": types,
        "pace_seconds": PACE_SECONDS,
        "events_per_second": round(1.0 / PACE_SECONDS),
    }


@app.get("/api/matrix")
def matrix(session: str = "default") -> dict:
    """Candidates x flows matrix scaffold for the Generalization Matrix view.

    Flows are grouped as train / generated / locked. Generated flows come from
    the red-team sweep (validation only). Cells are filled from scored events
    in the session log when present; otherwise left empty (never invented).
    """
    from flowforge.redteam.generator import generate_attacks

    attacks = [
        {"flow": f"{s.kind}_a{s.alpha}_re{int(s.reynolds)}", "kind": s.kind,
         "alpha": s.alpha, "reynolds": s.reynolds, "split": s.split}
        for s in generate_attacks()
    ]
    events = _read_events(session)
    candidates = sorted({str(e["candidate"]) for e in events if e.get("candidate")})
    cells = [
        {"candidate": str(e["candidate"]), "flow": str(e.get("flow", "")),
         "error": e.get("error"), "split": e.get("split", "generated")}
        for e in events if e.get("candidate") and e.get("flow")
    ]
    return {
        "session": session,
        "candidates": candidates,
        "flows": {
            "train": ["periodic_hill_re5600", "periodic_hill_re10595"],
            "generated": attacks,
            "locked": ["square_duct", "nasa_wall_mounted_hump"],
        },
        "locked_greyed": True,
        "cells": cells,
    }


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket, session: str = "default") -> None:
    await ws.accept()
    try:
        path = _events_path(session)
        replay = os.environ.get("FLOWFORGE_REPLAY") == "1"
        sent = 0
        offset = 0
        pending = ""
        idle_polls = 0
        first = True
        # True when a PACE sleep has just elapsed and may serve as the
        # pacing gap before the next send (avoids a double sleep).
        gap_ready = False

        async def _send(line: str) -> None:
            nonlocal sent, first, gap_ready
            if not first and not gap_ready:
                await asyncio.sleep(PACE_SECONDS)
            await ws.send_text(line)
            sent += 1
            first = False
            gap_ready = False

        while True:
            if _client_gone(ws):
                return
            lines, offset, pending = _read_new_lines(path, offset, pending)
            if lines:
                idle_polls = 0
                for line in lines:
                    if not line.strip():
                        continue
                    await _send(line)
                if replay:
                    break
            else:
                if replay:
                    break
                if idle_polls >= TAIL_IDLE_POLLS:
                    break
            # Tail poll: also the pacing gap before any next event.
            await asyncio.sleep(PACE_SECONDS)
            gap_ready = True
            idle_polls += 1

        # Flush a final unterminated line (finite/replay files and a
        # writer that finished without a trailing newline).
        if pending.strip():
            await _send(pending.strip())
        # Prompt end: no trailing sleep after the last event / decision.
        await ws.send_text(json.dumps({"type": "end", "sent": sent}))
    except WebSocketDisconnect:
        return

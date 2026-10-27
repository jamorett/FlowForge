"""FastAPI event streamer (S5.5). Server-paced at ~20 events/s by default.

A bare subscribe (no pacing, no count) still gets paced delivery:
first event promptly, then ~50 ms apart. The client cannot burst it.
Zero physics here: endpoints only read runs/<session>/events.jsonl and the
red-team sweep definition; all computation lives in the Python services.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="FlowForge")
PACE_SECONDS = 0.05
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
        sent = 0
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                await ws.send_text(line)
                sent += 1
                await asyncio.sleep(PACE_SECONDS)
        await ws.send_text(json.dumps({"type": "end", "sent": sent}))
    except WebSocketDisconnect:
        return

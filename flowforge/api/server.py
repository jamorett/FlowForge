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
    # Candidates: scored cells first, then step-level proposals (theorist /
    # rung survivors / champion). Cells stay empty until scored
    # candidate x flow events exist; they are never invented here.
    candidates = sorted({str(e["candidate"]) for e in events if e.get("candidate")})
    for e in events:
        for key in ("candidates", "expressions"):
            vals = e.get(key)
            if isinstance(vals, list):
                candidates.extend(str(v) for v in vals if isinstance(v, (str, int, float)))
        for key in ("survivors", "final"):
            vals = e.get(key)
            if isinstance(vals, list):
                for s in vals:
                    if isinstance(s, dict) and s.get("expression"):
                        candidates.append(str(s["expression"]))
        champ = e.get("champion")
        if isinstance(champ, dict) and champ.get("expression"):
            candidates.append(str(champ["expression"]))
    candidates = sorted(set(candidates))
    cells = [
        {"candidate": str(e["candidate"]), "flow": str(e.get("flow", "")),
         "error": e.get("error"), "split": e.get("split", "generated")}
        for e in events if e.get("candidate") and e.get("flow")
    ]
    return {
        "session": session,
        "candidates": candidates,
        "flows": {
            "train": ["periodic_hill_re5600", "periodic_hill_alpha1p5_re5600"],
            "generated": attacks,
            "locked": ["square_duct", "nasa_wall_mounted_hump"],
        },
        "locked_greyed": True,
        "cells": cells,
    }


@app.post("/api/rounds/start")
def start_round(session: str = "default", mock: bool = True,
                round_no: int = 1) -> dict:
    """Start a research round in the background (mock by default: no spend).

    The round appends to ``runs/<session>/events.jsonl``, which the UI
    already streams live. A second start for a running session is refused.
    Cancellation is not implemented: a started round runs to completion.
    """
    import threading

    from flowforge.orchestrator.round import run_round

    if not _SAFE_SESSION.match(session):
        return {"status": "rejected", "reason": "invalid session id"}
    existing = _round_threads.get(session)
    if existing is not None and existing.is_alive():
        return {"status": "already_running", "session": session}

    def _run() -> None:
        try:
            run_round(round_no, mock=mock, session=session)
        except Exception as exc:  # never take the thread down silently
            logger = __import__("logging").getLogger(__name__)
            logger.error("background round failed: %s", exc)

    thread = threading.Thread(target=_run, daemon=True,
                              name=f"round-{session}")
    _round_threads[session] = thread
    thread.start()
    return {"status": "started", "session": session, "mock": mock,
            "events": str(_events_path(session))}


_round_threads: dict = {}


@app.get("/api/regions")
def regions(image: str = "", use_api: bool = False) -> dict:
    """Segment one error-map PNG. Offline by default (no API spend).

    Set ``use_api=true`` only with ``MODEL_API_KEY`` configured; the
    response always reports which source produced the regions.
    """
    from flowforge.render.sam_client import segment_error_regions

    if not image:
        return {"image": image, "source": "none", "model": None,
                "regions": [], "detail": "no image given"}
    try:
        return segment_error_regions(image, use_api=use_api)
    except Exception as exc:
        return {"image": image, "source": "none", "model": None,
                "regions": [], "detail": f"segmentation failed: {exc}"}


@app.get("/api/latest_regions")
def latest_regions(session: str = "default", use_api: bool = False) -> dict:
    """Segment the newest rendered error map in ``runs/<session>``.

    Returns empty regions (never invented) when nothing was rendered yet.
    """
    from flowforge.render.sam_client import segment_error_regions

    root = Path("runs") / session
    newest: Path | None = None
    newest_mtime = -1.0
    if root.exists():
        for png in root.rglob("*.png"):
            if not png.with_suffix(".npy").exists():
                continue
            try:
                mtime = png.stat().st_mtime
            except OSError:
                continue
            if mtime > newest_mtime:
                newest, newest_mtime = png, mtime
    if newest is None:
        return {"image": None, "source": "none", "model": None,
                "regions": [], "detail": "no rendered error map yet"}
    try:
        return segment_error_regions(str(newest), use_api=use_api)
    except Exception as exc:
        return {"image": str(newest), "source": "none", "model": None,
                "regions": [], "detail": f"segmentation failed: {exc}"}


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

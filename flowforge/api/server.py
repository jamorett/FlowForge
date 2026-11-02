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
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FlowForge")
# The UI runs on its own port (Vite/static, 5173); without this the browser blocks every REST call.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
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


@app.get("/api/physics_cases")
def physics_cases() -> dict:
    """Cases the physics view may show: train, validation, red-team cases and attack hills (never locked)."""
    from flowforge.data.frozen_fields import (
        available_attack_flows,
        redteam_case_ids,
        train_case_ids,
        validation_case_ids,
    )

    return {"train": train_case_ids(), "validation": validation_case_ids(),
            "redteam": redteam_case_ids(),
            "attack": [f["case_id"] for f in available_attack_flows()]}


@app.get("/api/physics_view")
def physics_view(expression: str = "0", case: str = "periodic_hill_re5600", n: int = 1500) -> dict:
    """Lumley-triangle states of one case: RANS, DNS and RANS + candidate correction, plus where on
    the geometry the correction helps. A-priori (frozen) data only; locked cases are refused by the
    swarm guard like any other non-evaluator read."""
    import numpy as np

    from flowforge.data.split_guard import guard_swarm_path
    from flowforge.data.zarr_store import read_case
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.physics.tensors import barycentric_coords

    if not _SAFE_SESSION.match(case):
        return {"error": "invalid case id"}
    path = guard_swarm_path(Path("data/processed") / case, role="ui")
    if not path.exists():
        return {"error": f"case {case} not found"}
    data = read_case(path)
    inv = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("invariants/")}
    basis = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("tensor_basis/")}
    target, b_dns = data["targets/a_delta"], data["anisotropy/b_dns"]
    b_rans = b_dns - target
    try:
        pred = candidate_anisotropy(expression, inv, basis)
    except (ValueError, KeyError) as exc:
        return {"error": f"invalid expression: {exc}"}
    ok = np.isfinite(target).all(axis=(1, 2)) & np.isfinite(pred).all(axis=(1, 2))
    idx = np.flatnonzero(ok)
    if len(idx) > n:
        idx = np.sort(np.random.default_rng(0).choice(idx, n, replace=False))

    def lumley_xy(b: np.ndarray) -> dict:
        c1, _c2, c3 = barycentric_coords(b[idx])
        return {"x": np.round(c1 + 0.5 * c3, 4).tolist(), "y": np.round(np.sqrt(3) / 2 * c3, 4).tolist()}

    err_rans = np.sum(target[idx] ** 2, axis=(1, 2))
    err_corr = np.sum((target[idx] - pred[idx]) ** 2, axis=(1, 2))
    mse0 = float(np.mean(target[ok] ** 2))
    mse = float(np.mean((target[ok] - pred[ok]) ** 2))
    coords = data["coordinates"][idx]
    return {"case": case, "expression": expression, "n": len(idx),
            "ratio": mse / mse0 if mse0 > 0 else None,
            "rans": lumley_xy(b_rans), "dns": lumley_xy(b_dns), "corrected": lumley_xy(b_rans + pred),
            "b12": {"rans": np.round(b_rans[idx, 0, 1], 5).tolist(), "dns": np.round(b_dns[idx, 0, 1], 5).tolist(),
                    "corrected": np.round((b_rans + pred)[idx, 0, 1], 5).tolist()},
            "geometry": {"x": np.round(coords[:, 0], 4).tolist(), "y": np.round(coords[:, 1], 4).tolist(),
                         "gain": np.round(err_rans - err_corr, 8).tolist()}}


@app.get("/api/sessions")
def list_sessions() -> list[dict]:
    """Sessions with an event log under runs/, newest first (for the UI session picker)."""
    out = []
    for d in Path("runs").iterdir() if Path("runs").is_dir() else []:
        events = d / "events.jsonl"
        if d.is_dir() and _SAFE_SESSION.match(d.name) and events.is_file():
            with events.open(encoding="utf-8") as fh:
                count = sum(1 for line in fh if line.strip())
            out.append({"session": d.name, "events": count, "modified": events.stat().st_mtime})
    return sorted(out, key=lambda s: s["modified"], reverse=True)


@app.get("/api/session/state")
def session_state(session: str = "default") -> dict:
    events = _read_events(session)
    types: dict[str, int] = {}
    for e in events:
        types[str(e.get("type", "unknown"))] = types.get(str(e.get("type", "unknown")), 0) + 1
    from flowforge.agents.runtime.client import FALLBACK_PRICE_PER_M

    # Model-call records carry only total tokens (no in/out split): bill all at the
    # highest rate, so the figure is an upper bound like the runtime meter.
    tokens = sum(int(e["tokens"]) for e in events if isinstance(e.get("tokens"), (int, float)))
    rounds = sorted({e["round"] for e in events if isinstance(e.get("round"), int)})
    steps = [e for e in events if e.get("step")]
    return {
        "session": session,
        "exists": _events_path(session).exists(),
        "event_count": len(events),
        "event_types": types,
        "pace_seconds": PACE_SECONDS,
        "events_per_second": round(1.0 / PACE_SECONDS),
        "tokens": tokens,
        "dollars_upper": round(tokens * FALLBACK_PRICE_PER_M[1] / 1e6, 4),
        "rounds": rounds,
        "last_step": steps[-1].get("step") if steps else None,
    }


@app.get("/api/matrix")
def matrix(session: str = "default") -> dict:
    """Candidates x flows matrix scaffold for the Generalization Matrix view.

    Flows are grouped as train / generated / locked. Generated flows come from
    the red-team sweep (validation only). Cells are filled from scored events
    in the session log when present; otherwise left empty (never invented).
    """
    from flowforge.data.frozen_fields import attack_case_for
    from flowforge.redteam.generator import generate_attacks

    attacks = []
    for s in generate_attacks():
        spec = {"kind": s.kind, "alpha": s.alpha, "reynolds": s.reynolds}
        case_id = attack_case_for(spec)
        attacks.append({"flow": case_id or f"{s.kind}_a{s.alpha}_re{int(s.reynolds)}",
                        "kind": s.kind, "alpha": s.alpha, "reynolds": s.reynolds,
                        "split": s.split})
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
    # Scored cells from champion events (logged, never invented):
    # per-case validation ratios and frozen attack ratios.
    for e in events:
        champ = e.get("champion")
        if not isinstance(champ, dict) or not champ.get("expression"):
            continue
        expr = str(champ["expression"])
        for flow, payload in (champ.get("validation") or {}).items():
            if isinstance(payload, dict) and payload.get("ratio") is not None:
                cells.append({"candidate": expr, "flow": str(flow),
                              "error": float(payload["ratio"]), "split": "validation"})
        for flow, ratio in (champ.get("attack_ratios") or {}).items():
            try:
                cells.append({"candidate": expr, "flow": str(flow),
                              "error": float(ratio), "split": "generated"})
            except (TypeError, ValueError):
                continue
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
                round_no: int | None = None) -> dict:
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
    if round_no is None:  # continue the session: the UI never sends one, so every start used to be round 1
        done = [e["round"] for e in _read_events(session) if isinstance(e.get("round"), int)]
        round_no = max(done, default=0) + 1

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
    return {"status": "started", "session": session, "mock": mock, "round": round_no,
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


@app.get("/api/latex")
def latex(expr: str) -> dict:
    """Validated DSL expression -> LaTeX (falls back to the raw text, flagged, if it does not parse)."""
    import sympy as sp

    from flowforge.dsl.parser import validate_candidate

    try:
        tex = sp.latex(validate_candidate(expr))
    except Exception as exc:  # display helper: never fail the page over one bad expression
        return {"expr": expr, "latex": None, "error": str(exc)[:200]}
    for k in ("1", "2", "3", "4"):
        tex = tex.replace(f"T_{{{k}}}", f"T^{{({k})}}").replace(f"I_{{{k}}}", f"I_{k}")
    return {"expr": expr, "latex": tex}


_ARMS_FILE = re.compile(r"^[A-Za-z0-9_.-]+\.json$")


@app.get("/api/arms")
def arms_results() -> list[dict]:
    """Arms result files under runs/arms (newest first), each seed row enriched with its DL."""
    from flowforge.dsl.parser import complexity, validate_candidate
    from flowforge.elegance.engine import description_length

    root = Path("runs") / "arms"
    out = []
    for f in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if root.is_dir() else []:
        if not _ARMS_FILE.match(f.name):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or "arms" not in data:
            continue
        for arm in data["arms"].values():
            for row in arm.get("seeds", []):
                expr = row.get("expression")
                try:  # same DL as the champion rule (structure bits; constants not counted)
                    row["dl"] = description_length(complexity(validate_candidate(expr)), []) if expr else None
                except Exception:
                    row["dl"] = None
        out.append({"file": f.name, "modified": f.stat().st_mtime, **data})
    return out


_ARTIFACT = re.compile(r"^[A-Za-z0-9_.-]+\.png$")


@app.get("/api/artifact")
def artifact(session: str, name: str):
    """A rendered PNG (analyst error map) from runs/<session>/; names are strictly validated."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    if not _SAFE_SESSION.match(session) or not _ARTIFACT.match(name):
        raise HTTPException(status_code=400, detail="invalid session or file name")
    path = Path("runs") / session / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="image/png")


from pydantic import BaseModel  # noqa: E402  (run-control request bodies)


class SessionRunRequest(BaseModel):
    session: str
    rounds: int = 1
    groups: int = 1
    redteam: bool = True
    mock: bool = True
    budget_usd: float = 1.0
    confirm_live: bool = False


class ExperimentRequest(BaseModel):
    rounds: int = 5
    groups: int = 2
    seeds: list[int] = [42, 43, 44]
    budget_usd: float = 15.0
    dry_run: bool = False
    archive_existing: bool = False
    confirm_live: bool = False


@app.get("/api/runs")
def list_runs() -> dict:
    """Runs started from the UI (this server process), newest first, plus presets and limits."""
    from flowforge.api import run_control as rc

    return {"runs": rc.MANAGER.list(), "presets": rc.PRESETS,
            "limits": {"max_rounds": rc.MAX_ROUNDS, "max_groups": rc.MAX_GROUPS,
                       "session_dollar_limit": rc._session_cap(), "usd_per_round_group": rc.EST_USD_PER_ROUND_GROUP}}


@app.post("/api/runs/session")
def start_session_run(req: SessionRunRequest) -> dict:
    from flowforge.api import run_control as rc

    return rc.MANAGER.start_session(req.session, req.rounds, req.groups, req.redteam, req.mock,
                                    req.budget_usd, req.confirm_live)


@app.post("/api/runs/experiment")
def start_experiment_run(req: ExperimentRequest) -> dict:
    from flowforge.api import run_control as rc

    return rc.MANAGER.start_experiment(req.rounds, req.groups, list(req.seeds), req.budget_usd,
                                       req.dry_run, req.archive_existing, req.confirm_live)


@app.post("/api/runs/{run_id}/{action}")
def control_run(run_id: str, action: str) -> dict:
    from flowforge.api import run_control as rc

    if action not in ("pause", "resume", "stop", "kill"):
        return {"status": "rejected", "reason": "action must be pause, resume, stop or kill"}
    return rc.MANAGER.control(run_id, action)


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket, session: str = "default", backlog: str = "paced", skip: int = 0) -> None:
    """Stream a session's events. ``backlog="instant"`` sends the events already on disk at once
    (live view: no waiting for history); only events appended afterwards are paced. The default
    paces everything, which the Replay page uses to animate a recorded session. ``skip``: events
    the client already holds (reconnect after the idle end) are not resent."""
    await ws.accept()
    to_skip = max(int(skip), 0)
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

        instant_backlog = backlog == "instant"
        in_backlog = True

        async def _send(line: str) -> None:
            nonlocal sent, first, gap_ready
            if not first and not gap_ready and not (instant_backlog and in_backlog):
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
                    if to_skip:
                        to_skip -= 1
                        continue
                    await _send(line)
                in_backlog = False
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
        if pending.strip() and not to_skip:
            await _send(pending.strip())
        # Prompt end: no trailing sleep after the last event / decision.
        await ws.send_text(json.dumps({"type": "end", "sent": sent}))
    except WebSocketDisconnect:
        return

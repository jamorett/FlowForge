"""Run control for the UI: multi-round session runs and the 3-arm experiment.

* Session run: a background thread calling ``run_round`` round after round in one session.
  Pause / stop / budget are checked *between* rounds (a round is never cut in the middle).
* Experiment: ``scripts/run_arms.py`` as a subprocess, steered through ``pause`` / ``stop``
  files in a control dir (same between-round rule); ``kill`` terminates it at once (the
  result file is then not written and the run is reported as killed).

Live runs spend API credits, so they require ``confirm_live`` and a budget no larger than
``session_dollar_limit`` in ``configs/budgets.yaml``. All paths are relative to the working
directory, like the rest of the API (start the server from the repo root).
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

SAFE = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_ROUNDS, MAX_GROUPS = 20, 4
EST_USD_PER_ROUND_GROUP = 0.10  # observed ~$0.07 per round per group (frozen, 2026-11-01); rounded up
ARMS_SWARM = ("swarm", "swarm_no_redteam")
REPO = Path(__file__).resolve().parents[2]

PRESETS = [
    {"id": "smoke", "label": "Smoke test (mock, free)", "kind": "session",
     "description": "1 round, 1 group, mocked agents: checks the pipeline and the UI at no cost.",
     "params": {"rounds": 1, "groups": 1, "redteam": True, "mock": True, "budget_usd": 0.5}},
    {"id": "live-check", "label": "Quick live check", "kind": "session",
     "description": "1 real round, 1 group: confirms the live model path works (~$0.07).",
     "params": {"rounds": 1, "groups": 1, "redteam": True, "mock": False, "budget_usd": 0.5}},
    {"id": "session", "label": "Research session (5 × 2)", "kind": "session",
     "description": "5 live rounds × 2 groups with the red team — one full research line (~$0.7).",
     "params": {"rounds": 5, "groups": 2, "redteam": True, "mock": False, "budget_usd": 2.0}},
    {"id": "ablation", "label": "Ablation session (no red team)", "kind": "session",
     "description": "Same as the research session with the red team off (RP1 contrast).",
     "params": {"rounds": 5, "groups": 2, "redteam": False, "mock": False, "budget_usd": 2.0}},
    {"id": "experiment-dry", "label": "Experiment dry run (free)", "kind": "experiment",
     "description": "Whole 3-arm × 3-session protocol with mocked agents: bookkeeping only, never a result.",
     "params": {"rounds": 1, "groups": 1, "seeds": [42, 43, 44], "budget_usd": 1.0, "dry_run": True}},
    {"id": "experiment", "label": "Full experiment (3 arms × 3 sessions)", "kind": "experiment",
     "description": "Swarm vs no-red-team vs sparse baseline, 5 rounds × 2 groups per session — the results table (~$3–4).",
     "params": {"rounds": 5, "groups": 2, "seeds": [42, 43, 44], "budget_usd": 15.0, "dry_run": False}},
]


@dataclass
class Run:
    id: str
    kind: str
    params: dict
    status: str = "running"  # running | paused | stopping | stopped | budget | finished | failed | killed
    started: float = field(default_factory=time.time)
    ended: float | None = None
    rounds_done: int = 0
    round_now: int | None = None
    spent_usd: float = 0.0
    sessions: list = field(default_factory=list)
    out_file: str | None = None
    log_file: str | None = None
    message: str = ""


def _session_cap() -> float:
    from flowforge.config import load_budgets

    return float(load_budgets()["session_dollar_limit"])


def _next_round(session: str) -> int:
    path = Path("runs") / session / "events.jsonl"
    best = 0
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line).get("round")
            except (ValueError, AttributeError):
                continue
            if isinstance(r, int):
                best = max(best, r)
    return best + 1


def _tokens_upper_usd(sessions: list[str]) -> float:
    """Spend so far from the sessions' model-call records (upper bound, like the meter)."""
    from flowforge.agents.runtime.client import FALLBACK_PRICE_PER_M

    tokens = 0
    for s in sessions:
        path = Path("runs") / s / "events.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                t = json.loads(line).get("tokens")
            except (ValueError, AttributeError):
                continue
            if isinstance(t, (int, float)):
                tokens += int(t)
    return round(tokens * FALLBACK_PRICE_PER_M[1] / 1e6, 4)


def estimate_usd(kind: str, rounds: int, groups: int, mock_or_dry: bool) -> float:
    if mock_or_dry:
        return 0.0
    sessions = 1 if kind == "session" else 6
    return round(rounds * groups * sessions * EST_USD_PER_ROUND_GROUP, 2)


class RunManager:
    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}
        self._ctl: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ---- queries -------------------------------------------------------------------------
    def list(self) -> list[dict]:
        out = []
        for run in sorted(self.runs.values(), key=lambda r: r.started, reverse=True):
            self._refresh(run)
            out.append(asdict(run))
        return out

    def _active(self, run: Run) -> bool:
        return run.status in ("running", "paused", "stopping")

    def _refresh(self, run: Run) -> None:
        """Experiments: live spend from the session logs; final status once the process exits."""
        if run.kind != "experiment" or not self._active(run):
            return
        ctl = self._ctl[run.id]
        run.spent_usd = _tokens_upper_usd(run.sessions)
        code = ctl["proc"].poll()
        if code is None:
            return
        run.ended = time.time()
        ctl["log"].close()
        if code == 0:
            run.status = "stopped" if (ctl["dir"] / "stop").exists() else "finished"
            try:
                data = json.loads(Path(run.out_file).read_text(encoding="utf-8"))
                run.spent_usd = float(data.get("spent_usd", run.spent_usd))
                run.message = "incomplete (stopped or budget)" if data.get("incomplete") else "complete"
            except (OSError, ValueError, TypeError):
                run.message = "finished without a result file"
        else:
            run.status = "failed"
            run.message = f"exit code {code}; see {run.log_file}"

    # ---- session runs --------------------------------------------------------------------
    def start_session(self, session: str, rounds: int, groups: int, redteam: bool, mock: bool,
                      budget_usd: float, confirm_live: bool = False) -> dict:
        err = self._validate(rounds, groups, budget_usd, live=not mock, confirm=confirm_live)
        if err or not SAFE.match(session):
            return {"status": "rejected", "reason": err or "invalid session id (letters, digits, _ and - only)"}
        with self._lock:
            if any(self._active(r) and session in r.sessions for r in self.runs.values()):
                return {"status": "rejected", "reason": f"a run is already active in session '{session}'"}
            run = Run(id=uuid.uuid4().hex[:8], kind="session", sessions=[session],
                      params={"session": session, "rounds": rounds, "groups": groups, "redteam": redteam,
                              "mock": mock, "budget_usd": budget_usd, "first_round": _next_round(session)})
            ctl = {"pause": threading.Event(), "stop": threading.Event()}
            self.runs[run.id], self._ctl[run.id] = run, ctl
        threading.Thread(target=self._session_loop, args=(run, ctl), daemon=True, name=f"run-{run.id}").start()
        return {"status": "started", "run": asdict(run)}

    def _session_loop(self, run: Run, ctl: dict) -> None:
        from flowforge.orchestrator.round import run_round

        p = run.params
        try:
            for r in range(p["first_round"], p["first_round"] + p["rounds"]):
                while ctl["pause"].is_set() and not ctl["stop"].is_set():
                    run.status = "paused"
                    time.sleep(0.5)
                if ctl["stop"].is_set():
                    run.status = "stopped"
                    run.message = f"stopped by user after {run.rounds_done} round(s)"
                    return
                if run.spent_usd >= p["budget_usd"]:
                    run.status = "budget"
                    run.message = f"budget cap ${p['budget_usd']:.2f} reached"
                    return
                run.status, run.round_now = "running", r
                result = run_round(r, mock=p["mock"], session=p["session"], groups=p["groups"], redteam=p["redteam"])
                run.spent_usd += float(result.get("dollars_spent", 0.0) or 0.0)
                run.rounds_done += 1
                if result.get("status") == "error":
                    run.message = f"round {r} reported an error"
            run.status, run.message = "finished", run.message or "all rounds done"
        except Exception as exc:  # never die silently: the UI shows the reason
            run.status, run.message = "failed", f"{type(exc).__name__}: {exc}"[:300]
        finally:
            run.round_now, run.ended = None, time.time()

    # ---- experiment ----------------------------------------------------------------------
    def start_experiment(self, rounds: int, groups: int, seeds: list[int], budget_usd: float,
                         dry_run: bool, archive_existing: bool = False, confirm_live: bool = False) -> dict:
        err = self._validate(rounds, groups, budget_usd, live=not dry_run, confirm=confirm_live)
        if not err and (len(seeds) != 3 or len(set(seeds)) != 3):
            err = "the protocol needs exactly 3 distinct session seeds"
        if err:
            return {"status": "rejected", "reason": err}
        prefix = "dryrun-" if dry_run else ""
        sessions = [f"{prefix}arms-{arm}-s{s}" for arm in ARMS_SWARM for s in seeds]
        with self._lock:
            if any(self._active(r) and r.kind == "experiment" for r in self.runs.values()):
                return {"status": "rejected", "reason": "an experiment is already running"}
            existing = [s for s in sessions if (Path("runs") / s).exists()]
            if existing and not archive_existing:
                return {"status": "rejected", "needs_archive": existing,
                        "reason": "these sessions already hold events; their history would leak into the new run: "
                                  + ", ".join(existing) + ". Tick 'archive existing sessions' to move them aside."}
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            if existing:
                dest = Path("runs") / f"_archive-{stamp}"
                dest.mkdir(parents=True, exist_ok=True)
                for s in existing:
                    shutil.move(str(Path("runs") / s), str(dest / s))
            rid = uuid.uuid4().hex[:8]
            ctl_dir = Path("runs") / "arms" / f".control-{rid}"
            ctl_dir.mkdir(parents=True, exist_ok=True)
            out = Path("runs") / "arms" / f"{'dryrun' if dry_run else 'arms'}-{stamp}.json"
            log = Path("runs") / "arms" / f"{'dryrun' if dry_run else 'arms'}-{stamp}.log"
            cmd = [sys.executable, str(REPO / "scripts" / "run_arms.py"), "--rounds", str(rounds),
                   "--seeds", ",".join(map(str, seeds)), "--groups", str(groups), "--budget-usd", str(budget_usd),
                   "--out", str(out), "--control-dir", str(ctl_dir)] + (["--dry-run"] if dry_run else [])
            fh = open(log, "w", encoding="utf-8")
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=str(Path.cwd()))
            run = Run(id=rid, kind="experiment", sessions=sessions, out_file=str(out), log_file=str(log),
                      params={"rounds": rounds, "groups": groups, "seeds": seeds, "budget_usd": budget_usd,
                              "dry_run": dry_run, "archived": existing},
                      message=f"archived {len(existing)} old session(s)" if existing else "")
            self.runs[rid], self._ctl[rid] = run, {"proc": proc, "dir": ctl_dir, "log": fh}
        return {"status": "started", "run": asdict(run)}

    # ---- controls ------------------------------------------------------------------------
    def control(self, rid: str, action: str) -> dict:
        run, ctl = self.runs.get(rid), self._ctl.get(rid)
        if run is None or ctl is None:
            return {"status": "rejected", "reason": "unknown run"}
        self._refresh(run)
        if not self._active(run):
            return {"status": "rejected", "reason": f"run is {run.status}"}
        if run.kind == "session":
            if action == "pause":
                ctl["pause"].set(); run.message = "pausing after the current round"
            elif action == "resume":
                ctl["pause"].clear(); run.status, run.message = "running", ""
            elif action == "stop":
                ctl["stop"].set(); ctl["pause"].clear(); run.status = "stopping"
                run.message = "stopping after the current round"
            else:
                return {"status": "rejected", "reason": "session runs support pause, resume, stop"}
        else:
            d: Path = ctl["dir"]
            if action == "pause":
                (d / "pause").write_text("", encoding="utf-8"); run.status = "paused"
                run.message = "pauses before the next round"
            elif action == "resume":
                (d / "pause").unlink(missing_ok=True); run.status, run.message = "running", ""
            elif action == "stop":
                (d / "stop").write_text("", encoding="utf-8"); run.status = "stopping"
                run.message = "stops before the next round; the result file is marked incomplete"
            elif action == "kill":
                ctl["proc"].terminate(); ctl["log"].close(); run.status = "killed"; run.ended = time.time()
                run.message = "killed: no result file; sessions keep the events written so far"
            else:
                return {"status": "rejected", "reason": "unknown action"}
        return {"status": "ok", "run": asdict(run)}

    @staticmethod
    def _validate(rounds: int, groups: int, budget_usd: float, live: bool, confirm: bool) -> str | None:
        if not 1 <= rounds <= MAX_ROUNDS:
            return f"rounds must be 1..{MAX_ROUNDS}"
        if not 1 <= groups <= MAX_GROUPS:
            return f"groups must be 1..{MAX_GROUPS}"
        cap = _session_cap()
        if not 0 < budget_usd <= cap:
            return f"budget must be > 0 and <= the session dollar limit (${cap:.2f}, configs/budgets.yaml)"
        if live and not confirm:
            return "live runs spend API credits: confirm_live is required"
        return None


MANAGER = RunManager()

"""Append-only event log + replay (S4.4).

Log lives at ``runs/<session>/events.jsonl``. Replay
(``FLOWFORGE_REPLAY=1``) never hits the network: a recorded response is
returned for its prompt hash, and any miss is an error. An event that
carries a response but no prompt hash is corrupt: missing hash = error.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def prompt_hash(prompt: str) -> str:
    assert isinstance(prompt, str) and prompt, "prompt must be a non-empty string"
    return hashlib.sha256(prompt.encode()).hexdigest()


class EventLogger:
    """Append-only writer/reader for one session's events.jsonl."""

    def __init__(self, session_dir: Path):
        self.session_dir = Path(session_dir)
        self.path = self.session_dir / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_session(cls, session: str, runs_root: Path = Path("runs")) -> "EventLogger":
        assert session and "/" not in session and "\\" not in session, "bad session id"
        return cls(Path(runs_root) / session)

    def log(self, event: dict) -> None:
        assert isinstance(event, dict), "event must be a dict"
        if "response" in event:
            h = event.get("prompt_hash")
            if not isinstance(h, str) or not h.strip():
                raise ValueError("missing prompt_hash on response event; hash is required")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    def read_events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def replay_lookup(self, p_hash: str) -> dict | None:
        """Return recorded response for p_hash in replay mode.

        Returns None when replay is off. Raises RuntimeError on any miss,
        on an empty hash, or on a response event missing its hash.
        """
        if os.environ.get("FLOWFORGE_REPLAY") != "1":
            return None
        if not isinstance(p_hash, str) or not p_hash.strip():
            raise RuntimeError("Replay requested with missing/empty prompt hash")
        if not self.path.exists():
            raise RuntimeError("Replay requested but events.jsonl is missing")
        match: dict | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            if "response" in ev:
                h = ev.get("prompt_hash")
                if not isinstance(h, str) or not h.strip():
                    raise RuntimeError("Corrupt event log: response event missing prompt_hash")
                if h == p_hash and match is None:
                    resp = ev["response"]
                    assert isinstance(resp, dict), "recorded response must be a dict"
                    match = resp
        if match is not None:
            return match
        raise RuntimeError(f"Replay miss for prompt hash {p_hash}; live calls are forbidden in replay")

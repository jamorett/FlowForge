"""Locked guard + evaluator tests (A3). Temp dirs and fake paths only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from flowforge.data.split_guard import guard_path, guard_swarm_path

ROOT = Path(__file__).resolve().parents[2]


def _locked(tmp_path: Path) -> Path:
    return tmp_path / "data" / "locked" / "square_duct" / "U"


def test_swarm_role_denied_and_logged(tmp_path: Path) -> None:
    log = tmp_path / "runs" / "vault_access.log"
    with pytest.raises(PermissionError):
        guard_swarm_path(_locked(tmp_path), role="theorist", log_path=log)
    text = log.read_text(encoding="utf-8")
    assert "DENIED" in text and "theorist" in text and "locked" in text


@pytest.mark.parametrize("role", ["coder", "analyst", "swarm", "agent"])
def test_all_swarm_roles_denied(tmp_path: Path, role: str) -> None:
    with pytest.raises(PermissionError):
        guard_swarm_path(_locked(tmp_path), role=role,
                         log_path=tmp_path / "vault.log")


def test_evaluator_allowed(tmp_path: Path) -> None:
    p = _locked(tmp_path)
    assert guard_swarm_path(p, role="evaluator",
                            log_path=tmp_path / "vault.log") == p


def test_traversal_denied(tmp_path: Path) -> None:
    sneaky = tmp_path / "data" / "processed" / ".." / "locked" / "x"
    with pytest.raises(PermissionError):
        guard_swarm_path(sneaky, role="coder", log_path=tmp_path / "v.log")
    with pytest.raises(PermissionError):
        guard_path(sneaky, role="evaluator", log_path=tmp_path / "v.log")


def test_my_locked_notes_allowed(tmp_path: Path) -> None:
    p = tmp_path / "my_locked_notes" / "note.txt"
    assert guard_swarm_path(p, role="theorist") == p
    assert guard_path(p, role="theorist") == p


def test_guard_path_still_denies_every_role(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        guard_path(_locked(tmp_path), role="evaluator",
                   log_path=tmp_path / "v.log")


def test_normal_path_allowed(tmp_path: Path) -> None:
    p = tmp_path / "data" / "processed" / "case.npy"
    assert guard_swarm_path(p, role="theorist") == p


def _run_eval(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_locked.py"), *argv],
        cwd=cwd, capture_output=True, text=True, timeout=120)


def test_evaluate_locked_requires_args(tmp_path: Path) -> None:
    assert _run_eval(tmp_path).returncode != 0


def test_evaluate_locked_missing_scores_file_exits_2(tmp_path: Path) -> None:
    result = _run_eval(tmp_path, "--milestone", "1",
                       "--scores-file", str(tmp_path / "nope.json"))
    assert result.returncode == 2


def test_evaluate_locked_records_scores(tmp_path: Path) -> None:
    scores = tmp_path / "scores.json"
    scores.write_text(json.dumps({"candidate_a": 0.91}), encoding="utf-8")
    result = _run_eval(tmp_path, "--milestone", "1",
                       "--scores-file", str(scores), "--reason", "probe")
    assert result.returncode == 0
    assert "candidate_a" in result.stdout
    assert "does not read data/locked" in result.stdout
    log = (tmp_path / "runs" / "vault_access.log").read_text(encoding="utf-8")
    assert "LOCKED_EVAL" in log and "milestone=1" in log and "probe" in log

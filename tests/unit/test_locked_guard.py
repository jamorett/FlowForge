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


def _fake_locked_root(tmp_path: Path) -> Path:
    """Synthetic square_duct store (not real locked data) with one NaN target row."""
    import numpy as np

    from flowforge.data.zarr_store import write_case
    from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis

    rng = np.random.default_rng(0)
    n = 16
    s, w = normalized_tensors(0.1 * rng.standard_normal((n, 3, 3)), np.full(n, 2.0))
    basis = tensor_basis(s, w)
    t1 = basis["T1"]
    target = 0.5 * (t1 - np.trace(t1, axis1=1, axis2=2)[:, None, None] / 3 * np.eye(3))  # trace-free
    target[3] = np.nan
    arrays = {f"invariants/{k}": v for k, v in invariants(s, w).items()}
    arrays.update({f"tensor_basis/{k}": v for k, v in basis.items()})
    arrays["targets/a_delta"] = target
    arrays["targets/Pk_delta"] = np.zeros(n)
    root = tmp_path / "fake_locked"
    write_case(root / "square_duct", arrays)
    return root


def test_candidates_file_is_one_eval_and_masks_nan(tmp_path: Path) -> None:
    root = _fake_locked_root(tmp_path)
    cands = tmp_path / "m1.json"
    cands.write_text(json.dumps({"exact": "0.5 * T1", "zero": "0 * T1"}), encoding="utf-8")
    log = tmp_path / "vault.log"
    result = _run_eval(tmp_path, "--milestone", "1", "--candidates-file", str(cands),
                       "--locked-root", str(root), "--log-file", str(log), "--reason", "probe")
    assert result.returncode == 0, result.stderr
    lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.startswith("LOCKED_EVAL")]
    assert len(lines) == 1 and "mode=direct-set" in lines[0]
    scores = json.loads(lines[0].split("scores=", 1)[1])["candidates"]
    duct = scores["exact"]["cases"]["square_duct"]
    assert duct["n_excluded"] == 1 and duct["error_ratio"] < 1e-12  # NaN row excluded, not NaN
    assert abs(scores["zero"]["cases"]["square_duct"]["error_ratio"] - 1.0) < 1e-12


def test_invalid_candidate_uses_no_evaluation(tmp_path: Path) -> None:
    cands = tmp_path / "bad.json"
    cands.write_text(json.dumps({"bad": "C1 * T1"}), encoding="utf-8")
    log = tmp_path / "vault.log"
    for argv in (("--candidates-file", str(cands)), ("--champion", "I3 * T1")):
        result = _run_eval(tmp_path, "--milestone", "1", *argv,
                           "--locked-root", str(tmp_path / "none"), "--log-file", str(log))
        assert result.returncode == 2
    assert not log.exists()


def test_vault_endpoint_reports_logged_milestones_only(tmp_path, monkeypatch) -> None:
    import flowforge.api.server as srv

    monkeypatch.chdir(tmp_path)
    assert srv.vault_log() == {"evaluations": [], "used": 0, "max": 3}
    log = tmp_path / "runs" / "vault_access.log"
    log.parent.mkdir()
    scores = {"candidates": {"a": {"champion": "0.1 * T1", "cases": {"square_duct": {"error_ratio": 0.5}}}}}
    log.write_text("DENIED role=coder path=data\locked\n"
                   f"LOCKED_EVAL milestone=1 reason=m1 set mode=direct-set timestamp=2026-11-03T17:00:00+00:00 "
                   f"scores={json.dumps(scores)}\n", encoding="utf-8")
    v = srv.vault_log()
    assert v["used"] == 1 and v["evaluations"][0]["reason"] == "m1 set"
    assert v["evaluations"][0]["scores"]["candidates"]["a"]["cases"]["square_duct"]["error_ratio"] == 0.5

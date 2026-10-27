from pathlib import Path

import pytest

import flowforge.data.split_guard as split_guard
from flowforge.data.split_guard import guard_path


def test_locked_path_denied() -> None:
    with pytest.raises(PermissionError):
        guard_path(Path("data/locked/square_duct"), role="theorist")


def test_locked_root_denied() -> None:
    with pytest.raises(PermissionError):
        guard_path(Path("data/locked"), role="coder")


def test_locked_traversal_denied() -> None:
    with pytest.raises(PermissionError):
        guard_path(Path("data/raw/../locked/square_duct/U"), role="analyst")


def test_locked_denial_is_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "runs" / "vault_access.log"
    monkeypatch.setattr(split_guard, "LOG", log)
    with pytest.raises(PermissionError):
        guard_path(Path("data/locked/square_duct"), role="theorist")
    text = log.read_text(encoding="utf-8")
    assert "DENIED" in text and "theorist" in text and "locked" in text


def test_normal_path_allowed(tmp_path: Path) -> None:
    p = tmp_path / "case.npy"
    assert guard_path(p, role="theorist") == p

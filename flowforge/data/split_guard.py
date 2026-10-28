"""Locked-data guard (S4.2). Swarm access to data/locked is refused + logged.

Two enforcement levels:

* :func:`guard_path` — the original strict guard, kept backward
  compatible: any path that resolves into the vault raises
  :class:`PermissionError` for *every* role and appends a ``DENIED``
  line to ``runs/vault_access.log``.
* :func:`guard_swarm_path` — the tool-level boundary the swarm actually
  calls: swarm roles (anything that is not the evaluator) are denied
  any locked path, while the ``evaluator`` role is allowed through.
  Only the dedicated evaluator script may touch the vault.

Paths are resolved with ``Path.resolve(strict=False)`` before the
check, so ``..`` traversal (``data/processed/../locked/...``) and
symlinks cannot smuggle a locked path past the guard. A path counts
as locked when any resolved path component is exactly ``locked``
(case-insensitive); a name that merely contains the word, such as
``my_locked_notes``, is not the vault and is allowed.
"""

from __future__ import annotations

import os
from pathlib import Path

LOCKED = Path("data/locked")
LOG = Path("runs/vault_access.log")

EVALUATOR_ROLE = "evaluator"


def _resolve(p: Path) -> Path:
    try:
        return p.resolve(strict=False)
    except (OSError, RuntimeError):
        return Path(os.path.normpath(os.path.abspath(p)))


def _is_locked(p: Path) -> bool:
    return any(part.casefold() == "locked" for part in p.parts)


def _log_denied(role: str, raw: Path, log_path: Path | None) -> None:
    target = Path(log_path) if log_path is not None else LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(f"DENIED role={role} path={raw}\n")


def guard_path(path: Path, role: str, log_path: Path | None = None) -> Path:
    """Deny every role access to a locked path (backward compatible)."""
    p = Path(path)
    assert role, "role must be a non-empty string"
    if _is_locked(_resolve(p)):
        _log_denied(role, p, log_path)
        raise PermissionError(f"Role {role} may not read locked data: {p}")
    return p


def guard_swarm_path(path: Path, role: str, log_path: Path | None = None) -> Path:
    """Tool-level boundary: deny swarm roles, allow only the evaluator."""
    p = Path(path)
    assert role, "role must be a non-empty string"
    if _is_locked(_resolve(p)) and role.strip().casefold() != EVALUATOR_ROLE:
        _log_denied(role, p, log_path)
        raise PermissionError(f"Role {role} may not read locked data: {p}")
    return p

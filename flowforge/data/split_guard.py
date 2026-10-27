"""Locked-data guard (S4.2). Swarm access to data/locked is refused + logged.

Any path that resolves into ``data/locked/`` (including ``..`` traversal
such as ``data/raw/../locked/...``) raises :class:`PermissionError` and
appends a ``DENIED`` line to ``runs/vault_access.log``. There is no role
allowlist here: only the dedicated evaluator script may touch the vault,
and it does not go through swarm tools.
"""

from __future__ import annotations

from pathlib import Path

LOCKED = Path("data/locked")
LOG = Path("runs/vault_access.log")


def _is_locked(p: Path) -> bool:
    # Normalise without touching the filesystem: fold ``.``/``..`` segments
    # lexically so traversal cannot smuggle a locked path past the check.
    parts: list[str] = []
    for part in p.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part.casefold())
    if "locked" not in parts:
        return False
    # Locked only counts as the vault when it is the ``data/locked`` pair or
    # a bare trailing ``locked`` directory (defence in depth for vault roots
    # mounted elsewhere); this keeps the historical deny-any-``locked`` rule.
    return True


def guard_path(path: Path, role: str) -> Path:
    p = Path(path)
    assert role, "role must be a non-empty string"
    if _is_locked(p):
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"DENIED role={role} path={p}\n")
        raise PermissionError(f"Role {role} may not read locked data: {p}")
    return p

"""Frozen-RANS fields for live scoring (train split).

Live rounds score candidates against ingested frozen-RANS stores under
``data/processed/<case_id>/`` instead of synthetic fields. Each store holds
``invariants/I1..I5``, ``tensor_basis/T1..T4`` and ``targets/a_delta``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = ["load_frozen_fields", "train_case_ids"]

_INVARIANT_KEYS = ("I1", "I2", "I3", "I4", "I5")
_BASIS_KEYS = ("T1", "T2", "T3", "T4")
_TARGET_KEY = "targets/a_delta"


def train_case_ids(root=None) -> list[str]:
    """Return train-split case ids in ``configs/cases.yaml`` order.

    Args:
        root: Optional repo root / configs dir / YAML file passed through to
            :func:`flowforge.config.load_cases`.
    """
    from flowforge.config import load_cases

    data = load_cases(root)
    return [entry["id"] for entry in data["cases"] if entry["split"] == "train"]


def load_frozen_fields(
    case_ids: list[str] | tuple[str, ...],
    processed_dir: str | Path = "data/processed",
    max_points_per_case: int | None = None,
    seed: int = 0,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], np.ndarray]:
    """Load and concatenate frozen-RANS fields for ``case_ids`` in order.

    Args:
        case_ids: Non-empty sequence of case ids, concatenated along axis 0
            in the given order.
        processed_dir: Directory holding one Zarr store per case
            (``<processed_dir>/<case_id>/``).
        max_points_per_case: If set, cases with more points keep a
            deterministic random subset of exactly this many rows (same rows
            for every array of that case; ``numpy.random.default_rng(seed)``;
            subset sorted by original index). Cases with fewer points keep all.
        seed: Seed for the deterministic subset.

    Returns:
        ``(invariants, basis, target)`` where ``invariants`` maps ``I1..I5``
        to ``(N,)`` arrays, ``basis`` maps ``T1..T4`` to ``(N, 3, 3)`` arrays
        and ``target`` is the ``(N, 3, 3)`` ``targets/a_delta`` array.

    Raises:
        ValueError: If ``case_ids`` is empty or ``max_points_per_case`` is
            not a positive int when set.
        FileNotFoundError: If a case store is missing (message contains the
            case id).
        PermissionError: If a store path resolves into ``data/locked``
            (via :func:`flowforge.data.split_guard.guard_swarm_path`).
    """
    from flowforge.data.split_guard import guard_swarm_path
    from flowforge.data.zarr_store import read_case

    if not case_ids:
        raise ValueError("case_ids must be a non-empty sequence")
    ids = list(case_ids)
    if max_points_per_case is not None:
        if isinstance(max_points_per_case, bool) or not isinstance(max_points_per_case, int):
            raise ValueError(f"max_points_per_case must be a positive int, got {max_points_per_case!r}")
        if max_points_per_case <= 0:
            raise ValueError(f"max_points_per_case must be > 0, got {max_points_per_case!r}")

    base = Path(processed_dir)
    store_paths = [base / cid for cid in ids]
    # Guard every path before reading anything so swarm code never touches locked data.
    for store_path in store_paths:
        guard_swarm_path(store_path, role="swarm")

    rng = np.random.default_rng(seed)
    inv_parts: dict[str, list[np.ndarray]] = {k: [] for k in _INVARIANT_KEYS}
    basis_parts: dict[str, list[np.ndarray]] = {k: [] for k in _BASIS_KEYS}
    target_parts: list[np.ndarray] = []
    for cid, store_path in zip(ids, store_paths):
        if not store_path.exists():
            raise FileNotFoundError(f"frozen store missing for case {cid!r}: {store_path}")
        flat = read_case(store_path)
        target = np.asarray(flat[_TARGET_KEY])
        n_points = int(target.shape[0])
        if max_points_per_case is not None and n_points > max_points_per_case:
            idx = np.sort(rng.choice(n_points, size=max_points_per_case, replace=False))
        else:
            idx = None
        for key in _INVARIANT_KEYS:
            arr = np.asarray(flat[f"invariants/{key}"])
            inv_parts[key].append(arr[idx] if idx is not None else arr)
        for key in _BASIS_KEYS:
            arr = np.asarray(flat[f"tensor_basis/{key}"])
            basis_parts[key].append(arr[idx] if idx is not None else arr)
        target_parts.append(target[idx] if idx is not None else target)

    invariants = {k: np.concatenate(v, axis=0) for k, v in inv_parts.items()}
    basis = {k: np.concatenate(v, axis=0) for k, v in basis_parts.items()}
    target_all = np.concatenate(target_parts, axis=0)
    return invariants, basis, target_all

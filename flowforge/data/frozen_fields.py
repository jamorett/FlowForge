"""Frozen-RANS fields for live scoring (train split).

Live rounds score candidates against ingested frozen-RANS stores under
``data/processed/<case_id>/`` instead of synthetic fields. Each store holds
``invariants/I1..I5``, ``tensor_basis/T1..T4`` and ``targets/a_delta``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = [
    "load_frozen_fields",
    "score_expression",
    "score_on_cases",
    "train_case_ids",
    "validation_case_ids",
    "worst_ratio",
]

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


def validation_case_ids(root=None) -> list[str]:
    """Return validation-split case ids in ``configs/cases.yaml`` order.

    Args:
        root: Optional repo root / configs dir / YAML file passed through to
            :func:`flowforge.config.load_cases`.
    """
    from flowforge.config import load_cases

    data = load_cases(root)
    return [entry["id"] for entry in data["cases"] if entry["split"] == "validation"]


def score_expression(
    expression: str,
    invariants: dict[str, np.ndarray],
    basis: dict[str, np.ndarray],
    target: np.ndarray,
) -> dict[str, float | int]:
    """Score ``expression`` a priori against ``target``.

    Rows whose target contains any non-finite value are excluded from both
    ``mse`` and ``mse_zero``.

    Args:
        expression: DSL expression for the anisotropy correction.
        invariants: Mapping ``I1..I5`` to ``(N,)`` arrays.
        basis: Mapping ``T1..T4`` to ``(N, 3, 3)`` arrays.
        target: ``(N, 3, 3)`` frozen-RANS anisotropy correction.

    Returns:
        ``{"mse", "mse_zero", "ratio", "n_used", "n_excluded"}``
        where ``mse`` is the mean squared error on used rows, ``mse_zero``
        is the MSE of no correction on used rows (``mean(target**2)``),
        ``ratio = mse / mse_zero``, ``n_used`` is the number of rows used
        and ``n_excluded`` is the number of rows excluded for non-finite
        targets. A non-finite prediction on any used row yields
        ``mse=inf`` and ``ratio=inf``.

    Raises:
        ValueError: If no row has a finite target.
    """
    from flowforge.dsl.evaluate import candidate_anisotropy

    pred = candidate_anisotropy(expression, invariants, basis)
    target_arr = np.asarray(target, dtype=float)
    pred_arr = np.asarray(pred, dtype=float)
    if target_arr.ndim == 0:
        raise ValueError("no usable rows: target has no rows")
    if target_arr.ndim == 1:
        finite_mask = np.isfinite(target_arr)
    else:
        finite_mask = np.isfinite(target_arr).reshape(target_arr.shape[0], -1).all(axis=1)
    n_used = int(np.count_nonzero(finite_mask))
    n_excluded = int(target_arr.shape[0] - n_used)
    if n_used == 0:
        raise ValueError("no usable rows: all targets are non-finite")
    target_used = target_arr[finite_mask]
    pred_used = pred_arr[finite_mask]
    mse_zero = float(np.mean(target_used**2))
    if not bool(np.all(np.isfinite(pred_used))):
        return {
            "mse": float("inf"),
            "mse_zero": mse_zero,
            "ratio": float("inf"),
            "n_used": n_used,
            "n_excluded": n_excluded,
        }
    mse = float(np.mean((pred_used - target_used) ** 2))
    if mse_zero == 0.0:
        ratio = 0.0 if mse == 0.0 else float("inf")
    else:
        ratio = float(mse / mse_zero)
    return {"mse": mse, "mse_zero": mse_zero, "ratio": ratio, "n_used": n_used, "n_excluded": n_excluded}


def worst_ratio(scores: dict[str, dict]) -> float | None:
    """Return the worst (max) validation ``ratio``.

    Args:
        scores: Mapping ``case_id -> score dict`` as produced by
            :func:`score_on_cases`.

    Returns:
        The maximum ``ratio`` over cases without an ``"error"`` key, or
        ``None`` when no case has a ratio.

    Raises:
        ValueError: If any non-error ratio is NaN (a NaN score must never
            be silently skipped).
    """
    ratios: list[float] = []
    for entry in scores.values():
        if "error" in entry:
            continue
        if "ratio" not in entry:
            continue
        value = float(entry["ratio"])
        if np.isnan(value):
            raise ValueError("NaN ratio must never be skipped")
        ratios.append(value)
    if not ratios:
        return None
    return max(ratios)


def score_on_cases(
    expression: str,
    case_ids: list[str] | tuple[str, ...],
    processed_dir: str | Path = "data/processed",
    max_points_per_case: int | None = 4000,
    seed: int = 0,
) -> dict[str, dict]:
    """Score ``expression`` separately on each case in ``case_ids``.

    Each case is loaded with :func:`load_frozen_fields` (single-case load)
    and scored with :func:`score_expression`.

    Args:
        expression: DSL expression to score.
        case_ids: Case ids to score, in order.
        processed_dir: Directory holding one Zarr store per case.
        max_points_per_case: Deterministic subset size per case.
        seed: Seed for the deterministic subset.

    Returns:
        Mapping ``case_id -> {"mse", "mse_zero", "ratio", "n_used",
        "n_excluded"}``. A case that cannot be loaded
        (``FileNotFoundError``) or scored (``ValueError``, ``KeyError``)
        yields ``{"error": "<message>"}`` for that case.
        ``PermissionError`` (locked data) propagates.
    """
    scores: dict[str, dict] = {}
    for case_id in list(case_ids):
        try:
            inv, basis, target = load_frozen_fields(
                [case_id],
                processed_dir=processed_dir,
                max_points_per_case=max_points_per_case,
                seed=seed,
            )
        except FileNotFoundError as exc:
            scores[case_id] = {"error": str(exc)}
            continue
        try:
            scores[case_id] = score_expression(expression, inv, basis, target)
        except (ValueError, KeyError) as exc:
            scores[case_id] = {"error": str(exc)}
    return scores

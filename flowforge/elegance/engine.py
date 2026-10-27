"""Elegance engine (S3.4): rung-0 filters, description length, snapping, champion."""

from __future__ import annotations

import math

import numpy as np

SNAP_CANDIDATES = (0.0, 1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 0.333, -0.333, 1.5, -1.5)
VOCAB_SIZE = 16
SNAP_TOLERANCE = 0.01  # keep snap only if worst-case error rises <= 1%
CHAMPION_MARGIN = 0.03  # champion: lowest DL within 3% of best worst-case error


def description_length(n_nodes: int, constants: list[float]) -> float:
    bits_consts = sum(max(1.0, math.log2(abs(c) * 10 + 1)) for c in constants)
    return n_nodes * math.log2(VOCAB_SIZE) + bits_consts


def try_snap(value: float, error_before: float, error_after_fn) -> float:
    """Return snapped value if worst-case error rises <=1%, else original."""
    best = value
    for cand in sorted(SNAP_CANDIDATES, key=lambda c: abs(c - value)):
        err = error_after_fn(cand)
        if err <= (1.0 + SNAP_TOLERANCE) * error_before:
            best = cand
            break
    return best


def snap_value(value: float, error_before: float, error_after_fn) -> float:
    return try_snap(value, error_before, error_after_fn)


def pick_champion(candidates: list[dict]) -> dict:
    """candidates: {id, worst_error, dl}. Within 3% of best -> min DL."""
    assert candidates, "no candidates to pick from"
    best_err = min(c["worst_error"] for c in candidates)
    pool = [c for c in candidates if c["worst_error"] <= (1.0 + CHAMPION_MARGIN) * best_err]
    return min(pool, key=lambda c: c["dl"])


def zero_strain_ok(eval_at_zero: float, tol: float = 1e-8) -> bool:
    return abs(eval_at_zero) <= tol


def rotation_invariant(fn, x: np.ndarray, seed: int = 42) -> bool:
    """Rung-0 rotation test: fn(Q x Q^T) == Q fn(x) Q^T for a random rotation Q."""
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((3, 3))
    q, _ = np.linalg.qr(a)
    if np.linalg.det(q) < 0:  # force a proper rotation (det = +1), not a reflection
        q[:, 0] = -q[:, 0]
    assert np.allclose(q @ q.T, np.eye(3), atol=1e-10), "Q must be orthogonal"
    assert np.linalg.det(q) > 0, "Q must be a proper rotation"
    return bool(np.allclose(fn(q @ x @ q.T), q @ fn(x) @ q.T, atol=1e-8))


# Descriptive aliases for the rung-0 rotation test.
check_rotation_invariance = rotation_invariant
rotation_test = rotation_invariant

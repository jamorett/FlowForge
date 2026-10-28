"""Elegance engine (S3.4): rung-0 filters, description length, snapping, champion."""

from __future__ import annotations

import math

import numpy as np

from flowforge.composer.gates import GATE_DL_PENALTY_BITS, total_dl_penalty_bits

SNAP_CANDIDATES = (0.0, 1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 0.333, -0.333, 1.5, -1.5)
VOCAB_SIZE = 16
SNAP_TOLERANCE = 0.01  # keep snap only if worst-case error rises <= 1%
CHAMPION_MARGIN = 0.03  # champion: lowest DL within 3% of best worst-case error


def description_length(n_nodes: int, constants: list[float], n_gates: int = 0,
                       gate_penalty_bits: float | None = None,
                       dl_penalty_bits: float | None = None,
                       penalty_bits: float | None = None) -> float:
    """Description length in bits, including the 16-bit-per-gate penalty.

    Backward compatible: ``description_length(n_nodes, constants)`` is the
    old ungated value. A gated composite pays via ``n_gates`` (16 bits per
    gate, from ``flowforge.composer.gates``) or via an explicit penalty
    (``gate_penalty_bits`` / ``dl_penalty_bits`` / ``penalty_bits``, e.g.
    the ``dl_penalty_bits`` returned by ``evaluate_composition``).
    """
    if n_gates < 0:
        raise ValueError("n_gates must be >= 0")
    bits_consts = sum(max(1.0, math.log2(abs(c) * 10 + 1)) for c in constants)
    base = n_nodes * math.log2(VOCAB_SIZE) + bits_consts
    explicit = gate_penalty_bits
    if explicit is None:
        explicit = dl_penalty_bits
    if explicit is None:
        explicit = penalty_bits
    penalty = float(explicit) if explicit is not None else total_dl_penalty_bits(int(n_gates))
    return base + penalty


def _effective_dl(candidate: dict, gate_dl_penalty_bits: float) -> float:
    """DL used for champion ranking: base ``dl`` plus any gate penalty.

    Candidates may carry the penalty as ``dl_penalty_bits`` /
    ``gate_penalty_bits`` / ``penalty_bits`` (added once) or as ``n_gates``
    (16 bits each). A candidate whose ``dl`` already includes the penalty
    (e.g. built with ``description_length(..., n_gates=...)``) should not
    also carry those fields. Candidates with only a precomputed
    ``composite_dl`` / ``total_dl`` / ``effective_dl`` use it as-is.
    """
    if "dl" in candidate:
        base = float(candidate["dl"])
        explicit = None
        for key in ("dl_penalty_bits", "gate_penalty_bits", "penalty_bits"):
            if key in candidate:
                explicit = float(candidate[key])
                break
        if explicit is not None:
            return base + explicit
        if "n_gates" in candidate:
            return base + float(candidate["n_gates"]) * float(gate_dl_penalty_bits)
        return base
    for key in ("effective_dl", "composite_dl", "total_dl"):
        if key in candidate:
            return float(candidate[key])
    raise KeyError("candidate needs 'dl' (or a precomputed composite/effective DL)")


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


def pick_champion(candidates: list[dict],
                  gate_dl_penalty_bits: float = GATE_DL_PENALTY_BITS) -> dict:
    """candidates: {id, worst_error, dl[, dl_penalty_bits|n_gates]}.

    Within 3% of best worst-case error -> min *effective* DL, where the
    effective DL adds each candidate's 16-bit-per-gate penalty (see
    ``_effective_dl``) so a gated composite pays for its gates.
    """
    assert candidates, "no candidates to pick from"
    best_err = min(c["worst_error"] for c in candidates)
    pool = [c for c in candidates if c["worst_error"] <= (1.0 + CHAMPION_MARGIN) * best_err]
    return min(pool, key=lambda c: _effective_dl(c, gate_dl_penalty_bits))


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

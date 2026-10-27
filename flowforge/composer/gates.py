"""Gated composer (S6.2). Every gate pays +16 bits description length.

Formula (spec S6.2):
    a_comp = sigmoid(w * I + b) * M1 + (1 - sigmoid(w * I + b)) * M2
where I is a scalar invariant field per point, M1/M2 are module tensors
(e.g. (N, 3, 3) anisotropy corrections). No free gating.
"""

from __future__ import annotations

import numpy as np

GATE_DL_PENALTY_BITS = 16.0


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def total_dl_penalty_bits(n_gates: int) -> float:
    assert n_gates >= 0
    return GATE_DL_PENALTY_BITS * n_gates


def compose(a1: np.ndarray, a2: np.ndarray, gate_input: np.ndarray,
            w: float, b: float) -> tuple[np.ndarray, float]:
    """Return (composite, dl_penalty_bits). gate_input is I, shape (N,) or matching."""
    a1 = np.asarray(a1, dtype=float)
    a2 = np.asarray(a2, dtype=float)
    gate_input = np.asarray(gate_input, dtype=float)
    assert a1.shape == a2.shape, f"module shapes differ {a1.shape} vs {a2.shape}"
    assert np.all(np.isfinite(a1)) and np.all(np.isfinite(a2)), "non-finite module"
    assert np.all(np.isfinite(gate_input)), "non-finite gate input"
    assert np.isfinite(w) and np.isfinite(b), "non-finite gate params"
    g = sigmoid(w * gate_input + b)
    assert np.all((g >= 0.0) & (g <= 1.0)), "gate outside [0, 1]"
    if a1.ndim > gate_input.ndim:
        # Broadcast scalar gate per point over trailing tensor dims (e.g. 3x3).
        assert a1.shape[: gate_input.ndim] == gate_input.shape or gate_input.ndim == 0, (
            f"gate {gate_input.shape} cannot broadcast over {a1.shape}"
        )
        extra = g.reshape(g.shape + (1,) * (a1.ndim - gate_input.ndim))
    else:
        extra = g
    composite = extra * a1 + (1.0 - extra) * a2
    assert composite.shape == a1.shape
    assert np.all(np.isfinite(composite)), "non-finite composite"
    return composite, GATE_DL_PENALTY_BITS

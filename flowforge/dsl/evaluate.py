"""Compile a validated DSL expression to a NumPy evaluator over invariants."""

from __future__ import annotations

import numpy as np
import sympy as sp

from flowforge.dsl.parser import INVARIANTS, validate_candidate


def compile_evaluator(expression: str):
    """Return f(I1..I5 arrays) -> array. Raises on cap/grammar violations."""
    expr = validate_candidate(expression)
    fn = sp.lambdify(INVARIANTS, expr, modules="numpy")

    def evaluate(*invariant_arrays: np.ndarray) -> np.ndarray:
        assert len(invariant_arrays) == 5, "need I1..I5"
        shapes = {a.shape for a in invariant_arrays}
        assert len(shapes) == 1, f"invariant shape mismatch: {shapes}"
        out = fn(*invariant_arrays)
        return np.broadcast_to(np.asarray(out, dtype=float), invariant_arrays[0].shape).copy()

    return evaluate


def candidate_anisotropy(expression: str, invariants: dict[str, np.ndarray],
                         basis: dict[str, np.ndarray]) -> np.ndarray:
    """a_delta = g(I) * T1 with g from the expression (single-term form)."""
    ev = compile_evaluator(expression)
    g = ev(invariants["I1"], invariants["I2"], invariants["I3"],
           invariants["I4"], invariants["I5"])
    t1 = basis["T1"]
    raw = g[..., None, None] * t1
    # Project to symmetric, traceless (deviatoric) anisotropy by construction.
    sym = 0.5 * (raw + np.swapaxes(raw, -1, -2))
    trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
    result = sym - (1.0 / 3.0) * trace * np.eye(3)
    assert np.allclose(result, np.swapaxes(result, -1, -2), atol=1e-10), "a_delta must be symmetric"
    assert np.allclose(np.trace(result, axis1=-2, axis2=-1), 0, atol=1e-10), "a_delta must be traceless"
    return result

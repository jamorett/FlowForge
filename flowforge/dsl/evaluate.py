"""Compile a validated DSL expression to a NumPy evaluator."""
from __future__ import annotations

import numpy as np
import sympy as sp

from flowforge.dsl.parser import INVARIANTS, tensor_coefficients, validate_candidate


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

def _eval_coeff(coeff: sp.Expr, invariants: dict[str, np.ndarray]) -> np.ndarray:
    fn = sp.lambdify(INVARIANTS, coeff, modules="numpy")
    out = fn(invariants["I1"], invariants["I2"], invariants["I3"], invariants["I4"], invariants["I5"])
    ref = np.asarray(invariants["I1"], dtype=float)
    return np.broadcast_to(np.asarray(out, dtype=float), ref.shape).copy()

def candidate_anisotropy(expression: str, invariants: dict[str, np.ndarray], basis: dict[str, np.ndarray]) -> np.ndarray:
    """a_delta = dev(sum_k g_k(I) * T_k); T-free part folded into T1.

    Validated with ``validate_candidate`` (via ``tensor_coefficients``),
    so grammar violations and the 25-node cap raise ``ValueError``.
    """
    coeffs = tensor_coefficients(expression)
    if not coeffs:
        ref = np.asarray(invariants["I1"], dtype=float)
        return np.zeros(ref.shape + (3, 3), dtype=float)
    raw = None
    for name, coeff in coeffs.items():
        if name not in basis:
            raise KeyError(f"Tensor {name} used in {expression!r} is missing from basis")
        term = _eval_coeff(coeff, invariants)[..., None, None] * np.asarray(basis[name], dtype=float)
        raw = term if raw is None else raw + term
    assert raw is not None
    sym = 0.5 * (raw + np.swapaxes(raw, -1, -2))
    trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
    result = sym - (1.0 / 3.0) * trace * np.eye(3)
    assert np.allclose(result, np.swapaxes(result, -1, -2), atol=1e-10), "a_delta must be symmetric"
    assert np.allclose(np.trace(result, axis1=-2, axis2=-1), 0, atol=1e-10), "a_delta must be traceless"
    return result

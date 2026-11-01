"""Compile a validated DSL expression to a NumPy evaluator over invariants and tensor bases."""

from __future__ import annotations

import numpy as np
import sympy as sp

from flowforge.dsl.grammar import INVARIANTS
from flowforge.dsl.parser import decompose_candidate, validate_candidate


def compile_evaluator(expression: str):
    """Return f(I1..I5 arrays) -> array. Raises on cap/grammar violations."""
    expr = validate_candidate(expression)
    coeffs = decompose_candidate(expr)
    scalar_expr = coeffs["T1"]
    fn = sp.lambdify(INVARIANTS, scalar_expr, modules="numpy")

    def evaluate(*invariant_arrays: np.ndarray) -> np.ndarray:
        assert len(invariant_arrays) == 5, "need I1..I5"
        shapes = {a.shape for a in invariant_arrays}
        assert len(shapes) == 1, f"invariant shape mismatch: {shapes}"
        out = fn(*invariant_arrays)
        return np.broadcast_to(np.asarray(out, dtype=float), invariant_arrays[0].shape).copy()

    return evaluate


def compile_earsm_evaluator(expression: str):
    """Compile EARSM candidate to f(invariants_dict, basis_dict) -> np.ndarray (..., 3, 3)."""
    expr = validate_candidate(expression)
    coeffs = decompose_candidate(expr)
    lambdas = {}
    for name, c in coeffs.items():
        if c == 0:
            lambdas[name] = None
        else:
            lambdas[name] = sp.lambdify(INVARIANTS, c, modules="numpy")

    def evaluate(invariants: dict[str, np.ndarray], basis: dict[str, np.ndarray]) -> np.ndarray:
        inv_args = [invariants[str(s)] for s in INVARIANTS]
        shape = inv_args[0].shape
        out = np.zeros(shape + (3, 3), dtype=float)
        for name, fn in lambdas.items():
            if fn is None:
                continue
            if name not in basis:
                raise KeyError(f"Candidate requires basis tensor {name!r}, but only {sorted(basis)} provided")
            val = fn(*inv_args)
            g_arr = np.broadcast_to(np.asarray(val, dtype=float), shape)
            out += g_arr[..., None, None] * basis[name]
        # Project to symmetric, traceless (deviatoric) anisotropy by construction.
        sym = 0.5 * (out + np.swapaxes(out, -1, -2))
        trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
        result = sym - (1.0 / 3.0) * trace * np.eye(3)
        assert np.allclose(result, np.swapaxes(result, -1, -2), atol=1e-10), "a_delta must be symmetric"
        assert np.allclose(np.trace(result, axis1=-2, axis2=-1), 0, atol=1e-10), "a_delta must be traceless"
        return result

    return evaluate


def candidate_anisotropy(expression: str, invariants: dict[str, np.ndarray],
                         basis: dict[str, np.ndarray]) -> np.ndarray:
    """Evaluate candidate anisotropy correction: a_delta = sum_k g^(k)(I) * T_k."""
    ev = compile_earsm_evaluator(expression)
    return ev(invariants, basis)


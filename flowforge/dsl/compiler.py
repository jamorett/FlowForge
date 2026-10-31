"""Closure DSL compiler (S3): SymPy -> NumPy evaluator and C++ snippet.

Both backends consume only parser-validated expressions, so every division in
generated code is the guarded div(a, b) = a / (b**2 + 1e-4) and every root is
sqrt(abs(a) + 1e-4). Complexity cap (<= 25 nodes) is enforced on entry.
"""

from __future__ import annotations

import numpy as np
import sympy as sp
from sympy.printing.cxx import CXX11CodePrinter

from flowforge.dsl.grammar import INVARIANTS, TENSORS
from flowforge.dsl.parser import complexity, validate_candidate

_PRINTER = CXX11CodePrinter()
_TENSOR_SET = set(TENSORS)


def _reject_tensors(expr: sp.Expr, expression: str) -> None:
    """Reject solver codegen for tensor-basis candidates."""
    if expr.free_symbols & _TENSOR_SET:
        raise ValueError(f"Tensor symbols T1..T4 not supported by solver code generation in {expression!r}; use scalar g(I)")


def compile_numpy(expression: str):
    """Return f(I1, I2, I3, I4, I5) -> np.ndarray (broadcast, float)."""
    expr = validate_candidate(expression)
    _reject_tensors(expr, expression)
    fn = sp.lambdify(INVARIANTS, expr, modules="numpy")

    def evaluate(*invariant_arrays) -> np.ndarray:
        assert len(invariant_arrays) == 5, "need I1..I5"
        arrays = [np.asarray(a, dtype=float) for a in invariant_arrays]
        shapes = {a.shape for a in arrays}
        assert len(shapes) == 1, f"invariant shape mismatch: {shapes}"
        out = fn(*arrays)
        return np.broadcast_to(np.asarray(out, dtype=float), arrays[0].shape).copy()

    return evaluate


def compile_cpp(expression: str, out_name: str = "g") -> str:
    """Return a C++ snippet assigning the validated expression to out_name."""
    expr = validate_candidate(expression)
    _reject_tensors(expr, expression)
    cxx = _PRINTER.doprint(expr, assign_to=out_name)[0]
    lines = [f"// generated from: {expression}", "#pragma once"]
    for sym in INVARIANTS:
        lines.append(f"// input scalar field: {sym}")
    lines.append(cxx)
    return "\n".join(lines) + "\n"


def compile_candidate(expression: str) -> dict:
    """Compile both backends; returns {expr, complexity, numpy_fn, cpp}."""
    expr = validate_candidate(expression)
    _reject_tensors(expr, expression)
    return {
        "expr": expr,
        "complexity": complexity(expr),
        "numpy_fn": compile_numpy(expression),
        "cpp": compile_cpp(expression),
    }

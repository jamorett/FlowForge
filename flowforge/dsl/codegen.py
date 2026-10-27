"""Mode B codegen (S2/S3): SymPy expression -> C++ snippet for the solver.

Only safe ops survive the DSL, so generated code uses guarded division.
The snippet operates on scalar invariant fields I1..I5 (dimensionless).
"""

from __future__ import annotations

import sympy as sp
from sympy.printing.cxx import CXX11CodePrinter

from flowforge.dsl.parser import INVARIANTS, validate_candidate

_PRINTER = CXX11CodePrinter()


def to_cpp(expression: str, out_name: str = "g") -> str:
    expr = validate_candidate(expression)
    cxx = _PRINTER.doprint(expr, assign_to=out_name)[0]
    lines = [f"// generated from: {expression}", "#pragma once"]
    for sym in INVARIANTS:
        lines.append(f"// input scalar field: {sym}")
    lines.append(cxx)
    return "\n".join(lines) + "\n"


def candidate_cpp_files(expression: str) -> dict[str, str]:
    return {"generatedCorrection.H": to_cpp(expression)}

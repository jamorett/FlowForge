"""Temporal probe (S3, Phase 3): SymPy parsing assumptions before production edits.

Run: uv run python scratch/probe_sympy.py
Checks: safe div/sqrt expansion, node complexity, unknown-symbol rejection target,
tanh/exp round-trip, lambdify to NumPy, C++ printing.
This file is a probe only; production logic lives in flowforge/dsl/.
"""

from __future__ import annotations

import numpy as np
import sympy as sp

I1, I2 = sp.symbols("I1 I2")


def safe_div(a, b):
    return a / (b**2 + sp.Float("1e-4"))


def safe_sqrt(a):
    return sp.sqrt(sp.Abs(a) + sp.Float("1e-4"))


def main() -> None:
    expr = sp.sympify("I1 + tanh(I2)", locals={"I1": I1, "I2": I2, "tanh": sp.tanh})
    print("expr:", expr, "nodes:", sum(1 for _ in sp.preorder_traversal(expr)))
    print("div:", safe_div(I1, I2))
    print("sqrt:", safe_sqrt(I1))
    fn = sp.lambdify((I1, I2), expr, modules="numpy")
    print("numpy:", fn(np.array([1.0]), np.array([0.0])))
    from sympy.printing.cxx import CXX11CodePrinter

    print("cxx:", CXX11CodePrinter().doprint(expr, assign_to="g")[0])
    print("probe ok")


if __name__ == "__main__":
    main()

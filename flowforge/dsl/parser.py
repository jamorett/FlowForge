"""Closure DSL parser (S3.3). Safe ops only; complexity cap 25.

Grammar lives in flowforge.dsl.grammar: invariants I1..I5, numeric constants,
+ - * div tanh exp sqrt, integer powers. Raw / is forbidden;
div(a,b)=a/(b^2+1e-4), sqrt(a)=sqrt(|a|+1e-4).
"""

from __future__ import annotations

import sympy as sp

from flowforge.dsl.grammar import (
    ALLOWED_FUNCTIONS,
    ALL_SYMBOLS,
    BASIS_NAMES,
    BASIS_SYMBOLS,
    INVARIANTS,
    MAX_COMPLEXITY,
    safe_div,
    safe_sqrt,
)

MAX_NODES = MAX_COMPLEXITY
MAX_TENSOR_NODES = 35
_ALLOWED_FUNCS = {"tanh": sp.tanh, "exp": sp.exp}


def _safe_sqrt(x):
    return safe_sqrt(x)


def _safe_div(a, b):
    return safe_div(a, b)


def decompose_candidate(expr: sp.Expr) -> dict[str, sp.Expr]:
    """Decompose an expression into EARSM tensor coefficients g^(1)..g^(4).

    Returns a dict mapping 'T1'..'T4' to scalar SymPy expressions in invariants I1..I5.
    If expr contains no basis symbols, it is assigned to 'T1' by default (single-term form).
    """
    has_tensors = any(t in expr.free_symbols for t in BASIS_SYMBOLS)
    if not has_tensors:
        return {
            "T1": expr,
            "T2": sp.Integer(0),
            "T3": sp.Integer(0),
            "T4": sp.Integer(0),
        }
    coeffs = {}
    rem = expr
    for name, t in zip(BASIS_NAMES, BASIS_SYMBOLS):
        c = expr.coeff(t)
        coeffs[name] = c
        rem = rem - c * t
    rem = sp.simplify(rem)
    if rem != 0:
        raise ValueError(f"Unattached scalar or non-linear basis terms: remainder={rem}")
    for name, c in coeffs.items():
        unknown = c.free_symbols - set(INVARIANTS)
        if unknown:
            raise ValueError(f"Basis tensor {name} coefficient contains invalid symbols: {unknown}")
    return coeffs


def _validate_tree(expr: sp.Expr, text: str) -> None:
    unknown = expr.free_symbols - set(ALL_SYMBOLS)
    if unknown:
        raise ValueError(f"Unknown symbols {sorted(map(str, unknown))} in {text!r}; only I1..I5 and T1..T4 allowed")
    for node in sp.preorder_traversal(expr):
        func = getattr(node, "func", None)
        if func is not None and isinstance(node, sp.Function):
            if func not in ALLOWED_FUNCTIONS:
                raise ValueError(f"Function {func.__name__} not allowed in {text!r}")
            if any(t in node.free_symbols for t in BASIS_SYMBOLS):
                raise ValueError(f"Basis tensor not allowed inside function {func.__name__} in {text!r}")
        if isinstance(node, sp.Pow):
            if any(t in node.free_symbols for t in BASIS_SYMBOLS):
                raise ValueError(f"Basis tensor powers not allowed in {text!r}")
            exp = node.exp
            is_half = (exp == sp.Rational(1, 2) or exp == sp.Float(0.5))
            if is_half:
                base = node.base
                guarded = isinstance(base, sp.Add) and any(
                    term == sp.Float("1e-4") or term == sp.Rational(1, 10000) for term in base.args
                )
                if not guarded:
                    raise ValueError(f"Unguarded square root in {text!r}; use sqrt(a)")
            elif not isinstance(exp, sp.Integer):
                raise ValueError(f"Only integer powers allowed in {text!r}")
            elif int(exp) < 0:
                # Only guarded division may invert: (b**2 + 1e-4) ** -1 from div().
                base = node.base
                guarded = int(exp) == -1 and isinstance(base, sp.Add) and any(
                    term == sp.Float("1e-4") or term == sp.Rational(1, 10000) for term in base.args
                )
                if not guarded:
                    raise ValueError(f"Unguarded negative power in {text!r}; use div(a, b)")
    if any(t in expr.free_symbols for t in BASIS_SYMBOLS):
        decompose_candidate(expr)


def parse_expression(text: str) -> sp.Expr:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Expression must be a non-empty string")
    local = {str(s): s for s in ALL_SYMBOLS}
    local.update(_ALLOWED_FUNCS)
    local["sqrt"] = _safe_sqrt
    local["div"] = _safe_div
    if "/" in text.replace("div", ""):
        raise ValueError("Raw / is forbidden; use div(a, b)")
    try:
        expr = sp.sympify(text, locals=local)
    except (sp.SympifyError, SyntaxError, TypeError) as exc:
        raise ValueError(f"Cannot parse expression {text!r}: {exc}") from exc
    if not isinstance(expr, sp.Expr):
        raise ValueError(f"Cannot parse expression {text!r}")
    _validate_tree(expr, text)
    return expr


def complexity(expr: sp.Expr) -> int:
    return sum(1 for _ in sp.preorder_traversal(expr))


def validate_candidate(text: str) -> sp.Expr:
    local = {str(s): s for s in ALL_SYMBOLS}
    local.update(_ALLOWED_FUNCS)
    local["sqrt"] = _safe_sqrt
    local["div"] = _safe_div
    has_tensors = any(name in text for name in BASIS_NAMES)
    cap = MAX_TENSOR_NODES if has_tensors else MAX_NODES
    try:
        raw_expr = sp.sympify(text, locals=local, evaluate=False)
        raw_n = sum(1 for _ in sp.preorder_traversal(raw_expr))
        if raw_n > cap:
            raise ValueError(f"Complexity {raw_n} exceeds cap {cap}")
    except (sp.SympifyError, SyntaxError, TypeError):
        pass
    expr = parse_expression(text)
    n = complexity(expr)
    if n > cap:
        raise ValueError(f"Complexity {n} exceeds cap {cap}")
    return expr


"""Closure DSL parser (S3.3). Safe ops only; complexity cap 25.

Grammar lives in flowforge.dsl.grammar: invariants I1..I5, numeric constants,
+ - * div tanh exp sqrt, integer powers. Raw / is forbidden;
div(a,b)=a/(b^2+1e-4), sqrt(a)=sqrt(|a|+1e-4).
"""

from __future__ import annotations

import sympy as sp

from flowforge.dsl.grammar import (
    ALLOWED_FUNCTIONS,
    INVARIANTS,
    MAX_COMPLEXITY,
    safe_div,
    safe_sqrt,
)

MAX_NODES = MAX_COMPLEXITY
_ALLOWED_FUNCS = {"tanh": sp.tanh, "exp": sp.exp}


def _safe_sqrt(x):
    return safe_sqrt(x)


def _safe_div(a, b):
    return safe_div(a, b)


def _validate_tree(expr: sp.Expr, text: str) -> None:
    unknown = expr.free_symbols - set(INVARIANTS)
    if unknown:
        raise ValueError(f"Unknown symbols {sorted(map(str, unknown))} in {text!r}; only I1..I5 allowed")
    for node in sp.preorder_traversal(expr):
        func = getattr(node, "func", None)
        if func is not None and isinstance(node, sp.Function):
            if func not in ALLOWED_FUNCTIONS:
                raise ValueError(f"Function {func.__name__} not allowed in {text!r}")
        if isinstance(node, sp.Pow):
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


def parse_expression(text: str) -> sp.Expr:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Expression must be a non-empty string")
    local = {str(s): s for s in INVARIANTS}
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
    local = {str(s): s for s in INVARIANTS}
    local.update(_ALLOWED_FUNCS)
    local["sqrt"] = _safe_sqrt
    local["div"] = _safe_div
    try:
        raw_expr = sp.sympify(text, locals=local, evaluate=False)
        raw_n = sum(1 for _ in sp.preorder_traversal(raw_expr))
        if raw_n > MAX_NODES:
            raise ValueError(f"Complexity {raw_n} exceeds cap {MAX_NODES}")
    except (sp.SympifyError, SyntaxError, TypeError):
        pass
    expr = parse_expression(text)
    n = complexity(expr)
    if n > MAX_NODES:
        raise ValueError(f"Complexity {n} exceeds cap {MAX_NODES}")
    return expr


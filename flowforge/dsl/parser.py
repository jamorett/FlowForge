"""Closure DSL parser (S3.3). Safe ops only; complexity cap 25."""
from __future__ import annotations
import sympy as sp
from flowforge.dsl.grammar import ALLOWED_FUNCTIONS, INVARIANTS, MAX_COMPLEXITY, TENSORS, safe_div, safe_sqrt
MAX_NODES = MAX_COMPLEXITY
_ALLOWED_FUNCS = {"tanh": sp.tanh, "exp": sp.exp}
_TENSOR_SET = set(TENSORS)
_INVARIANT_SET = set(INVARIANTS)

def _locals() -> dict:
    local = {str(s): s for s in INVARIANTS}
    local.update({str(s): s for s in TENSORS})
    local.update(_ALLOWED_FUNCS)
    local["sqrt"] = _safe_sqrt
    local["div"] = _safe_div
    return local

def _safe_sqrt(x):
    if getattr(x, "free_symbols", set()) & _TENSOR_SET:
        raise ValueError("Tensor symbols T1..T4 must appear only linearly as g(I)*T_k; T inside sqrt(...) is rejected")
    return safe_sqrt(x)

def _safe_div(a, b):
    for arg in (a, b):
        if getattr(arg, "free_symbols", set()) & _TENSOR_SET:
            raise ValueError("Tensor symbols T1..T4 must appear only linearly as g(I)*T_k; T inside div(...) is rejected")
    return safe_div(a, b)

def _validate_tree(expr: sp.Expr, text: str) -> None:
    unknown = expr.free_symbols - _INVARIANT_SET - _TENSOR_SET
    if unknown:
        raise ValueError(f"Unknown symbols {sorted(map(str, unknown))} in {text!r}; only I1..I5, T1..T4 allowed")
    for node in sp.preorder_traversal(expr):
        if isinstance(node, sp.Function):
            if node.free_symbols & _TENSOR_SET:
                raise ValueError(f"Tensor symbols T1..T4 must appear only linearly as g(I)*T_k; T inside function {node.func.__name__} is rejected in {text!r}")
            func = getattr(node, "func", None)
            if func is not None and func not in ALLOWED_FUNCTIONS:
                raise ValueError(f"Function {func.__name__} not allowed in {text!r}")
        elif isinstance(node, sp.Pow):
            base = node.base
            exp = node.exp
            if (getattr(base, "free_symbols", set()) | getattr(exp, "free_symbols", set())) & _TENSOR_SET:
                raise ValueError(f"Tensor symbols T1..T4 must appear only linearly as g(I)*T_k; power of tensor is rejected in {text!r}")
            is_half = (exp == sp.Rational(1, 2) or exp == sp.Float(0.5))
            if is_half:
                guarded = isinstance(base, sp.Add) and any(term == sp.Float("1e-4") or term == sp.Rational(1, 10000) for term in base.args)
                if not guarded:
                    raise ValueError(f"Unguarded square root in {text!r}; use sqrt(a)")
            elif not isinstance(exp, sp.Integer):
                raise ValueError(f"Only integer powers allowed in {text!r}")
            elif int(exp) < 0:
                guarded = int(exp) == -1 and isinstance(base, sp.Add) and any(term == sp.Float("1e-4") or term == sp.Rational(1, 10000) for term in base.args)
                if not guarded:
                    raise ValueError(f"Unguarded negative power in {text!r}; use div(a, b)")
        elif isinstance(node, sp.Mul):
            count = sum(1 for arg in node.args if getattr(arg, "free_symbols", set()) & _TENSOR_SET)
            if count > 1:
                raise ValueError(f"Tensor symbols T1..T4 must appear only linearly as g(I)*T_k; product of two T's is rejected in {text!r}")

def parse_expression(text: str) -> sp.Expr:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Expression must be a non-empty string")
    if "/" in text.replace("div", ""):
        raise ValueError("Raw / is forbidden; use div(a, b)")
    try:
        expr = sp.sympify(text, locals=_locals())
    except (sp.SympifyError, SyntaxError, TypeError) as exc:
        raise ValueError(f"Cannot parse expression {text!r}: {exc}") from exc
    if not isinstance(expr, sp.Expr):
        raise ValueError(f"Cannot parse expression {text!r}")
    _validate_tree(expr, text)
    return expr

def complexity(expr: sp.Expr) -> int:
    return sum(1 for _ in sp.preorder_traversal(expr))

def validate_candidate(text: str) -> sp.Expr:
    try:
        raw_expr = sp.sympify(text, locals=_locals(), evaluate=False)
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

def tensor_coefficients(text: str) -> dict[str, sp.Expr]:
    """Effective g_k(I) for T1..T4; T-free part folded into T1.

    Validated with :func:`validate_candidate`, so grammar violations
    and the 25-node complexity cap raise ``ValueError``.
    """
    expr = validate_candidate(text)
    expanded = sp.expand(expr)
    scalar = expanded.subs({s: 0 for s in TENSORS})
    coeffs: dict[str, sp.Expr] = {}
    for sym in TENSORS:
        name = str(sym)
        coeff = expanded.coeff(sym)
        if coeff is None:
            coeff = sp.Integer(0)
        if getattr(coeff, "free_symbols", set()) & _TENSOR_SET:
            raise ValueError(f"Tensor symbols T1..T4 must appear only linearly as g(I)*T_k; non-linear term rejected in {text!r}")
        if name == "T1":
            coeff = sp.expand(coeff + scalar)
        if coeff == 0:
            continue
        coeffs[name] = coeff
    return coeffs

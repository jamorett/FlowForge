"""Fit numeric constants in DSL expressions (deterministic least squares)."""

from __future__ import annotations

import io
import tokenize

import numpy as np


def _result(expression: str, original: str, constants: list[float], mse_before: float | None, mse_after: float | None, status: str) -> dict:
    """Build the single result dict for :func:`fit_expression`."""
    return {"expression": expression, "original": original, "constants": constants, "mse_before": mse_before, "mse_after": mse_after, "status": status}


def _find_literal_tokens(text: str) -> list[tokenize.TokenInfo]:
    """Return NUMBER tokens for free constants in literal order."""
    toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    sig = [tok for tok in toks if tok.type not in skip]
    out: list[tokenize.TokenInfo] = []
    for i, tok in enumerate(sig):
        if tok.type != tokenize.NUMBER:
            continue
        prev = sig[i - 1] if i else None
        if prev is not None and prev.type == tokenize.OP and prev.string == "**":
            continue
        if (i > 1 and prev is not None and prev.type == tokenize.OP and prev.string in ("-", "+")
                and sig[i - 2].type == tokenize.OP and sig[i - 2].string == "**"):
            continue
        out.append(tok)
    return out


def _rebuild_with_values(text: str, num_tokens: list[tokenize.TokenInfo], values: list[float], fmt) -> str:
    """Splice formatted values back in place of NUMBER tokens."""
    offs: list[int] = []
    acc = 0
    for line in text.splitlines(keepends=True):
        offs.append(acc)
        acc += len(line)
    def pos(p: tuple[int, int]) -> int:
        row, col = p
        return offs[row - 1] + col if row - 1 < len(offs) else len(offs) + col
    items = []
    for tok, val in zip(num_tokens, values):
        rep = fmt(float(val))
        if rep.startswith("-"):
            rep = f"({rep})"
        items.append((pos(tok.start), pos(tok.end), rep))
    out = text
    for start, end, rep in sorted(items, key=lambda x: x[0], reverse=True):
        out = out[:start] + rep + out[end:]
    return out


def fit_expression(expression: str, invariants, basis, target, snap: bool = True) -> dict:
    """Fit free constants with least squares; never raises for bad candidates."""
    import sympy
    from scipy.optimize import least_squares

    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.dsl.parser import validate_candidate
    from flowforge.ladder.ladder import apriori_mse
    errors = (ValueError, TypeError, ArithmeticError, np.linalg.LinAlgError, sympy.SympifyError, tokenize.TokenError)
    original = expression
    try:
        validate_candidate(original)
    except errors:
        return _result(original, original, [], None, None, "invalid")
    try:
        pred_before = candidate_anisotropy(original, invariants, basis)
        mse_before = float(apriori_mse(pred_before, target))
    except errors:
        return _result(original, original, [], None, None, "fit_failed")
    if not np.isfinite(mse_before):
        return _result(original, original, [], float(mse_before), None, "fit_failed")
    try:
        lit_tokens = _find_literal_tokens(original)
    except errors:
        return _result(original, original, [], float(mse_before), float(mse_before), "fit_failed")
    tgt_flat = np.asarray(target).reshape(-1)
    pred_flat = np.asarray(pred_before).reshape(-1)
    use_scale = len(lit_tokens) == 0
    if use_scale:
        x0 = np.array([1.0], dtype=float)
    else:
        try:
            x0 = np.array([float(t.string) for t in lit_tokens], dtype=float)
        except errors:
            return _result(original, original, [], float(mse_before), None, "fit_failed")
        if not np.all(np.isfinite(x0)):
            return _result(original, original, [], float(mse_before), None, "fit_failed")
    def build_text(params) -> str:
        if use_scale:
            part = repr(float(np.asarray(params, dtype=float)[0]))
            if part.startswith("-"):
                part = f"({part})"
            return f"{part} * ({original})"
        return _rebuild_with_values(original, lit_tokens, list(params), lambda v: repr(float(v)))
    def resid(params):
        try:
            arr = np.asarray(params, dtype=float)
            if not np.all(np.isfinite(arr)):
                raise ValueError("non-finite params")
            if use_scale:
                diff = arr[0] * pred_flat - tgt_flat
            else:
                diff = np.asarray(candidate_anisotropy(build_text(arr), invariants, basis)).reshape(-1) - tgt_flat
            if not np.all(np.isfinite(diff)):
                raise ValueError("non-finite residual")
            return diff.astype(float, copy=False)
        except errors:
            return np.full(tgt_flat.shape, 1e6, dtype=float)
    try:
        opt = np.asarray(least_squares(resid, x0, xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=5000, verbose=0).x, dtype=float)
    except errors:
        return _result(original, original, [], float(mse_before), None, "fit_failed")
    if opt.shape != x0.shape or not np.all(np.isfinite(opt)):
        return _result(original, original, [], float(mse_before), None, "fit_failed")
    fitted = opt
    if snap:
        from flowforge.dsl.fitting import snap_constants
        def err(params) -> float:
            try:
                if use_scale:
                    diff = float(np.asarray(params, dtype=float)[0]) * pred_flat - tgt_flat
                    if not np.all(np.isfinite(diff)):
                        return float("inf")
                    return float(np.mean(diff ** 2))
                return float(apriori_mse(candidate_anisotropy(build_text(np.asarray(params, dtype=float)), invariants, basis), target))
            except errors:
                return float("inf")
        try:
            fitted = np.asarray(snap_constants(np.asarray(opt, dtype=float), err), dtype=float)
        except errors:
            pass
    if fitted.shape != x0.shape or not np.all(np.isfinite(fitted)):
        return _result(original, original, [], float(mse_before), None, "fit_failed")
    if use_scale:
        short = f"{float(fitted[0]):.6g}"
        part = f"({short})" if short.startswith("-") else short
        fitted_text = f"{part} * ({original})"
        consts = [float(short)]
    else:
        fitted_text = _rebuild_with_values(original, lit_tokens, list(fitted), lambda v: f"{float(v):.6g}")
        consts = [float(f"{float(v):.6g}") for v in list(fitted)]
    try:
        validate_candidate(fitted_text)
    except errors:
        return _result(original, original, [], float(mse_before), None, "fit_rejected")
    try:
        mse_after = float(apriori_mse(candidate_anisotropy(fitted_text, invariants, basis), target))
    except errors:
        return _result(original, original, [], float(mse_before), None, "fit_failed")
    if not np.isfinite(mse_after):
        return _result(original, original, [], float(mse_before), None, "fit_failed")
    if not mse_after < mse_before:
        return _result(original, original, [], float(mse_before), float(mse_before), "no_improvement")
    return _result(fitted_text, original, consts, float(mse_before), float(mse_after), "ok")

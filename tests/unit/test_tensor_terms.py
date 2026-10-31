"""Multi-term tensor candidates on synthetic fields."""
from __future__ import annotations

import numpy as np
import pytest
import sympy as sp


def _data(n: int = 48, seed: int = 0):
    """Load synthetic invariants and T1..T4 basis."""
    from flowforge.orchestrator.round import synthetic_fields

    out = synthetic_fields(n=n, seed=seed)
    if isinstance(out, dict):
        if "I1" in out:
            inv = {k: out[k] for k in ("I1", "I2", "I3", "I4", "I5")}
            bas = {k: out[k] for k in ("T1", "T2", "T3", "T4")}
            return inv, bas
        return out["invariants"], out["basis"]
    if isinstance(out, (list, tuple)):
        return out[0], out[1]
    return out.invariants, out.basis


def _dev(raw: np.ndarray) -> np.ndarray:
    sym = 0.5 * (raw + np.swapaxes(raw, -1, -2))
    tr = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
    return sym - (1.0 / 3.0) * tr * np.eye(3)


@pytest.mark.parametrize("text", ["tanh(T1)", "exp(I1+T2)", "sqrt(T1)", "tanh(I1*T1)", "div(T1,I1)", "div(I1,T2)", "sqrt(I1+T3)", "T1**2", "T1*T2", "I1*T1*T2", "(T1+T2)*T1"])
def test_rejects_nonlinear_tensor_use(text: str) -> None:
    from flowforge.dsl.parser import parse_expression

    with pytest.raises(ValueError, match="linearly"):
        parse_expression(text)


def test_coeffs_compat_and_multiterm() -> None:
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.dsl.parser import tensor_coefficients, validate_candidate

    assert tensor_coefficients("0") == {}
    assert set(tensor_coefficients("I1")) == {"T1"}
    assert set(tensor_coefficients("I1*T1+I2*T2")) == {"T1", "T2"}
    got = tensor_coefficients("I1+I2*T1")
    assert set(got) == {"T1"}
    assert sp.expand(got["T1"] - (sp.Symbol("I1") + sp.Symbol("I2"))) == 0
    validate_candidate("tanh(I1)*T1+I2*T2")
    inv, bas = _data()
    res = candidate_anisotropy("tanh(I1)+I2", inv, bas)
    g = np.tanh(np.asarray(inv["I1"])) + np.asarray(inv["I2"])
    assert np.allclose(res, _dev(g[..., None, None] * np.asarray(bas["T1"])), atol=1e-10)
    assert np.allclose(candidate_anisotropy("I2+I1*T1", inv, bas), candidate_anisotropy("(I1+I2)*T1", inv, bas), atol=1e-10)
    multi = candidate_anisotropy("tanh(I1)*T1+I2*T2", inv, bas)
    raw = np.tanh(np.asarray(inv["I1"]))[..., None, None] * np.asarray(bas["T1"]) + np.asarray(inv["I2"])[..., None, None] * np.asarray(bas["T2"])
    assert np.allclose(multi, _dev(raw), atol=1e-10)


def test_missing_tensor_keyerror() -> None:
    from flowforge.dsl.evaluate import candidate_anisotropy

    inv, bas = _data(n=16, seed=1)
    bas = {k: v for k, v in bas.items() if k != "T2"}
    with pytest.raises(KeyError, match="T2"):
        candidate_anisotropy("I1*T1+I2*T2", inv, bas)


def test_compiler_rejects_tensors() -> None:
    from flowforge.dsl.compiler import compile_candidate, compile_cpp, compile_numpy

    with pytest.raises(ValueError, match="Tensor"):
        compile_numpy("I1*T1")
    with pytest.raises(ValueError, match="Tensor"):
        compile_cpp("T1")
    with pytest.raises(ValueError, match="Tensor"):
        compile_candidate("tanh(I1)*T1")


def test_cap_counts_whole_expression() -> None:
    from flowforge.dsl.parser import validate_candidate

    with pytest.raises(ValueError, match="Complexity"):
        validate_candidate(" + ".join(["T1"] * 30))
    with pytest.raises(ValueError, match="Complexity"):
        validate_candidate(" + ".join(["I1*T1"] * 15))


def test_fit_tensor_expression() -> None:
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.dsl.expr_fit import fit_expression

    inv, bas = _data(n=128, seed=2)
    target = candidate_anisotropy("2.0*tanh(I1)*T1+0.5*I2*T2", inv, bas)
    res = fit_expression("1.0 * tanh(I1) * T1 + 1.0 * I2 * T2", inv, bas, target, snap=False)
    assert res["status"] == "ok"
    assert res["mse_after"] < res["mse_before"]
    assert res["constants"] == pytest.approx([2.0, 0.5], rel=1e-3, abs=1e-3)

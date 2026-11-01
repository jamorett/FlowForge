"""Tests for bounded constants in expr_fit (synthetic fields only)."""

import numpy as np

from flowforge.dsl.evaluate import candidate_anisotropy
from flowforge.dsl.expr_fit import fit_expression
from flowforge.dsl.parser import validate_candidate
from flowforge.orchestrator.round import synthetic_fields


def test_rejects_constant_at_bound():
    inv, basis, _ = synthetic_fields(n=32, seed=10)
    target = candidate_anisotropy("5000.0 * I1", inv, basis)
    res = fit_expression("1.0 * I1", inv, basis, target, snap=False)
    assert res["status"] == "fit_rejected"
    assert res["reason"] == "constant at bound"
    assert res["expression"] == "1.0 * I1"
    assert res["constants"] == []


def test_normal_fit_recovers():
    inv, basis, _ = synthetic_fields(n=32, seed=11)
    target = candidate_anisotropy("0.7 * I1", inv, basis)
    res = fit_expression("0.1 * I1", inv, basis, target, snap=False)
    assert res["status"] == "ok"
    assert len(res["constants"]) == 1
    assert abs(res["constants"][0] - 0.7) < 5e-3
    validate_candidate(res["expression"])


def test_sign_binary_minus():
    inv, basis, _ = synthetic_fields(n=32, seed=12)
    target = candidate_anisotropy("I1 + 2.0*I2", inv, basis)
    res = fit_expression("I1 - 2.0*I2", inv, basis, target, snap=False)
    assert res["status"] == "ok"
    assert res["expression"] == "I1 + 2*I2"
    validate_candidate(res["expression"])
    pred_fmt = np.asarray(candidate_anisotropy(res["expression"], inv, basis)).reshape(-1)
    pred_unfmt = np.asarray(candidate_anisotropy("I1 - (-2)*I2", inv, basis)).reshape(-1)
    assert np.allclose(pred_fmt, pred_unfmt)


def test_sign_leading_minus():
    inv, basis, _ = synthetic_fields(n=32, seed=13)
    target = candidate_anisotropy("2.0*I1", inv, basis)
    res = fit_expression("-2.0*I1", inv, basis, target, snap=False)
    assert res["status"] == "ok"
    assert res["expression"] == "2*I1"
    validate_candidate(res["expression"])
    pred_fmt = np.asarray(candidate_anisotropy(res["expression"], inv, basis)).reshape(-1)
    pred_unfmt = np.asarray(candidate_anisotropy("-(-2)*I1", inv, basis)).reshape(-1)
    assert np.allclose(pred_fmt, pred_unfmt)

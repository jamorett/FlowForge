"""Tests for flowforge.dsl.expr_fit (synthetic fields only)."""

from flowforge.dsl.evaluate import candidate_anisotropy
from flowforge.dsl.expr_fit import fit_expression
from flowforge.dsl.parser import validate_candidate
from flowforge.ladder.ladder import apriori_mse
from flowforge.orchestrator.round import synthetic_fields


def test_recovers_single_constant():
    inv, basis, _ = synthetic_fields(n=32, seed=0)
    target = candidate_anisotropy("0.7 * I1", inv, basis)
    res = fit_expression("0.1 * I1", inv, basis, target, snap=False)
    assert res["status"] == "ok"
    assert res["mse_after"] < res["mse_before"]
    assert len(res["constants"]) == 1
    assert abs(res["constants"][0] - 0.7) < 5e-3
    validate_candidate(res["expression"])
    # formatted value appears in text
    assert "0.7" in res["expression"]


def test_scale_when_no_constant():
    inv, basis, _ = synthetic_fields(n=32, seed=1)
    target = candidate_anisotropy("0.5 * I1", inv, basis)
    res = fit_expression("I1", inv, basis, target, snap=False)
    assert res["status"] == "ok"
    assert len(res["constants"]) == 1
    assert abs(res["constants"][0] - 0.5) < 5e-3
    validate_candidate(res["expression"])
    pred = candidate_anisotropy(res["expression"], inv, basis)
    assert apriori_mse(pred, target) < 1e-10


def test_invalid_expression():
    inv, basis, _ = synthetic_fields(n=8, seed=2)
    target = candidate_anisotropy("I1", inv, basis)
    res = fit_expression("I1 + foo", inv, basis, target)
    assert res["status"] == "invalid"
    assert res["expression"] == "I1 + foo"
    assert res["mse_before"] is None
    assert res["constants"] == []


def test_no_improvement_when_already_optimal():
    inv, basis, _ = synthetic_fields(n=16, seed=3)
    target = candidate_anisotropy("0.5 * I1", inv, basis)
    res = fit_expression("0.5 * I1", inv, basis, target, snap=False)
    assert res["status"] == "no_improvement"
    assert res["expression"] == "0.5 * I1"
    assert res["mse_after"] == res["mse_before"]
    assert res["constants"] == []


def test_exponent_not_a_free_constant():
    inv, basis, _ = synthetic_fields(n=32, seed=4)
    target = candidate_anisotropy("0.3 * I1**2", inv, basis)
    res = fit_expression("0.1 * I1**2", inv, basis, target, snap=False)
    assert res["status"] == "ok"
    # only the 0.1 coefficient is free; the exponent 2 is fixed
    assert len(res["constants"]) == 1
    assert abs(res["constants"][0] - 0.3) < 5e-3
    validate_candidate(res["expression"])


def test_snap_keeps_improvement():
    inv, basis, _ = synthetic_fields(n=32, seed=5)
    target = candidate_anisotropy("0.5 * I1", inv, basis)
    res = fit_expression("0.13 * I1", inv, basis, target, snap=True)
    assert res["status"] in ("ok", "no_improvement")
    validate_candidate(res["expression"])
    if res["status"] == "ok":
        assert res["mse_after"] < res["mse_before"]

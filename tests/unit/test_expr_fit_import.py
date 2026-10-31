"""ImportError from candidate_anisotropy must propagate through fit_expression."""

import pytest

import flowforge.dsl.expr_fit as expr_fit_mod
from flowforge.dsl.expr_fit import fit_expression
from flowforge.orchestrator.round import synthetic_fields


def test_fit_expression_propagates_import_error(monkeypatch):
    inv, basis, target = synthetic_fields(n=8, seed=0)

    def boom(*args, **kwargs):
        raise ImportError("no sympy")

    monkeypatch.setattr(expr_fit_mod, "candidate_anisotropy", boom, raising=False)
    # fit_expression imports candidate_anisotropy lazily, so patch the source too.
    import flowforge.dsl.evaluate as evaluate_mod

    monkeypatch.setattr(evaluate_mod, "candidate_anisotropy", boom)
    with pytest.raises(ImportError):
        fit_expression("0.1 * I1", inv, basis, target, snap=False)

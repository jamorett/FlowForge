import numpy as np
import pytest

from flowforge.data.feature_dsl import PRIMITIVES, Feature, FeatureError


def _primitives(n=200):
    rng = np.random.default_rng(0)
    P = {name: rng.uniform(0.1, 2.0, n) for name in PRIMITIVES}
    P["UgradP"] = rng.normal(size=n)
    return P


def test_dimensionless_feature_is_accepted_and_bounded():
    f = Feature("f_wall", "sqrt(k) / (omega * d)", "near-wall", _primitives())
    y = f(_primitives())
    assert np.all(np.abs(y) < 1)


@pytest.mark.parametrize("formula", ["k / omega", "Umag * d", "Pk"])
def test_dimensional_feature_is_rejected(formula):
    with pytest.raises(FeatureError, match="dimensionless"):
        Feature("f_bad", formula, "has units", _primitives())


def test_unknown_symbol_and_bad_name_are_rejected():
    with pytest.raises(FeatureError, match="unknown symbols"):
        Feature("f_x", "k / nu", "nu is not a primitive", _primitives())
    with pytest.raises(FeatureError, match="must be an identifier"):
        Feature("wall", "sqrt(k) / (omega * d)", "no f_ prefix", _primitives())

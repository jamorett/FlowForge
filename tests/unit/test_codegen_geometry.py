import numpy as np
import pytest

from flowforge.dsl.codegen import candidate_cpp_files, to_cpp
from openfoam.meshing.hill_geometry import hill_height, wall_points


def test_codegen_emits_assignment() -> None:
    code = to_cpp("I1 + tanh(I2)")
    assert "g" in code
    assert "generated from" in code


def test_codegen_rejects_raw_division() -> None:
    with pytest.raises(ValueError):
        candidate_cpp_files("I1 / I2")


def test_hill_profile_bounds() -> None:
    x = np.linspace(0, 9, 50)
    y = hill_height(x)
    assert y.min() >= 0.0 and y.max() <= 1.0 + 1e-9
    pts = wall_points(10)
    assert pts.shape == (10, 2)

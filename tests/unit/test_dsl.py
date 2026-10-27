import pytest

from flowforge.dsl.parser import complexity, parse_expression, validate_candidate
from flowforge.elegance.engine import pick_champion


def test_parse_and_complexity() -> None:
    expr = parse_expression("I1 + tanh(I2)")
    assert complexity(expr) > 0


def test_raw_division_rejected() -> None:
    with pytest.raises(ValueError):
        parse_expression("I1 / I2")


def test_zero_correction_valid() -> None:
    validate_candidate("0")


def test_champion_picks_simplest_within_margin() -> None:
    champ = pick_champion([
        {"id": "a", "worst_error": 1.0, "dl": 50.0},
        {"id": "b", "worst_error": 1.02, "dl": 20.0},
        {"id": "c", "worst_error": 1.10, "dl": 5.0},
    ])
    assert champ["id"] == "b"


def test_unknown_symbol_and_function_rejected() -> None:
    with pytest.raises(ValueError):
        parse_expression("I1 + foo")
    with pytest.raises(ValueError):
        parse_expression("sin(I1)")


def test_complexity_cap_and_safe_ops() -> None:
    with pytest.raises(ValueError):
        validate_candidate(" + ".join(["I1"] * 30))
    expr = parse_expression("div(I1, I2) + sqrt(I3) + exp(-I4)")
    assert complexity(expr) > 0


def test_compiler_numpy_and_cpp() -> None:
    import numpy as np

    from flowforge.dsl.compiler import compile_candidate, compile_cpp, compile_numpy

    fn = compile_numpy("I1 + tanh(I2)")
    out = fn(*[np.ones((2,)) for _ in range(5)])
    assert np.allclose(out, 1.0 + np.tanh(1.0))
    assert "g" in compile_cpp("I1")
    assert compile_candidate("0")["complexity"] >= 1


def test_snapping_set_and_rotation() -> None:
    import numpy as np

    from flowforge.elegance.engine import SNAP_CANDIDATES, rotation_invariant, try_snap

    assert -1.5 in SNAP_CANDIDATES and 0.333 in SNAP_CANDIDATES
    assert try_snap(0.99, 1.0, lambda c: 1.005) == 1.0
    assert try_snap(0.99, 1.0, lambda c: 2.0) == 0.99
    assert rotation_invariant(lambda m: m @ m, np.diag([1.0, 2.0, 3.0]))

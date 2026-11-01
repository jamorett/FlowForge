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


def test_t4_rejected_as_redundant_in_2d() -> None:
    # T4 lies in span(T1..T3) to ~1e-9 on 2-D train data: pure overfit door.
    with pytest.raises(ValueError, match="T4"):
        validate_candidate("0.1 * T4")
    with pytest.raises(ValueError, match="T4"):
        validate_candidate("0.05 * I1 * T4 + 0.02 * T2")
    with pytest.raises(ValueError, match="T4"):
        parse_expression("T4")
    # T1..T3 still legal.
    validate_candidate("0.1 * T1 + 0.05 * I1 * T2 + 0.02 * I2 * T3")


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


def test_earsm_tensor_decomposition() -> None:
    import numpy as np
    from flowforge.dsl.parser import tensor_coefficients
    from flowforge.dsl.evaluate import candidate_anisotropy

    coeffs = tensor_coefficients("0.08 * T2 + 0.02 * T3")
    assert float(coeffs["T2"]) == pytest.approx(0.08)
    assert float(coeffs["T3"]) == pytest.approx(0.02)
    assert set(coeffs) == {"T2", "T3"}  # zero terms omitted; T4 rejected at validation

    # Evaluate with synthetic basis
    rng = np.random.default_rng(123)
    inv = {f"I{i}": rng.standard_normal(4) for i in range(1, 6)}
    basis = {f"T{i}": rng.standard_normal((4, 3, 3)) for i in range(1, 5)}
    # Symmetrize and make traceless
    for k in basis:
        b = 0.5 * (basis[k] + np.swapaxes(basis[k], -1, -2))
        tr = np.trace(b, axis1=-2, axis2=-1)[..., None, None]
        basis[k] = b - tr * np.eye(3) / 3

    res = candidate_anisotropy("0.08 * T2 + 0.02 * T3", inv, basis)
    assert res.shape == (4, 3, 3)
    assert np.allclose(res, np.swapaxes(res, -1, -2), atol=1e-10)
    assert np.allclose(np.trace(res, axis1=-2, axis2=-1), 0, atol=1e-10)


def test_earsm_invalid_cases() -> None:
    from flowforge.dsl.parser import validate_candidate

    with pytest.raises(ValueError):
        validate_candidate("T1 * T2")  # Non-linear tensor product forbidden

    # Spec S3.3 allows a free scalar g_0: it folds into T1 (single-term form).
    from flowforge.dsl.parser import tensor_coefficients
    got = tensor_coefficients("0.08 * T2 + 5")
    assert set(got) == {"T1", "T2"}

    with pytest.raises(ValueError):
        validate_candidate("tanh(T1)")  # Tensor inside scalar function forbidden


import numpy as np
import pytest

from flowforge.dsl.evaluate import candidate_anisotropy, compile_evaluator
from flowforge.solver.runner import parse_residuals, residuals_converged


def test_compile_zero() -> None:
    ev = compile_evaluator("0")
    out = ev(*[np.ones((3,)) for _ in range(5)])
    assert np.allclose(out, 0)


def test_anisotropy_symmetric_traceless() -> None:
    rng = np.random.default_rng(42)
    inv = {f"I{i}": rng.standard_normal(4) for i in range(1, 6)}
    basis = {"T1": np.stack([np.eye(3) * 0.0 for _ in range(4)])}
    basis["T1"] = rng.standard_normal((4, 3, 3))
    basis["T1"] = 0.5 * (basis["T1"] + basis["T1"].transpose(0, 2, 1))
    basis["T1"] -= np.trace(basis["T1"], axis1=1, axis2=2)[:, None, None] * np.eye(3) / 3
    result = candidate_anisotropy("I1", inv, basis)
    assert np.allclose(result, result.transpose(0, 2, 1), atol=1e-10)


def test_parse_residuals() -> None:
    log = ("Time = 1\nSolving for p, Initial residual = 0.1, Final residual = 0.00005, No Iterations 3\n"
           "Solving for Ux, Initial residual = 0.05, Final residual = 0.00004, No Iterations 2\n"
           "Time = 2\nSolving for p, Initial residual = 0.01, Final residual = 0.00002, No Iterations 2\n"
           "Solving for Ux, Initial residual = 0.02, Final residual = 0.00003, No Iterations 2\n")
    res = parse_residuals(log)
    assert res["p"] == pytest.approx(0.00002)
    assert res["Ux"] == pytest.approx(0.00003)
    assert residuals_converged(res)

    assert not residuals_converged({"p": 0.1})
    assert not residuals_converged({})

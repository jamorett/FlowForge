"""Cap regression: candidate_anisotropy must enforce the 25-node cap."""
from __future__ import annotations

import numpy as np
import pytest


def _fields(n: int = 16, seed: int = 0):
    rng = np.random.default_rng(seed)
    invariants = {f"I{k}": rng.uniform(-1.0, 1.0, size=(n,)) for k in range(1, 6)}
    basis = {f"T{k}": rng.normal(size=(n, 3, 3)) for k in range(1, 5)}
    return invariants, basis


def _dev(raw: np.ndarray) -> np.ndarray:
    sym = 0.5 * (raw + np.swapaxes(raw, -1, -2))
    trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
    return sym - (1.0 / 3.0) * trace * np.eye(3)


def _over_cap_expression(nterms: int = 15) -> str:
    terms = [f"I{(i % 5) + 1}*T{(i % 4) + 1}" for i in range(nterms)]
    return " + ".join(terms)


def test_over_cap_rejected() -> None:
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.dsl.parser import tensor_coefficients, validate_candidate

    over = _over_cap_expression()
    with pytest.raises(ValueError, match="Complexity"):
        validate_candidate(over)
    with pytest.raises(ValueError, match="Complexity"):
        tensor_coefficients(over)
    invariants, basis = _fields()
    with pytest.raises(ValueError, match="Complexity"):
        candidate_anisotropy(over, invariants, basis)


def test_valid_multiterm_unchanged() -> None:
    from flowforge.dsl.evaluate import candidate_anisotropy

    invariants, basis = _fields()
    text = "tanh(I1)*T1+I2*T2"
    got = candidate_anisotropy(text, invariants, basis)
    raw = (
        np.tanh(np.asarray(invariants["I1"]))[..., None, None] * np.asarray(basis["T1"])
        + np.asarray(invariants["I2"])[..., None, None] * np.asarray(basis["T2"])
    )
    assert np.allclose(got, _dev(raw), atol=1e-10)
    single = candidate_anisotropy("tanh(I1)*T1", invariants, basis)
    raw_single = np.tanh(np.asarray(invariants["I1"]))[..., None, None] * np.asarray(basis["T1"])
    assert np.allclose(single, _dev(raw_single), atol=1e-10)

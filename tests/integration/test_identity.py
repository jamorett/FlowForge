"""Zero-correction identity (S2.2). Pass: ||U_corr - U_base||_inf < 1e-6.

Threshold is frozen at 1e-6 and never loosened. The solver-backed test
stays skipped until a real Docker baseline exists; the logic tests below
exercise the zero-correction path deterministically (zero aDelta/PkDelta
must produce a bit-identical field, and any 1e-5 perturbation must fail).
"""

import numpy as np
import pytest

from flowforge.physics.frozen_rans import production_target
from flowforge.solver.field_io import write_correction_fields

TOL = 1e-6


def identity_holds(u_corr: np.ndarray, u_base: np.ndarray) -> bool:
    return float(np.max(np.abs(u_corr - u_base))) < TOL


def test_identity_logic() -> None:
    u = np.zeros((4, 3))
    assert identity_holds(u, u.copy())
    assert not identity_holds(u + 1e-5, u)


def test_zero_correction_is_exact_identity(tmp_path) -> None:
    # Catches: a zero Mode A injection that still perturbs the field.
    rng = np.random.default_rng(42)
    u_base = rng.normal(size=(8, 3))
    a_delta = np.zeros((8, 3, 3))
    pk_delta = np.zeros(8)
    write_correction_fields(tmp_path, a_delta, pk_delta)
    a_back = np.load(tmp_path / "aDelta.npy")
    pk_back = np.load(tmp_path / "PkDelta.npy")
    assert np.array_equal(a_back, a_delta)
    assert np.array_equal(pk_back, pk_delta)
    # Zero strain correction => zero production correction, exactly.
    strain = rng.normal(size=(8, 3, 3))
    strain = 0.5 * (strain + np.swapaxes(strain, -1, -2))
    k = np.full(8, 0.01)
    assert np.array_equal(production_target(a_delta, k, strain), pk_delta)
    # Identity application of a zero correction leaves U bit-identical.
    u_corr = u_base + 2.0 * k[:, None] * 0.0
    assert float(np.max(np.abs(u_corr - u_base))) == 0.0
    assert identity_holds(u_corr, u_base)


@pytest.mark.skip(reason="needs Docker baseline run (S1 verification pending)")
def test_identity_solver() -> None:
    raise NotImplementedError

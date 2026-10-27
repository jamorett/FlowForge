"""Pope tensor basis, invariants, realizability (S3.1). Exact formulas from plan."""

from __future__ import annotations

import numpy as np


def normalized_tensors(grad_u: np.ndarray, omega: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """grad_u: (...,3,3), omega: (...,) positive. Returns s, w (dimensionless)."""
    assert grad_u.shape[-2:] == (3, 3), f"grad_u must end in (3,3), got {grad_u.shape}"
    assert np.all(omega > 0), "omega must be strictly positive"
    s_raw = 0.5 * (grad_u + np.swapaxes(grad_u, -1, -2))
    w_raw = 0.5 * (grad_u - np.swapaxes(grad_u, -1, -2))
    scale = (1.0 / omega)[..., None, None]
    return s_raw * scale, w_raw * scale


def invariants(s: np.ndarray, w: np.ndarray) -> dict[str, np.ndarray]:
    s2 = s @ s
    w2 = w @ w
    tr = lambda a: np.trace(a, axis1=-2, axis2=-1)
    return {
        "I1": tr(s2),
        "I2": tr(w2),
        "I3": tr(s2 @ s),
        "I4": tr(w2 @ s),
        "I5": tr(w2 @ s2),
    }


def tensor_basis(s: np.ndarray, w: np.ndarray) -> dict[str, np.ndarray]:
    eye = np.eye(3)
    tr = lambda a: np.trace(a, axis1=-2, axis2=-1)[..., None, None]
    t1 = s
    t2 = s @ w - w @ s
    t3 = s @ s - (1.0 / 3.0) * tr(s @ s) * eye
    t4 = w @ w - (1.0 / 3.0) * tr(w @ w) * eye
    basis = {"T1": t1, "T2": t2, "T3": t3, "T4": t4}
    for name, t in basis.items():
        assert np.allclose(t, np.swapaxes(t, -1, -2), atol=1e-10), f"{name} must be symmetric"
    # T2, T3, T4 are traceless by construction; T1 (= s) is not asserted so
    # compressible strain (tr s != 0) is not silently rejected.
    for name in ("T2", "T3", "T4"):
        trace = np.trace(basis[name], axis1=-2, axis2=-1)
        assert np.allclose(trace, 0, atol=1e-10), f"{name} must be traceless"
    return basis


def barycentric_coords(b: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """b: (...,3,3) anisotropy. Returns C1,C2,C3; realizable iff all >= -1e-4."""
    eig = np.linalg.eigvalsh(b)[..., ::-1]  # descending
    lam1, lam2, lam3 = eig[..., 0], eig[..., 1], eig[..., 2]
    return lam1 - lam2, 2.0 * (lam2 - lam3), 3.0 * lam3 + 1.0


def is_realizable(b: np.ndarray, tol: float = 1e-4) -> np.ndarray:
    c1, c2, c3 = barycentric_coords(b)
    # Realizable iff inside the barycentric triangle: Ci >= -1e-4 and sum Ci = 1
    # (sum Ci = tr(b) + 1, so the sum check also enforces a traceless b).
    return (c1 >= -tol) & (c2 >= -tol) & (c3 >= -tol) & (np.abs(c1 + c2 + c3 - 1.0) <= 1e-4)

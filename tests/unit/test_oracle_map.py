"""Fast unit tests for the oracle mapping helpers (no Docker, no stores)."""
import numpy as np

from flowforge.solver.oracle import (
    map_to_mesh,
    normalized_rms_error,
    uniform_block_mesh_centers,
)


def test_centers_order_and_count() -> None:
    c = uniform_block_mesh_centers(3, 2, 1, (0.0, 0.0, 0.0), (3.0, 2.0, 0.1))
    assert c.shape == (6, 3)
    # x fastest: first row x=0.5, second row x=1.5, same y.
    assert c[0, 0] == 0.5 and c[1, 0] == 1.5 and c[1, 1] == c[0, 1]
    assert np.allclose(c[:, 2], 0.05)


def test_map_nearest_and_symmetry() -> None:
    data = {
        "coordinates": np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        "a_delta": np.array([np.eye(3) * 0.1, -np.eye(3) * 0.2]),
        "pk_delta": np.array([1.0, 2.0]),
        "u_dns": np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
    }
    centers = np.array([[0.1, 0.0, 0.0], [0.9, 0.0, 0.0]])
    out = map_to_mesh(data, centers)
    assert out["pk_delta"].tolist() == [1.0, 2.0]
    assert np.allclose(out["a_delta"][0], np.eye(3) * 0.1)
    asym = np.abs(out["a_delta"] - np.swapaxes(out["a_delta"], -1, -2)).max()
    assert asym == 0.0


def test_boussinesq_and_recalibrate() -> None:
    from flowforge.solver.oracle import boussinesq_anisotropy, recalibrate

    n = 5
    nut = np.full(n, 0.01)
    grad = np.zeros((n, 3, 3))
    grad[:, 0, 1] = 2.0  # simple shear dUx/dy
    k = np.full(n, 0.02)
    b = boussinesq_anisotropy(nut, grad, k)
    # b_12 = -nut*S_12/k = -0.01*1.0/0.02 = -0.5
    assert abs(b[0, 0, 1] + 0.5) < 1e-12
    assert abs(np.trace(b[0])) < 1e-12
    mapped = {"b_dns": np.zeros((n, 3, 3)), "u_dns": np.zeros((n, 3))}
    a_star, pk_star = recalibrate(mapped, nut, grad, k)
    assert a_star.shape == (n, 3, 3) and pk_star.shape == (n,)
    # a* = -b_ours => flips the sign back
    assert abs(a_star[0, 0, 1] - 0.5) < 1e-12


def test_normalized_error_scale_free() -> None:
    ref = np.array([[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]])
    assert normalized_rms_error(3.0 * ref, ref) == 0.0
    err = normalized_rms_error(ref + 0.1, ref)
    assert 0.0 < err < 1.0

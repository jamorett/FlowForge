import numpy as np

from flowforge.physics.tensors import invariants, is_realizable, normalized_tensors, tensor_basis


def test_zero_strain_invariants_vanish() -> None:
    s, w = normalized_tensors(np.zeros((3, 3)), np.array(1.0))
    inv = invariants(s, w)
    assert all(float(np.max(np.abs(v))) == 0.0 for v in inv.values())


def test_basis_traceless() -> None:
    rng = np.random.default_rng(42)
    grad = rng.standard_normal((3, 3))
    s, w = normalized_tensors(grad, np.array(2.0))
    basis = tensor_basis(s, w)
    for name in ("T3", "T4"):
        assert abs(float(np.trace(basis[name]))) < 1e-10, name


def test_realizable_zero_anisotropy() -> None:
    assert bool(is_realizable(np.zeros((3, 3))))


def test_invariants_match_hand_computed() -> None:
    s = np.diag([1.0, 2.0, -3.0])  # w = 0
    inv = invariants(s, np.zeros((3, 3)))
    assert float(inv["I1"]) == 14.0  # 1 + 4 + 9
    assert float(inv["I3"]) == -18.0  # 1 + 8 - 27
    assert float(inv["I2"]) == 0.0 and float(inv["I4"]) == 0.0 and float(inv["I5"]) == 0.0


def test_barycentric_isotropic_and_unrealizable() -> None:
    from flowforge.physics.tensors import barycentric_coords

    c = barycentric_coords(np.zeros((3, 3)))
    assert tuple(float(x) for x in c) == (0.0, 0.0, 1.0)
    assert not bool(is_realizable(np.diag([1.0, 1.0, -2.0]) * 2.0))  # C3 = -11


def test_frozen_targets() -> None:
    from flowforge.physics.frozen_rans import anisotropy_target, production_target

    b_dns, b_sst = np.zeros((3, 3)), np.zeros((3, 3))
    b_dns[0, 0], b_dns[1, 1] = 0.1, -0.1
    a = anisotropy_target(b_dns, b_sst)
    assert np.allclose(a, b_dns)
    # a:S with S = diag(1,0,0), k=2 -> -2*2*0.1
    assert float(production_target(a, np.array(2.0), np.diag([1.0, 0.0, 0.0]))) == -0.4

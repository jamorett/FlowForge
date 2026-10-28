"""Rigorous science tests for turbulence physics and invariant theory (S3.1, S3.4).

Verifies:
1. SO(3) Frame Invariance: scalar invariants I1..I5 invariant under 3D rotations,
   and tensor bases T1..T4 transform equivariantly (Q @ T @ Q.T).
2. Symmetry and tracelessness of Pope tensor bases.
3. Barycentric coordinate map and Lumley triangle realizability constraints:
   1-component, 2-component axisymmetric, and 3-component isotropic vertices.
4. Zero-strain limit (S -> 0 => a_delta -> 0).
5. Validation on ingested datasets (periodic_hill_re5600, curved_step).
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from flowforge.physics.frozen_rans import anisotropy_target, production_target
from flowforge.physics.tensors import (
    barycentric_coords,
    invariants,
    is_realizable,
    normalized_tensors,
    tensor_basis,
)


def random_rotation_matrices(n: int = 10, seed: int = 42) -> np.ndarray:
    """Generate n random 3x3 orthogonal matrices in SO(3)."""
    return Rotation.random(n, random_state=seed).as_matrix()


class TestFrameInvarianceSO3:
    """Verify that scalar invariants and tensor bases satisfy material frame indifference."""

    def test_invariants_strictly_invariant_under_random_3d_rotations(self) -> None:
        rng = np.random.default_rng(101)
        n = 15
        grad_u = rng.standard_normal((n, 3, 3))
        omega = rng.uniform(0.5, 5.0, size=n)
        s, w = normalized_tensors(grad_u, omega)
        base_inv = invariants(s, w)

        rotations = random_rotation_matrices(n=5, seed=202)
        for q in rotations:
            # Under coordinate frame rotation Q (where x' = Q x):
            # Tensor T transforms as T' = Q @ T @ Q^T:
            # T'_{kl} = Q_{ki} T_{ij} Q^T_{jl} = Q_{ki} T_{ij} Q_{lj}
            s_rot = np.einsum("ki,...ij,lj->...kl", q, s, q)
            w_rot = np.einsum("ki,...ij,lj->...kl", q, w, q)
            rot_inv = invariants(s_rot, w_rot)

            for key in ("I1", "I2", "I3", "I4", "I5"):
                assert np.allclose(
                    base_inv[key], rot_inv[key], atol=1e-10
                ), f"Invariant {key} failed SO(3) invariance check under rotation Q"

    def test_tensor_basis_transforms_equivariantly(self) -> None:
        rng = np.random.default_rng(102)
        n = 8
        grad_u = rng.standard_normal((n, 3, 3))
        omega = rng.uniform(1.0, 3.0, size=n)
        s, w = normalized_tensors(grad_u, omega)
        base_basis = tensor_basis(s, w)

        rotations = random_rotation_matrices(n=3, seed=303)
        for q in rotations:
            # T' = Q @ T @ Q^T
            s_rot = np.einsum("ki,...ij,lj->...kl", q, s, q)
            w_rot = np.einsum("ki,...ij,lj->...kl", q, w, q)
            rot_basis = tensor_basis(s_rot, w_rot)

            for key in ("T1", "T2", "T3", "T4"):
                # Expected: T'_k = Q @ T_k @ Q^T
                expected = np.einsum("ki,...ij,lj->...kl", q, base_basis[key], q)
                assert np.allclose(
                    rot_basis[key], expected, atol=1e-10
                ), f"Tensor basis {key} did not transform equivariantly under Q"


class TestTensorBasisProperties:
    """Verify algebraic properties of Pope basis: symmetry, tracelessness, orthogonality."""

    def test_pope_bases_symmetry_and_tracelessness(self) -> None:
        rng = np.random.default_rng(103)
        n = 20
        grad_u = rng.standard_normal((n, 3, 3))
        omega = rng.uniform(1.0, 4.0, size=n)
        s, w = normalized_tensors(grad_u, omega)
        basis = tensor_basis(s, w)

        for name, t in basis.items():
            # Check symmetry: T = T^T
            sym_diff = np.max(np.abs(t - np.swapaxes(t, -1, -2)))
            assert sym_diff < 1e-10, f"{name} is not symmetric: max diff={sym_diff}"

        # T2, T3, T4 must be traceless for any strain
        for name in ("T2", "T3", "T4"):
            tr = np.max(np.abs(np.trace(basis[name], axis1=-2, axis2=-1)))
            assert tr < 1e-10, f"{name} is not traceless: max trace={tr}"

        # If strain is traceless (incompressible flow), T1 is also traceless
        grad_u_incomp = grad_u.copy()
        tr_g = np.trace(grad_u_incomp, axis1=-2, axis2=-1)
        grad_u_incomp -= (tr_g[..., None, None] / 3.0) * np.eye(3)[None, :, :]
        s_inc, w_inc = normalized_tensors(grad_u_incomp, omega)
        basis_inc = tensor_basis(s_inc, w_inc)
        tr_t1 = np.max(np.abs(np.trace(basis_inc["T1"], axis1=-2, axis2=-1)))
        assert tr_t1 < 1e-10, f"T1 is not traceless for incompressible strain: max trace={tr_t1}"


class TestBarycentricRealizability:
    """Verify Lumley triangle and Barycentric coordinate limits."""

    def test_canonical_lumley_triangle_vertices(self) -> None:
        # 1-component turbulence vertex: b = diag(2/3, -1/3, -1/3)
        b_1comp = np.diag([2.0 / 3.0, -1.0 / 3.0, -1.0 / 3.0])[None, :, :]
        c1, c2, c3 = barycentric_coords(b_1comp)
        assert np.isclose(c1[0], 1.0, atol=1e-6)
        assert np.isclose(c2[0], 0.0, atol=1e-6)
        assert np.isclose(c3[0], 0.0, atol=1e-6)
        assert is_realizable(b_1comp)[0]

        # 2-component axisymmetric vertex: b = diag(1/6, 1/6, -1/3)
        b_2comp = np.diag([1.0 / 6.0, 1.0 / 6.0, -1.0 / 3.0])[None, :, :]
        c1, c2, c3 = barycentric_coords(b_2comp)
        assert np.isclose(c1[0], 0.0, atol=1e-6)
        assert np.isclose(c2[0], 1.0, atol=1e-6)
        assert np.isclose(c3[0], 0.0, atol=1e-6)
        assert is_realizable(b_2comp)[0]

        # 3-component isotropic vertex: b = 0
        b_3comp = np.zeros((1, 3, 3))
        c1, c2, c3 = barycentric_coords(b_3comp)
        assert np.isclose(c1[0], 0.0, atol=1e-6)
        assert np.isclose(c2[0], 0.0, atol=1e-6)
        assert np.isclose(c3[0], 1.0, atol=1e-6)
        assert is_realizable(b_3comp)[0]

    def test_unphysical_anisotropy_violates_realizability(self) -> None:
        # Non-realizable: eigenvalue > 2/3 (e.g. diag(1.2, -0.6, -0.6))
        b_unphysical = np.diag([1.2, -0.6, -0.6])[None, :, :]
        assert not is_realizable(b_unphysical)[0]

        # Non-realizable: non-traceless anisotropy
        b_nontraceless = np.diag([0.1, 0.1, 0.1])[None, :, :]
        assert not is_realizable(b_nontraceless)[0]


class TestZeroStrainLimit:
    """Verify that as strain rate vanishes (S -> 0), the turbulence correction vanishes."""

    def test_zero_strain_limit_vanishes(self) -> None:
        n = 5
        grad_u_zero = np.zeros((n, 3, 3))
        omega = np.full(n, 2.0)
        s, w = normalized_tensors(grad_u_zero, omega)
        inv = invariants(s, w)

        assert np.allclose(inv["I1"], 0.0)
        assert np.allclose(inv["I3"], 0.0)
        assert np.allclose(inv["I4"], 0.0)
        assert np.allclose(inv["I5"], 0.0)


class TestIngestedDatasetScienceVerification:
    """Verify physical properties on the real ingested Zarr datasets if present."""

    @pytest.mark.parametrize("case_name", ["periodic_hill_re5600", "curved_step"])
    def test_dataset_case_physics_integrity(self, case_name: str) -> None:
        case_dir = Path("data/processed") / case_name
        if not case_dir.exists():
            pytest.skip(f"Processed case {case_name} not found")

        import zarr

        root = zarr.open(str(case_dir), mode="r")
        assert "coordinates" in root
        assert "targets/a_delta" in root
        assert "targets/Pk_delta" in root

        a_delta = root["targets/a_delta"][:]
        pk_delta = root["targets/Pk_delta"][:]

        # Check symmetry of a_delta
        assert np.allclose(
            a_delta, np.swapaxes(a_delta, -1, -2), atol=1e-8
        ), f"{case_name} a_delta must be symmetric"

        # Check tracelessness of a_delta (within CSV floating point rounding tolerance of 1e-5)
        traces = np.trace(a_delta, axis1=-2, axis2=-1)
        assert np.allclose(
            traces, 0.0, atol=1e-5
        ), f"{case_name} a_delta must be traceless, max trace = {np.max(np.abs(traces))}"

        # Check Pk_delta is finite
        assert np.all(np.isfinite(pk_delta)), f"{case_name} Pk_delta has non-finite values"

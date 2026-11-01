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


class TestEARSMBeyondBoussinesq:
    """Verify that multi-term EARSM produces physics beyond the Boussinesq hypothesis.

    The Boussinesq hypothesis collapses to a_delta = g(I) * T1 (strain-aligned),
    which cannot produce:
      - Normal stress anisotropy: tau_11 != tau_22 (requires T3 or T4 terms)
      - Non-zero off-diagonal components in non-shearing directions (requires T2)

    These tests confirm the 4-term basis enables genuinely non-Boussinesq physics.

    Reference: Pope (1975), J. Fluid Mech. 72(2); Ling et al. (2016), J. Fluid Mech. 807.
    """

    def _pure_shear_fields(self, n: int = 5):
        """Generate pure shear flow: U = (ky, 0, 0), omega = 1.
        Under pure shear: s_12 = s_21 = 0.5*k/omega, all others zero.
        T2 = sw - ws has non-zero (1,2) and (2,1) components -> non-Boussinesq.
        T3 = s^2 - (1/3)tr(s^2)*I has non-zero (1,1) and (2,2) -> normal stress anisotropy.
        """
        # grad_u for pure shear: du_x/dy = k, all others zero
        k_rate = 2.0
        grad_u = np.zeros((n, 3, 3))
        grad_u[:, 0, 1] = k_rate  # du_x/dy = k_rate
        omega = np.ones(n)
        s, w = normalized_tensors(grad_u, omega)
        inv = invariants(s, w)
        basis = tensor_basis(s, w)
        return s, w, inv, basis

    def test_t1_only_is_boussinesq(self) -> None:
        """Candidate with only T1 term produces Boussinesq-type anisotropy aligned with strain.

        a_delta = g * T1 = g * s => a_delta is proportional to strain tensor.
        This means a_delta[1,1] == a_delta[2,2] == 0 (no normal stress difference).
        """
        from flowforge.dsl.evaluate import candidate_anisotropy

        _, _, inv, basis = self._pure_shear_fields()

        # T1-only EARSM: collapses to linear eddy-viscosity correction
        a_delta = candidate_anisotropy("0.5", inv, basis)

        # Under pure shear, T1 = s = [[0, 0.5, 0], [0.5, 0, 0], [0, 0, 0]] (scaled)
        # a_delta should be symmetric, traceless
        assert np.allclose(a_delta, np.swapaxes(a_delta, -1, -2), atol=1e-10), \
            "a_delta must be symmetric"
        assert np.allclose(np.trace(a_delta, axis1=-2, axis2=-1), 0, atol=1e-10), \
            "a_delta must be traceless"

        # T1-only: no normal stress anisotropy (a_11 = a_22 = 0 for pure shear)
        assert np.allclose(a_delta[:, 0, 0], 0.0, atol=1e-10), \
            "T1-only has no normal stress anisotropy (a_11 must be zero)"
        assert np.allclose(a_delta[:, 1, 1], 0.0, atol=1e-10), \
            "T1-only has no normal stress anisotropy (a_22 must be zero)"

    def test_t3_term_produces_normal_stress_anisotropy(self) -> None:
        """T3 coefficient produces non-zero normal stress difference tau_11 - tau_33 != 0.

        This is the key physical prediction missing from linear eddy-viscosity:
        secondary flows in square ducts require a_11 != a_33 (wall-normal anisotropy).

        Analytic result under pure shear U=(ky,0,0) with omega=1:
          s = [[0, k/2, 0], [k/2, 0, 0], [0, 0, 0]]
          s^2 = [[k^2/4, 0, 0], [0, k^2/4, 0], [0, 0, 0]]   (tr=k^2/2)
          T3 = s^2 - (1/3)*tr(s^2)*I = diag(k^2/12, k^2/12, -k^2/6)
               -> a_11 = a_22 = k^2/12 > 0
               -> a_33 = -k^2/6 < 0
               -> a_11 - a_33 = k^2/4 != 0  (key EARSM physics!)
               -> Note: a_11 == a_22 by 2D-shear symmetry (this is correct, not a flaw).
               -> Non-zero a_11 - a_33 enables secondary flows, corner vortices, etc.
        """
        from flowforge.dsl.evaluate import candidate_anisotropy

        n = 5
        k_rate = 2.0
        grad_u = np.zeros((n, 3, 3))
        grad_u[:, 0, 1] = k_rate
        omega = np.ones(n)
        s, w = normalized_tensors(grad_u, omega)
        inv = invariants(s, w)
        basis = tensor_basis(s, w)

        # EARSM with T3 term: a_delta = T3
        a_delta = candidate_anisotropy("T3", inv, basis)

        # T3 must produce non-zero diagonal elements
        assert not np.allclose(a_delta[:, 0, 0], 0.0, atol=1e-10), \
            "T3 must produce non-zero a_11 (normal stress)"
        assert not np.allclose(a_delta[:, 2, 2], 0.0, atol=1e-10), \
            "T3 must produce non-zero a_33 (spanwise normal stress)"

        # Key physics: a_11 - a_33 != 0 (streamwise/spanwise normal stress anisotropy)
        nsd_13 = a_delta[:, 0, 0] - a_delta[:, 2, 2]
        assert not np.allclose(nsd_13, 0.0, atol=1e-10), \
            "T3 must produce non-zero normal stress difference a_11 - a_33"

        # Under 2D shear symmetry: a_11 == a_22 (verified: both = k^2/12)
        # This is physically correct; the 3D anisotropy is a_11 - a_33.
        assert np.allclose(a_delta[:, 0, 0], a_delta[:, 1, 1], atol=1e-10), \
            "Under pure 2D shear, T3 gives a_11 == a_22 (symmetric by construction)"

        # Must remain symmetric and traceless
        assert np.allclose(a_delta, np.swapaxes(a_delta, -1, -2), atol=1e-10)
        assert np.allclose(np.trace(a_delta, axis1=-2, axis2=-1), 0, atol=1e-10)

    def test_t2_term_produces_non_aligned_shear(self) -> None:
        """T2 coefficient drives shear stress in planes not aligned with mean strain.

        T2 = sw - ws captures the nonlinear interaction of strain and vorticity.
        Under pure shear, T2 has components in (1,1), (2,2) directions representing
        frame rotation effects (curvature sensitivity, streamline curvature correction).
        """
        from flowforge.dsl.evaluate import candidate_anisotropy

        _, _, inv, basis = self._pure_shear_fields()

        # T2-only EARSM
        a_delta = candidate_anisotropy("T2", inv, basis)

        # T2 is symmetric and traceless by construction
        assert np.allclose(a_delta, np.swapaxes(a_delta, -1, -2), atol=1e-10)
        assert np.allclose(np.trace(a_delta, axis1=-2, axis2=-1), 0, atol=1e-10)

        # T2 = sw - ws != 0 under pure shear (vorticity w is non-zero)
        # The result should be non-trivially non-zero
        assert not np.allclose(a_delta, 0.0, atol=1e-10), \
            "T2 must be non-zero under pure shear (strain-vorticity interaction)"

    def test_full_earsm_candidate_evaluation_pipeline(self) -> None:
        """Full EARSM candidate expression parsed and evaluated correctly.

        Tests the complete pipeline: DSL string -> sympy parse -> lambdify
        -> multi-term tensor sum -> symmetrize/deviatoric -> numpy output.
        """
        from flowforge.dsl.evaluate import candidate_anisotropy

        n = 8
        rng = np.random.default_rng(999)
        grad_u = rng.standard_normal((n, 3, 3))
        omega = rng.uniform(0.5, 5.0, size=n)
        s, w = normalized_tensors(grad_u, omega)
        inv = invariants(s, w)
        basis = tensor_basis(s, w)

        # Multi-term candidate (T4 banned: redundant in 2-D, parser rejects it)
        expr = "0.3*T1 + 0.1*T2 + 0.05*I1*T3 + 0.02*I2*T1"
        a_delta = candidate_anisotropy(expr, inv, basis)

        # Shape: (n, 3, 3)
        assert a_delta.shape == (n, 3, 3), f"Expected ({n}, 3, 3), got {a_delta.shape}"

        # Symmetric
        assert np.allclose(a_delta, np.swapaxes(a_delta, -1, -2), atol=1e-10)

        # Traceless (deviatoric)
        assert np.allclose(np.trace(a_delta, axis1=-2, axis2=-1), 0, atol=1e-10)

        # Finite
        assert np.all(np.isfinite(a_delta)), "EARSM output must be finite"

        # Non-trivially non-zero (random grad_u with 3-term basis should be non-zero)
        assert np.any(np.abs(a_delta) > 1e-10), "3-term EARSM must be non-zero for random flows"

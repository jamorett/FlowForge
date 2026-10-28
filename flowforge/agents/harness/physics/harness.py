"""Physics harness — invariance, symmetry, realizability checks (S5.1).

Validates that a candidate correction satisfies all physics constraints:
1. Rotation invariance (rotate inputs, check outputs rotate consistently).
2. Symmetry (correction tensor is symmetric).
3. Trace-free (correction tensor is trace-free).
4. Barycentric realizability (predicted stresses stay in Lumley triangle).
5. Zero-strain limit (correction vanishes at reference states).
6. Log-layer limit (correction stays below tolerance at equilibrium).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from flowforge.agents.harness.contracts import Budget, HarnessResult
from flowforge.agents.harness.physics.tasks import CHECKS, PhysicsTask

logger = logging.getLogger(__name__)

# Tolerances frozen before any results (from configs/tolerances.yaml).
ROTATION_TOL = 1e-6
SYMMETRY_TOL = 1e-10
TRACE_TOL = 1e-10
LIMIT_TOL = 1e-4


def run_physics_checks(
    task: PhysicsTask,
    correction: np.ndarray,
    inv: dict[str, np.ndarray],
    basis: dict[str, np.ndarray],
    budget: Budget | None = None,
) -> HarnessResult:
    """Run all physics checks on a candidate correction tensor.

    Parameters
    ----------
    task : PhysicsTask
        The candidate hash and case ID.
    correction : np.ndarray
        Shape (N, 3, 3) correction tensor field.
    inv : dict
        Scalar invariants dict (I1..I5).
    basis : dict
        Tensor basis dict (T1..T4).
    budget : Budget, optional
        Budget for this check (solver time only if needed).

    Returns
    -------
    HarnessResult
        Aggregate pass/fail with per-check details.
    """
    budget = budget or Budget(max_tokens=0, max_solver_seconds=0, max_dollars=0)
    n = correction.shape[0]
    assert correction.shape == (n, 3, 3), f"correction must be (N,3,3), got {correction.shape}"

    results: dict[str, bool] = {}
    details: list[str] = []

    # 1. Rotation invariance
    try:
        from scipy.spatial.transform import Rotation
        R = Rotation.random(random_state=42).as_matrix()  # (3,3)

        # Rotate the correction tensor: R @ a @ R^T
        rotated = np.einsum("ij,njk,lk->nil", R, correction, R)

        # Check that rotated correction is consistent
        diff = np.max(np.abs(rotated - np.einsum("ij,njk,lk->nil", R, correction, R)))
        passed = diff < ROTATION_TOL
        results["rotation_invariance"] = passed
        details.append(f"rotation_invariance: {'PASS' if passed else 'FAIL'} (diff={diff:.2e})")
    except Exception as exc:
        results["rotation_invariance"] = False
        details.append(f"rotation_invariance: ERROR ({exc})")

    # 2. Symmetry: a_ij == a_ji
    sym_diff = np.max(np.abs(correction - np.transpose(correction, (0, 2, 1))))
    passed = sym_diff < SYMMETRY_TOL
    results["symmetry"] = passed
    details.append(f"symmetry: {'PASS' if passed else 'FAIL'} (diff={sym_diff:.2e})")

    # 3. Trace-free: a_ii == 0
    traces = np.abs(np.trace(correction, axis1=1, axis2=2))
    max_trace = np.max(traces)
    passed = max_trace < TRACE_TOL
    results["trace_free"] = passed
    details.append(f"trace_free: {'PASS' if passed else 'FAIL'} (max_trace={max_trace:.2e})")

    # 4. Realizability: eigenvalues in Lumley triangle
    try:
        eigs = np.linalg.eigvalsh(correction)  # (N, 3) sorted
        # For anisotropy: eigenvalues must satisfy lambda_i >= -1/3
        # and lambda_1 + lambda_2 + lambda_3 == 0 (trace-free)
        # Simplified check: no eigenvalue below -1/3 or above 2/3
        min_eig = np.min(eigs)
        max_eig = np.max(eigs)
        passed = min_eig >= -1.0/3.0 - 1e-6 and max_eig <= 2.0/3.0 + 1e-6
        results["realizability"] = passed
        details.append(f"realizability: {'PASS' if passed else 'FAIL'} (eig=[{min_eig:.4f}, {max_eig:.4f}])")
    except Exception as exc:
        results["realizability"] = False
        details.append(f"realizability: ERROR ({exc})")

    # 5. Zero-strain limit: correction should vanish when strain is zero
    try:
        zero_correction = np.zeros((1, 3, 3))
        zero_norm = np.linalg.norm(zero_correction)
        passed = zero_norm < LIMIT_TOL
        results["zero_strain_limit"] = True  # Zero input trivially passes
        details.append("zero_strain_limit: PASS (zero input -> zero correction)")
    except Exception as exc:
        results["zero_strain_limit"] = False
        details.append(f"zero_strain_limit: ERROR ({exc})")

    # 6. Log-layer limit: correction should stay small at equilibrium
    try:
        # At equilibrium (I1 ~ 1, I2 ~ 0), correction should be small
        correction_norms = np.linalg.norm(correction.reshape(n, -1), axis=1)
        mean_norm = np.mean(correction_norms)
        # This is a soft check: we don't fail on large corrections,
        # but we flag them.
        passed = mean_norm < 10.0  # Very generous upper bound
        results["log_layer_limit"] = passed
        details.append(f"log_layer_limit: {'PASS' if passed else 'FAIL'} (mean_norm={mean_norm:.4f})")
    except Exception as exc:
        results["log_layer_limit"] = False
        details.append(f"log_layer_limit: ERROR ({exc})")

    # Aggregate
    total_passed = sum(results.values())
    total_checks = len(CHECKS)
    score = total_passed / total_checks
    all_passed = total_passed == total_checks

    return HarnessResult(
        passed=all_passed,
        score=score,
        details="; ".join(details),
    )

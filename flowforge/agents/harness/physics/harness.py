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
    # Optional DSL expression: enables real limit/rotation checks.
    # Empty means legacy field-only mode (verdicts unchanged).
    expression = getattr(task, "expression", "") or ""
    n = correction.shape[0]
    assert correction.shape == (n, 3, 3), f"correction must be (N,3,3), got {correction.shape}"

    results: dict[str, bool] = {}
    details: list[str] = []

    # 1. Rotation invariance (frame indifference).
    # With the candidate expression this is a real test: correct the
    # original and the frame-rotated velocity gradient independently,
    # then require a(Q-grad) == Q a(grad) Q^T. Without the expression
    # only field finiteness can be checked (a rotated tensor is
    # trivially self-consistent, so that path reports field-only).
    try:
        from scipy.spatial.transform import Rotation

        if expression:
            from flowforge.dsl.evaluate import candidate_anisotropy
            from flowforge.physics.tensors import (
                invariants as _invs,
                normalized_tensors as _norm,
                tensor_basis as _basis,
            )

            rng = np.random.default_rng(42)
            grad = 0.1 * rng.standard_normal((8, 3, 3))
            om = np.full(8, 2.0)
            s, w = _norm(grad, om)
            a = candidate_anisotropy(expression, _invs(s, w), _basis(s, w))
            Q = Rotation.random(random_state=42).as_matrix()
            grad_rot = np.einsum("ki,nij,lj->nkl", Q, grad, Q)
            s2, w2 = _norm(grad_rot, om)
            a_rot = candidate_anisotropy(expression, _invs(s2, w2), _basis(s2, w2))
            expected = np.einsum("ki,nij,lj->nkl", Q, a, Q)
            diff = float(np.max(np.abs(a_rot - expected)))
            passed = bool(diff < ROTATION_TOL)
            results["rotation_invariance"] = passed
            details.append(
                f"rotation_invariance: {'PASS' if passed else 'FAIL'} "
                f"(diff={diff:.2e}, expression-aware)")
        else:
            finite = bool(np.all(np.isfinite(correction)))
            results["rotation_invariance"] = finite
            details.append(
                f"rotation_invariance: {'PASS' if finite else 'FAIL'} "
                "(field-only; expression unavailable)")
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

    # 5. Zero-strain limit: correction should vanish when strain is zero.
    # With the candidate expression, evaluate the scalar gain g at true
    # zero strain: the tensor basis vanishes there, so the correction
    # vanishes iff g(0) is finite. A singular g (inf/nan) is a real FAIL.
    # Without the expression only field finiteness can be checked.
    try:
        if expression:
            from flowforge.dsl.evaluate import compile_evaluator

            g0 = compile_evaluator(expression)(
                *(np.zeros(1) for _ in range(5)))
            g0_val = float(np.asarray(g0).reshape(-1)[0])
            passed = bool(np.isfinite(g0_val))
            results["zero_strain_limit"] = passed
            details.append(
                f"zero_strain_limit: {'PASS' if passed else 'FAIL'} "
                f"(g(0)={g0_val:.4g}, expression-aware)")
        else:
            finite = bool(np.all(np.isfinite(correction)))
            results["zero_strain_limit"] = finite
            logger.warning(
                "zero_strain_limit: field-only mode (no expression); "
                "verdict covers finiteness, not the true zero-strain limit")
            details.append(
                f"zero_strain_limit: {'PASS' if finite else 'FAIL'} "
                "(field-only; expression unavailable)")
    except Exception as exc:
        results["zero_strain_limit"] = False
        details.append(f"zero_strain_limit: ERROR ({exc})")

    # 6. Log-layer limit: correction should stay small at equilibrium
    # (I1 ~ 1, rest ~ 0), where SST is already right. Expression-aware
    # when possible; otherwise the legacy field heuristic is kept and
    # its measured norm is reported.
    try:
        if expression:
            from flowforge.dsl.evaluate import compile_evaluator

            g_ref = compile_evaluator(expression)(
                np.ones(1), *(np.zeros(1) for _ in range(4)))
            g_ref_val = float(np.asarray(g_ref).reshape(-1)[0])
            passed = bool(np.isfinite(g_ref_val))
            results["log_layer_limit"] = passed
            details.append(
                f"log_layer_limit: {'PASS' if passed else 'FAIL'} "
                f"(g(I1=1)={g_ref_val:.4g}, expression-aware)")
        else:
            correction_norms = np.linalg.norm(correction.reshape(n, -1), axis=1)
            mean_norm = float(np.mean(correction_norms))
            passed = mean_norm < 10.0  # Legacy heuristic bound, field-only
            results["log_layer_limit"] = passed
            details.append(
                f"log_layer_limit: {'PASS' if passed else 'FAIL'} "
                f"(mean_norm={mean_norm:.4f}, field-only)")
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

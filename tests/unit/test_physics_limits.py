"""Expression-aware physics limits: real zero-strain / log-layer / rotation.

Field-only mode (no expression) keeps the legacy verdicts; with an
expression the checks evaluate the candidate itself instead of a
trivially-passing stub.
"""
import numpy as np

from flowforge.agents.harness.physics.harness import run_physics_checks
from flowforge.agents.harness.physics.tasks import PhysicsTask


def _valid_correction(n: int = 8, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    raw = 0.01 * rng.standard_normal((n, 3, 3))
    sym = 0.5 * (raw + np.transpose(raw, (0, 2, 1)))
    trace = np.trace(sym, axis1=1, axis2=2)
    for i in range(3):
        sym[:, i, i] -= trace / 3.0
    return sym


def _env(n: int = 8):
    inv = {f"I{i}": np.ones(n) for i in range(1, 6)}
    basis = {"T1": np.eye(3)[None].repeat(n, axis=0)}
    return inv, basis


def test_task_defaults_to_field_only() -> None:
    task = PhysicsTask(candidate_hash="h", case_id="c")
    assert task.expression == ""


def test_zero_expression_is_expression_aware_and_passes() -> None:
    n = 8
    task = PhysicsTask(candidate_hash="h", case_id="c", expression="0")
    inv, basis = _env(n)
    res = run_physics_checks(task, _valid_correction(n), inv, basis)
    assert "expression-aware" in res.details
    assert "zero_strain_limit: PASS" in res.details
    assert "log_layer_limit: PASS" in res.details
    assert "rotation_invariance: PASS" in res.details
    assert res.passed


def test_i1_expression_passes_real_rotation() -> None:
    n = 8
    task = PhysicsTask(candidate_hash="h", case_id="c", expression="I1")
    inv, basis = _env(n)
    res = run_physics_checks(task, _valid_correction(n), inv, basis)
    assert "rotation_invariance: PASS" in res.details
    assert "expression-aware" in res.details


def test_field_only_legacy_verdicts_unchanged() -> None:
    n = 8
    task = PhysicsTask(candidate_hash="h", case_id="c")
    inv, basis = _env(n)
    good = run_physics_checks(task, _valid_correction(n), inv, basis)
    assert good.passed
    assert "field-only" in good.details

    bad = _valid_correction(n).copy()
    bad[:, 0, 1] += 0.5  # break symmetry
    res = run_physics_checks(task, bad, inv, basis)
    assert "symmetry: FAIL" in res.details
    assert not res.passed

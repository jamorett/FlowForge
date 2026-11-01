"""Tests for the classical sparse-regression baseline."""
from __future__ import annotations

import numpy as np

from flowforge.baselines.sparse import evaluate_sparse_baseline, fit_sparse_baseline

_INVARIANT_KEYS = ("I1", "I2", "I3", "I4", "I5")
_BASIS_KEYS = ("T1", "T2", "T3", "T4")
_ALPHA_GRID = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2)


def synthetic_fields(n: int = 400, seed: int = 7) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Deterministic synthetic invariants and tensor basis."""
    rng = np.random.default_rng(seed)
    invariants = {key: rng.uniform(-1.0, 1.0, size=n) for key in _INVARIANT_KEYS}
    basis: dict[str, np.ndarray] = {}
    for key in _BASIS_KEYS:
        mat = rng.normal(size=(n, 3, 3))
        sym = 0.5 * (mat + np.swapaxes(mat, -1, -2))
        trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
        basis[key] = sym - (1.0 / 3.0) * trace * np.eye(3)
    return invariants, basis


def _target_from_expression(
    invariants: dict[str, np.ndarray], basis: dict[str, np.ndarray]
) -> tuple[str, np.ndarray]:
    from flowforge.dsl.evaluate import candidate_anisotropy

    expression = "0.5 * I1 * T1 + (-0.25) * tanh(I2) * T2"
    target = candidate_anisotropy(expression, invariants, basis)
    return expression, target


def test_recovers_known_two_term_expression():
    invariants, basis = synthetic_fields(n=400, seed=7)
    _, target = _target_from_expression(invariants, basis)
    result = fit_sparse_baseline(invariants, basis, target, max_terms=4, seed=42)
    assert result["train"]["ratio"] < 0.05
    tensors = {term["tensor"] for term in result["terms"]}
    assert {"T1", "T2"} <= tensors
    assert len(result["terms"]) <= 4


def test_emitted_text_validates_and_deterministic():
    from flowforge.dsl.parser import validate_candidate

    invariants, basis = synthetic_fields(n=400, seed=7)
    _, target = _target_from_expression(invariants, basis)
    first = fit_sparse_baseline(invariants, basis, target, seed=42)
    second = fit_sparse_baseline(invariants, basis, target, seed=42)
    assert first == second
    validate_candidate(first["expression"])
    rng = np.random.default_rng(0)
    n_points = int(np.asarray(target).shape[0])
    noise = rng.normal(size=(n_points, 3, 3))
    sym = 0.5 * (noise + np.swapaxes(noise, -1, -2))
    trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
    dev_noise = sym - (1.0 / 3.0) * trace * np.eye(3)
    noisy = fit_sparse_baseline(invariants, basis, dev_noise, seed=42)
    validate_candidate(noisy["expression"])


def test_evaluate_sparse_baseline_monkeypatched(monkeypatch):
    import flowforge.data.frozen_fields as frozen

    invariants, basis = synthetic_fields(n=300, seed=11)
    _, target = _target_from_expression(invariants, basis)

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        assert list(case_ids) == ["train_a"]
        return invariants, basis, target

    def fake_score(expression, case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        from flowforge.data.frozen_fields import score_expression

        return {
            cid: score_expression(expression, invariants, basis, target) for cid in list(case_ids)
        }

    monkeypatch.setattr(frozen, "load_frozen_fields", fake_load)
    monkeypatch.setattr(frozen, "score_on_cases", fake_score)
    result = evaluate_sparse_baseline(
        case_ids_train=["train_a"],
        case_ids_validation=["val_a"],
        seed=42,
    )
    assert result["mode"] == "frozen"
    assert result["synthetic"] is False
    assert "val_a" in result["validation"]
    assert result["worst_validation_ratio"] < 0.05
    assert result["train"]["ratio"] < 0.05


def test_recovers_terms_with_different_scales():
    from flowforge.dsl.evaluate import candidate_anisotropy

    invariants, basis = synthetic_fields(n=400, seed=7)
    scaled = dict(invariants)
    scaled["I1"] = np.asarray(invariants["I1"], dtype=float) * 0.005
    expression_true = "0.5 * T3 + 100.0 * I1 * T1"
    target = candidate_anisotropy(expression_true, scaled, basis)
    result = fit_sparse_baseline(scaled, basis, target, max_terms=4, seed=42)
    assert result["train"]["ratio"] < 0.05
    pairs = {(term["feature"], term["tensor"]) for term in result["terms"]}
    assert ("1", "T3") in pairs
    assert ("I1", "T1") in pairs
    assert len(result["terms"]) <= 4


def test_cv_is_deterministic_and_records_grid():
    invariants, basis = synthetic_fields(n=120, seed=7)
    _, target = _target_from_expression(invariants, basis)
    first = fit_sparse_baseline(invariants, basis, target, max_terms=4, seed=42)
    second = fit_sparse_baseline(invariants, basis, target, max_terms=4, seed=42)
    assert first == second
    assert first["alpha"] in list(_ALPHA_GRID)
    assert isinstance(first["cv"], dict)
    assert set(first["cv"].keys()) == {float(item) for item in _ALPHA_GRID}
    for value in first["cv"].values():
        assert np.isfinite(float(value))


def test_explicit_alpha_bypasses_cv(monkeypatch):
    import flowforge.baselines.sparse as sparse_mod

    invariants, basis = synthetic_fields(n=120, seed=7)
    _, target = _target_from_expression(invariants, basis)

    def boom(*args, **kwargs):
        raise AssertionError("CV must not run when alpha is explicit")

    monkeypatch.setattr(sparse_mod, "_cv_errors_for_grid", boom)
    result = fit_sparse_baseline(invariants, basis, target, max_terms=4, seed=42, alpha=1e-3)
    assert result["alpha"] == 1e-3
    assert result["cv"] is None


def test_no_drop_on_independent_synthetic_features():
    from flowforge.baselines.sparse import collinearity_dropped_features

    invariants, _ = synthetic_fields(n=400, seed=7)
    kept, dropped = collinearity_dropped_features(invariants)
    assert dropped == []
    assert kept == ["1", "I1", "I2", "I1*I2", "tanh(I1)", "tanh(I2)"]


def test_collinear_tanh_duplicates_dropped_on_small_invariants():
    from flowforge.baselines.sparse import collinearity_dropped_features
    from flowforge.dsl.parser import validate_candidate

    rng = np.random.default_rng(3)
    small = {key: rng.uniform(-0.02, 0.02, size=300) for key in _INVARIANT_KEYS}
    kept, dropped = collinearity_dropped_features(small)
    assert "tanh(I1)" in dropped
    assert "tanh(I2)" in dropped
    assert "I1" in kept and "I2" in kept

    _, basis = synthetic_fields(n=300, seed=3)
    _, target = _target_from_expression(
        {**small, "I1": small["I1"], "I2": small["I2"]}, basis
    )
    result = fit_sparse_baseline(small, basis, target, max_terms=4, seed=42)
    assert result["dropped_features"] == dropped
    assert result["collinearity_threshold"] == 0.999
    validate_candidate(result["expression"])

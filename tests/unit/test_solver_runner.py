"""Cheap runner invariants. No Docker required."""

from flowforge.solver.runner import compute_run_hash


def test_run_hash_is_deterministic() -> None:
    # Catches: cache keys that change between identical runs.
    a = compute_run_hash("case", "mesh", {"model": "kOmegaSST"})
    b = compute_run_hash("case", "mesh", {"model": "kOmegaSST"})
    assert a == b


def test_run_hash_changes_with_settings() -> None:
    a = compute_run_hash("case", "mesh", {"model": "kOmegaSST"})
    b = compute_run_hash("case", "mesh", {"model": "other"})
    assert a != b

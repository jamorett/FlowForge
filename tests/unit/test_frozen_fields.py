"""Unit tests for flowforge.data.frozen_fields (no data/processed dependency)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def _make_arrays(n: int, fill: float = 0.0) -> dict[str, np.ndarray]:
    """Small valid store payload with constant per-case fill."""
    arrays: dict[str, np.ndarray] = {"coordinates": np.zeros((n, 3), dtype=np.float64)}
    for i in range(1, 6):
        arrays[f"invariants/I{i}"] = np.full((n,), fill + float(i), dtype=np.float64)
    for i in range(1, 5):
        arrays[f"tensor_basis/T{i}"] = np.full((n, 3, 3), fill, dtype=np.float64)
    arrays["targets/a_delta"] = np.full((n, 3, 3), fill + 10.0, dtype=np.float64)
    arrays["targets/Pk_delta"] = np.full((n,), fill, dtype=np.float64)
    return arrays


def _make_indexed_arrays(n: int) -> dict[str, np.ndarray]:
    """Row i encodes i everywhere so subset consistency can be checked."""
    idx = np.arange(n, dtype=np.float64)
    arrays: dict[str, np.ndarray] = {"coordinates": np.zeros((n, 3), dtype=np.float64)}
    for i in range(1, 6):
        arrays[f"invariants/I{i}"] = idx.copy()
    tiled = np.ones((n, 3, 3), dtype=np.float64) * idx[:, None, None]
    for i in range(1, 5):
        arrays[f"tensor_basis/T{i}"] = tiled.copy()
    arrays["targets/a_delta"] = tiled.copy()
    arrays["targets/Pk_delta"] = idx.copy()
    return arrays


def _write(tmp: Path, case_id: str, arrays: dict[str, np.ndarray]) -> Path:
    from flowforge.data.zarr_store import write_case

    path = tmp / case_id
    write_case(path, arrays)
    return path


def test_train_case_ids_matches_config() -> None:
    from flowforge.config import load_cases
    from flowforge.data.frozen_fields import train_case_ids

    expected = [e["id"] for e in load_cases()["cases"] if e["split"] == "train"]
    assert train_case_ids() == expected
    assert expected, "expected at least one train case"


def test_load_concatenates_in_order(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import load_frozen_fields

    proc = tmp_path / "processed"
    _write(proc, "case_a", _make_arrays(4, fill=0.0))
    _write(proc, "case_b", _make_arrays(3, fill=100.0))
    inv, basis, target = load_frozen_fields(["case_a", "case_b"], processed_dir=proc)
    assert set(inv) == {"I1", "I2", "I3", "I4", "I5"}
    assert set(basis) == {"T1", "T2", "T3", "T4"}
    # case_a I1 == 1, case_b I1 == 101; order must follow case_ids.
    assert inv["I1"].shape == (7,)
    assert list(inv["I1"][:4]) == [1.0] * 4
    assert list(inv["I1"][4:]) == [101.0] * 3
    assert basis["T1"].shape == (7, 3, 3)
    assert target.shape == (7, 3, 3)
    assert float(target[0, 0, 0]) == 10.0
    assert float(target[4, 0, 0]) == 110.0


def test_missing_store_message_contains_case_id(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import load_frozen_fields

    proc = tmp_path / "processed"
    proc.mkdir()
    with pytest.raises(FileNotFoundError) as exc:
        load_frozen_fields(["ghost_case"], processed_dir=proc)
    assert "ghost_case" in str(exc.value)


def test_empty_case_ids_raises(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import load_frozen_fields

    with pytest.raises(ValueError):
        load_frozen_fields([], processed_dir=tmp_path)


def test_max_points_deterministic_sorted_and_consistent(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import load_frozen_fields

    proc = tmp_path / "processed"
    _write(proc, "case_a", _make_indexed_arrays(10))
    inv1, basis1, tgt1 = load_frozen_fields(["case_a"], processed_dir=proc, max_points_per_case=4, seed=0)
    inv2, _basis2, tgt2 = load_frozen_fields(["case_a"], processed_dir=proc, max_points_per_case=4, seed=0)
    assert inv1["I1"].shape == (4,)
    assert tgt1.shape == (4, 3, 3)
    # Deterministic across calls with the same seed.
    assert np.array_equal(inv1["I1"], inv2["I1"])
    assert np.array_equal(tgt1, tgt2)
    # Sorted by original index (original was 0..9, so subset stays sorted).
    assert bool(np.all(np.diff(inv1["I1"]) > 0))
    # Same rows for every array of the case.
    assert np.array_equal(inv1["I1"], tgt1[:, 0, 0])
    assert np.array_equal(inv1["I2"], inv1["I1"])
    assert np.array_equal(basis1["T1"][:, 0, 0], inv1["I1"])


def test_fewer_points_keep_all(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import load_frozen_fields

    proc = tmp_path / "processed"
    _write(proc, "tiny", _make_arrays(3, fill=5.0))
    inv, _basis, target = load_frozen_fields(["tiny"], processed_dir=proc, max_points_per_case=10)
    assert inv["I1"].shape == (3,)
    assert target.shape == (3, 3, 3)


def test_locked_path_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowforge.data import split_guard
    from flowforge.data.frozen_fields import load_frozen_fields

    # Isolate the audit log so fake DENIED lines never touch runs/vault_access.log.
    fake_log = tmp_path / "vault_access.log"
    monkeypatch.setattr(split_guard, "LOG", fake_log)
    locked_base = tmp_path / "data" / "locked"
    with pytest.raises(PermissionError):
        load_frozen_fields(["any_case"], processed_dir=locked_base)
    # Traversal into locked via case id must also be denied before any read.
    proc = tmp_path / "data" / "processed"
    proc.mkdir(parents=True)
    with pytest.raises(PermissionError):
        load_frozen_fields(["../locked/evil"], processed_dir=proc)
    assert fake_log.is_file()
    lines = fake_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(line.startswith("DENIED") for line in lines)
    assert any("any_case" in line for line in lines)
    assert any("evil" in line for line in lines)


def test_score_on_cases_reports_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowforge.data.frozen_fields as frozen

    rng = np.random.default_rng(3)
    n = 60
    inv = {k: rng.uniform(-2.0, 2.0, size=n) for k in ("I1", "I2", "I3", "I4", "I5")}
    basis = {}
    for k in ("T1", "T2", "T3"):
        mat = rng.normal(size=(n, 3, 3))
        sym = 0.5 * (mat + np.swapaxes(mat, -1, -2))
        trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
        basis[k] = sym - trace / 3.0 * np.eye(3)
    target = np.zeros((n, 3, 3))

    def fake_load(case_ids, processed_dir="data/processed", max_points_per_case=None, seed=0):
        assert list(case_ids) == ["big"]
        return inv, basis, target

    monkeypatch.setattr(frozen, "load_frozen_fields", fake_load)
    # exp(50*I1) overflows -> physics-guard AssertionError must become an
    # error payload, never an escaped exception (mini-probe).
    scores = frozen.score_on_cases("0.05 * exp(50.0 * I1) * T2", ["big"])
    assert "error" in scores["big"]

"""Unit tests for frozen-mode attack flows (data side)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def _make_arrays(n: int = 4) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {"coordinates": np.zeros((n, 3), dtype=np.float64)}
    for i in range(1, 6):
        arrays[f"invariants/I{i}"] = np.full((n,), float(i), dtype=np.float64)
    for i in range(1, 5):
        arrays[f"tensor_basis/T{i}"] = np.zeros((n, 3, 3), dtype=np.float64)
    arrays["targets/a_delta"] = np.zeros((n, 3, 3), dtype=np.float64)
    arrays["targets/Pk_delta"] = np.zeros((n,), dtype=np.float64)
    return arrays


def _write(proc: Path, case_id: str, n: int = 4) -> Path:
    from flowforge.data.zarr_store import write_case

    path = proc / case_id
    write_case(path, _make_arrays(n))
    return path


def _write_all(proc: Path) -> None:
    from flowforge.data.frozen_fields import ATTACK_FLOWS

    for entry in ATTACK_FLOWS:
        _write(proc, entry["case_id"])


def test_attack_case_for_exact_and_tolerance(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import attack_case_for

    proc = tmp_path / "processed"
    _write_all(proc)
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}, processed_dir=proc) == "periodic_hill_alpha0p5_re5600"
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.8, "reynolds": 5600}, processed_dir=proc) == "periodic_hill_alpha0p8_re5600"
    assert attack_case_for({"kind": "periodic_hill", "alpha": 1.2, "reynolds": 5600}, processed_dir=proc) == "periodic_hill_alpha1p2_re5600"
    # Case-insensitive kind.
    assert attack_case_for({"kind": "PERIODIC_HILL", "alpha": 0.5, "reynolds": 5600}, processed_dir=proc) == "periodic_hill_alpha0p5_re5600"
    # Within tolerance: alpha diff 0.03, reynolds diff ~2.7%.
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.53, "reynolds": 5750}, processed_dir=proc) == "periodic_hill_alpha0p5_re5600"
    # Inclusive alpha boundary (diff exactly 0.05).
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.55, "reynolds": 5600}, processed_dir=proc) == "periodic_hill_alpha0p5_re5600"
    # Outside alpha tolerance.
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.6, "reynolds": 5600}, processed_dir=proc) is None
    # Outside reynolds tolerance (400 / 5600 ~ 7.1% > 5%).
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.5, "reynolds": 6000}, processed_dir=proc) is None


def test_attack_case_for_unknown_kind_and_bad_fields(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import attack_case_for

    proc = tmp_path / "processed"
    _write_all(proc)
    assert attack_case_for({"kind": "curved_step", "alpha": 0.5, "reynolds": 5600}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}, processed_dir=tmp_path / "empty") is None
    assert attack_case_for({"alpha": 0.5, "reynolds": 5600}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "reynolds": 5600}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.5}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "alpha": "bad", "reynolds": 5600}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "alpha": None, "reynolds": 5600}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.5, "reynolds": None}, processed_dir=proc) is None
    assert attack_case_for({"kind": 123, "alpha": 0.5, "reynolds": 5600}, processed_dir=proc) is None
    # Never raise for a bad flow dict.
    assert attack_case_for({}, processed_dir=proc) is None
    assert attack_case_for(None, processed_dir=proc) is None  # type: ignore[arg-type]
    assert attack_case_for("periodic_hill", processed_dir=proc) is None  # type: ignore[arg-type]
    assert attack_case_for([], processed_dir=proc) is None  # type: ignore[arg-type]
    assert attack_case_for({"kind": "periodic_hill", "alpha": float("nan"), "reynolds": 5600}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "alpha": float("inf"), "reynolds": 5600}, processed_dir=proc) is None


def test_attack_case_for_missing_store_returns_none(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import attack_case_for

    proc = tmp_path / "processed"
    proc.mkdir(parents=True)
    # No stores at all.
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}, processed_dir=proc) is None
    # Only one store exists; other alphas still miss.
    _write(proc, "periodic_hill_alpha0p5_re5600")
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}, processed_dir=proc) == "periodic_hill_alpha0p5_re5600"
    assert attack_case_for({"kind": "periodic_hill", "alpha": 0.8, "reynolds": 5600}, processed_dir=proc) is None
    assert attack_case_for({"kind": "periodic_hill", "alpha": 1.2, "reynolds": 5600}, processed_dir=proc) is None


def test_available_attack_flows_listing(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import available_attack_flows

    proc = tmp_path / "processed"
    proc.mkdir(parents=True)
    assert available_attack_flows(processed_dir=proc) == []
    _write(proc, "periodic_hill_alpha0p5_re5600")
    _write(proc, "periodic_hill_alpha1p2_re5600")
    found = available_attack_flows(processed_dir=proc)
    assert {entry["case_id"] for entry in found} == {"periodic_hill_alpha0p5_re5600", "periodic_hill_alpha1p2_re5600"}
    for entry in found:
        assert entry["kind"] == "periodic_hill"
        assert entry["reynolds"] == 5600
    by_id = {entry["case_id"]: entry for entry in found}
    assert by_id["periodic_hill_alpha0p5_re5600"]["alpha"] == pytest.approx(0.5)
    assert by_id["periodic_hill_alpha1p2_re5600"]["alpha"] == pytest.approx(1.2)
    _write(proc, "periodic_hill_alpha0p8_re5600")
    assert len(available_attack_flows(processed_dir=proc)) == 3


def test_attack_disjointness_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import flowforge.config as config_mod
    from flowforge.data import frozen_fields

    proc = tmp_path / "processed"
    _write_all(proc)

    def fake_overlap(root=None):
        return {"cases": [{"id": frozen_fields.ATTACK_FLOWS[0]["case_id"], "split": "train", "source": "test"}]}

    monkeypatch.setattr(config_mod, "load_cases", fake_overlap)
    with pytest.raises(ValueError):
        frozen_fields.attack_case_for({"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}, processed_dir=proc)
    with pytest.raises(ValueError):
        frozen_fields.available_attack_flows(processed_dir=proc)

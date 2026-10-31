"""Unit tests for total-anisotropy realizability gate (rung 3)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def dummy_fields(n: int):
    """Return zero invariants/basis/target with ``n`` points."""
    inv = {f"I{i}": np.zeros((n,), dtype=float) for i in range(1, 6)}
    basis = {f"T{i}": np.zeros((n, 3, 3), dtype=float) for i in range(1, 5)}
    target = np.zeros((n, 3, 3), dtype=float)
    return inv, basis, target


def one_c_mat():
    """Return the 1C corner anisotropy (realizable, traceless)."""
    return np.array([[2.0 / 3.0, 0.0, 0.0], [0.0, -1.0 / 3.0, 0.0], [0.0, 0.0, -1.0 / 3.0]], dtype=float)


def test_correction_alone_fails_but_total_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowforge.dsl.evaluate as eval_mod
    from flowforge.ladder.ladder import rung3_full
    from flowforge.physics.tensors import is_realizable

    npts = 4
    inv, basis, target = dummy_fields(npts)
    dmat = one_c_mat()
    brans = np.tile(dmat, (npts, 1, 1))
    good = np.tile(-dmat, (npts, 1, 1))
    assert bool(np.all(is_realizable(brans)))
    assert not bool(np.all(is_realizable(good)))
    assert bool(np.all(is_realizable(brans + good)))

    def fake(expr: str, inv_arg, basis_arg):
        assert expr == "good"
        return good

    monkeypatch.setattr(eval_mod, "candidate_anisotropy", fake)
    cands = [{"expression": "good", "score": 0.0}]
    got = rung3_full(cands, inv, basis, target, b_rans=brans)
    assert len(got) == 1
    entry = got[0]
    assert entry["realizable"] is True
    assert entry["realizable_fraction"] == pytest.approx(1.0)


def test_total_nonrealizable_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowforge.dsl.evaluate as eval_mod
    from flowforge.ladder.ladder import rung3_full
    from flowforge.physics.tensors import is_realizable

    npts = 4
    inv, basis, target = dummy_fields(npts)
    dmat = one_c_mat()
    brans = np.tile(dmat, (npts, 1, 1))
    bad = np.tile(dmat, (npts, 1, 1))
    assert bool(np.all(is_realizable(bad)))
    assert not bool(np.all(is_realizable(brans + bad)))

    def fake(expr: str, inv_arg, basis_arg):
        assert expr == "bad"
        return bad

    monkeypatch.setattr(eval_mod, "candidate_anisotropy", fake)
    cands = [{"expression": "bad", "score": 0.0}]
    got = rung3_full(cands, inv, basis, target, b_rans=brans)
    assert got == []


def test_legacy_without_b_rans(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowforge.dsl.evaluate as eval_mod
    from flowforge.ladder.ladder import rung3_full

    npts = 4
    inv, basis, target = dummy_fields(npts)
    dmat = one_c_mat()
    good = np.tile(-dmat, (npts, 1, 1))
    bad = np.tile(dmat, (npts, 1, 1))

    def fake(expr: str, inv_arg, basis_arg):
        if expr == "good":
            return good
        if expr == "bad":
            return bad
        raise AssertionError(f"unexpected {expr!r}")

    monkeypatch.setattr(eval_mod, "candidate_anisotropy", fake)
    assert rung3_full([{"expression": "good", "score": 0.0}], inv, basis, target) == []
    got = rung3_full([{"expression": "bad", "score": 0.0}], inv, basis, target)
    assert len(got) == 1
    assert got[0]["realizable"] is True
    assert got[0]["realizable_fraction"] == pytest.approx(1.0)


def test_nonfinite_rows_ignored_for_total_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowforge.dsl.evaluate as eval_mod
    from flowforge.ladder.ladder import rung3_full

    npts = 3
    inv, basis, target = dummy_fields(npts)
    dmat = one_c_mat()
    brans = np.tile(dmat, (npts, 1, 1))
    pred = np.tile(-dmat, (npts, 1, 1))
    pred[2] = np.nan

    def fake(expr: str, inv_arg, basis_arg):
        assert expr == "good"
        return pred

    monkeypatch.setattr(eval_mod, "candidate_anisotropy", fake)
    got = rung3_full([{"expression": "good", "score": 0.0}], inv, basis, target, b_rans=brans)
    assert len(got) == 1
    assert got[0]["realizable_fraction"] == pytest.approx(1.0)


def test_run_ladder_forwards_b_rans(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowforge.dsl.evaluate as eval_mod
    import flowforge.ladder.ladder as ladder_mod
    from flowforge.ladder.ladder import run_ladder

    npts = 2
    inv, basis, target = dummy_fields(npts)
    dmat = one_c_mat()
    brans = np.tile(dmat, (npts, 1, 1))
    good = np.tile(-dmat, (npts, 1, 1))
    monkeypatch.setattr(ladder_mod, "rung0", lambda expr: True)
    monkeypatch.setattr(eval_mod, "candidate_anisotropy", lambda expr, inv_arg, basis_arg: good)
    legacy = run_ladder(["good"], inv, basis, target)
    assert legacy["rung3"] == []
    total = run_ladder(["good"], inv, basis, target, b_rans=brans)
    assert len(total["rung3"]) == 1
    assert total["rung3"][0]["realizable_fraction"] == pytest.approx(1.0)


def test_load_frozen_fields_return_b_rans(tmp_path: Path) -> None:
    from flowforge.data.frozen_fields import load_frozen_fields
    from flowforge.data.zarr_store import write_case

    npts = 8
    idx = np.arange(npts, dtype=float)
    tiled = np.ones((npts, 3, 3), dtype=float) * idx[:, None, None]
    base: dict[str, np.ndarray] = {"coordinates": np.zeros((npts, 3), dtype=float)}
    for num in range(1, 6):
        base[f"invariants/I{num}"] = idx.copy()
    for num in range(1, 5):
        base[f"tensor_basis/T{num}"] = tiled.copy()
    base["targets/a_delta"] = tiled.copy()
    base["targets/Pk_delta"] = idx.copy()
    proc = tmp_path / "processed"
    proc.mkdir()
    store_path = proc / "case_x"
    write_case(store_path, base)
    import zarr

    grp = zarr.open_group(str(store_path), mode="a")
    aniso = grp.require_group("anisotropy")
    aniso.create_dataset("b_dns", data=2.0 * tiled, overwrite=True)
    loaded = load_frozen_fields(["case_x"], processed_dir=proc)
    inv, basis_fields, target = loaded
    assert inv["I1"].shape == (npts,)
    assert basis_fields["T1"].shape == (npts, 3, 3)
    assert target.shape == (npts, 3, 3)
    loaded_rans = load_frozen_fields(["case_x"], processed_dir=proc, return_b_rans=True)
    inv2, basis2, target2, brans2 = loaded_rans
    assert brans2.shape == (npts, 3, 3)
    assert np.array_equal(brans2, tiled)
    assert basis2["T1"].shape == (npts, 3, 3)
    assert np.array_equal(inv2["I1"], target2[:, 0, 0])
    inv3, basis3, target3, brans3 = load_frozen_fields(
        ["case_x"], processed_dir=proc, max_points_per_case=4, seed=0, return_b_rans=True
    )
    assert inv3["I1"].shape == (4,)
    assert target3.shape == (4, 3, 3)
    assert brans3.shape == (4, 3, 3)
    assert np.array_equal(inv3["I1"], brans3[:, 0, 0])
    assert np.array_equal(inv3["I1"], target3[:, 0, 0])
    assert np.array_equal(basis3["T1"][:, 0, 0], inv3["I1"])
    assert bool(np.all(np.diff(inv3["I1"]) > 0))

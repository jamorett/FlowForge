"""Temporal probe (5-Phase Loop, Phase 3) for flowforge/data/zarr_store.py.

Pre-flight hallucination audit:
- Risk: assuming zarr v3 API (create_array / groups API) when pyproject pins
  zarr>=2.17,<3.0.0. Probe only uses v2 surface: open_group, require_group,
  create_dataset(..., overwrite=True), group_keys()/array_keys().
- Risk: slash keys (``invariants/I1``) silently stored flat instead of as a
  group hierarchy, and read-back dropping nested arrays. Probe asserts the
  full hierarchy round-trips.
- Risk: shape drift between /coordinates (N,3), /grad_u (N,3,3),
  /invariants/I* (N,), /tensor_basis/T* (N,3,3), /targets/* .

Run: uv run python scratch/probe_zarr_store.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import zarr

from flowforge.data.zarr_store import read_case, write_case


def main() -> None:
    print(f"numpy={np.__version__} zarr={zarr.__version__}")
    assert int(zarr.__version__.split(".")[0]) == 2, "probe expects zarr v2 (pinned <3.0.0)"
    n = 4
    rng = np.random.default_rng(42)
    arrays: dict[str, np.ndarray] = {
        "coordinates": rng.standard_normal((n, 3)),
        "cell_volumes": np.full(n, 0.25),
        "wall_distance": np.full(n, 0.1),
        "U": rng.standard_normal((n, 3)),
        "p": rng.standard_normal(n),
        "k": np.full(n, 1.0),
        "omega": np.full(n, 10.0),
        "grad_u": rng.standard_normal((n, 3, 3)),
        "targets/a_delta": rng.standard_normal((n, 3, 3)),
        "targets/Pk_delta": rng.standard_normal(n),
    }
    arrays.update({f"invariants/I{i}": rng.standard_normal(n) for i in range(1, 6)})
    arrays.update({f"tensor_basis/T{i}": rng.standard_normal((n, 3, 3)) for i in range(1, 5)})
    with tempfile.TemporaryDirectory() as td:
        store = write_case(Path(td) / "case.zarr", arrays)
        root = zarr.open_group(str(store), mode="r")
        print(f"groups={sorted(root.group_keys())} top_arrays={sorted(root.array_keys())}")
        assert sorted(root.group_keys()) == ["invariants", "targets", "tensor_basis"]
        back = read_case(store)
        print(f"read_keys={sorted(back)}")
        assert set(back) == set(arrays), f"round-trip key mismatch: {set(arrays) ^ set(back)}"
        for key, expected in arrays.items():
            assert np.allclose(back[key], expected), f"value mismatch: {key}"
    print("PROBE OK: zarr v2 hierarchy round-trip verified")


if __name__ == "__main__":
    main()

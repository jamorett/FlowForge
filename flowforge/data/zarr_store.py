"""Zarr storage per case (S4.1). Hierarchy from plan; zarr v2 API.

Hierarchy per case store::

    /coordinates  /cell_volumes  /wall_distance  /U  /p  /k  /omega  /grad_u
    /invariants/I1..I5
    /tensor_basis/T1..T4
    /targets/a_delta, /targets/Pk_delta

Keys are slash-separated (``"invariants/I1"``). ``write_case`` stores them
as real Zarr groups; ``read_case`` walks groups recursively so nested
arrays are never dropped. Embedded assertions enforce ndarray inputs,
complete I1..I5 / T1..T4 groups when present, and a shared leading cell
count across arrays (no silent shape drift).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FIELDS = ("coordinates", "cell_volumes", "wall_distance", "U", "p", "k", "omega", "grad_u")
INVARIANTS = tuple(f"I{i}" for i in range(1, 6))
TENSOR_BASIS = tuple(f"T{i}" for i in range(1, 5))
TARGETS = ("a_delta", "Pk_delta")
_GROUPS = {"invariants": INVARIANTS, "tensor_basis": TENSOR_BASIS, "targets": TARGETS}


def _validate_arrays(arrays: dict[str, np.ndarray]) -> None:
    assert isinstance(arrays, dict) and arrays, "arrays must be a non-empty dict"
    for name, arr in arrays.items():
        assert isinstance(name, str) and name and not name.startswith("/") and ".." not in name.split("/"), (
            f"invalid dataset key: {name!r}"
        )
        assert isinstance(arr, np.ndarray), f"{name} must be ndarray, got {type(arr).__name__}"
    for group, members in _GROUPS.items():
        present = {k.split("/", 1)[1] for k in arrays if k.startswith(f"{group}/")}
        if present:
            assert present == set(members), (
                f"{group}/ must contain exactly {members}, got {sorted(present)}"
            )
    if "coordinates" in arrays:
        coords = arrays["coordinates"]
        assert coords.ndim >= 2 and coords.shape[-1] == 3, (
            f"coordinates must end in (..., 3), got {coords.shape}"
        )
        n_cells = coords.shape[0]
        for name, arr in arrays.items():
            assert arr.shape and arr.shape[0] == n_cells, (
                f"{name} leading dim {arr.shape} != n_cells={n_cells} from coordinates"
            )
        cell_shape = coords.shape[:-1]
        for name in (f"invariants/{m}" for m in INVARIANTS):
            if name in arrays:
                assert arrays[name].shape == cell_shape, (
                    f"{name} must have shape {cell_shape}, got {arrays[name].shape}"
                )
        for name in [f"tensor_basis/{m}" for m in TENSOR_BASIS] + ["grad_u", "targets/a_delta"]:
            if name in arrays:
                assert arrays[name].shape == (*cell_shape, 3, 3), (
                    f"{name} must have shape {(*cell_shape, 3, 3)}, got {arrays[name].shape}"
                )


def write_case(store_path: Path, arrays: dict[str, np.ndarray]) -> Path:
    import zarr  # deferred so unit tests run without the solver stack

    assert int(zarr.__version__.split(".")[0]) == 2, (
        f"flowforge pins zarr>=2.17,<3.0.0, found {zarr.__version__}"
    )
    _validate_arrays(arrays)
    store_path = Path(store_path)
    store_path.mkdir(parents=True, exist_ok=True)
    root = zarr.open_group(str(store_path), mode="w")
    for name in sorted(arrays):
        arr = arrays[name]
        if "/" in name:
            group_name, leaf = name.rsplit("/", 1)
            group = root.require_group(group_name)
            group.create_dataset(leaf, data=arr, overwrite=True)
        else:
            root.create_dataset(name, data=arr, overwrite=True)
    return store_path


def read_case(store_path: Path) -> dict[str, np.ndarray]:
    import zarr

    root = zarr.open_group(str(store_path), mode="r")
    out: dict[str, np.ndarray] = {}

    def _walk(group: object, prefix: str) -> None:
        for key in group.array_keys():  # type: ignore[attr-defined]
            out[f"{prefix}{key}"] = group[key][:]  # type: ignore[index]
        for key in group.group_keys():  # type: ignore[attr-defined]
            _walk(group[key], f"{prefix}{key}/")  # type: ignore[index]

    _walk(root, "")
    return out

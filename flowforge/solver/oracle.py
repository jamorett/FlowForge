"""Oracle mapping: DNS-derived corrections onto a solver mesh (S2 gate).

Pipeline:
  1. :func:`load_oracle_fields` reads coordinates, ``targets/a_delta``,
     ``targets/Pk_delta`` and ``U_dns`` from a processed case store.
  2. :func:`uniform_block_mesh_centers` gives the cell centers of the
     (uniform, single-block) template mesh in OpenFOAM cell order
     (x fastest — verified against ``writeCellCentres`` output to
     machine precision for the 90x30 periodicHill template).
  3. :func:`map_to_mesh` nearest-neighbour-interpolates dataset fields
     onto those centers and symmetrizes the anisotropy correction.
  4. :func:`pk_scale_factor` matches the dimensionful production
     correction to the solve's velocity scale (the dataset is stored
     at a different bulk velocity than the template's Ub=1 inlet).
  5. :func:`normalized_rms_error` compares velocity fields
     scale-free; the oracle gate is
     ``err_corrected <= oracle_ratio * err_baseline`` with
     ``oracle_ratio`` frozen in ``configs/tolerances.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def load_oracle_fields(store_path: Path) -> dict[str, np.ndarray]:
    """DNS-derived oracle data for one processed case store."""
    import zarr

    store_path = Path(store_path)
    try:
        group = zarr.open_group(str(store_path), mode="r")
        coords = group["coordinates"][:]
        a_delta = group["targets"]["a_delta"][:]
        pk_delta = group["targets"]["Pk_delta"][:]
        u_dns = group["U_dns"][:]
        b_dns = group["anisotropy"]["b_dns"][:]
    except KeyError as exc:
        raise KeyError(
            f"oracle store {store_path} lacks {exc}; "
            "re-run python -m flowforge.data.ingest_csv"
        ) from exc
    return {
        "coordinates": np.asarray(coords, dtype=float),
        "a_delta": np.asarray(a_delta, dtype=float),
        "pk_delta": np.asarray(pk_delta, dtype=float),
        "u_dns": np.asarray(u_dns, dtype=float),
        "b_dns": np.asarray(b_dns, dtype=float),
    }


def uniform_block_mesh_centers(nx: int, ny: int, nz: int,
                               lo: tuple[float, float, float],
                               hi: tuple[float, float, float]) -> np.ndarray:
    """Cell centers of a uniform single-block mesh in OpenFOAM order."""
    axes = [
        (np.arange(n) + 0.5) * (hi[d] - lo[d]) / n + lo[d]
        for d, n in enumerate((nx, ny, nz))
    ]
    xx, yy, zz = np.meshgrid(axes[0], axes[1], axes[2], indexing="xy")
    return np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1)


def map_to_mesh(data: dict[str, np.ndarray],
                centers: np.ndarray) -> dict[str, np.ndarray]:
    """Nearest-neighbour dataset -> mesh mapping for oracle fields."""
    from scipy.spatial import cKDTree

    tree = cKDTree(data["coordinates"])
    _, idx = tree.query(centers)
    a = data["a_delta"][idx]
    a = 0.5 * (a + np.swapaxes(a, -1, -2))  # exact symmetry for the writer
    out = {
        "a_delta": a,
        "pk_delta": data["pk_delta"][idx],
        "u_dns": data["u_dns"][idx],
    }
    if "b_dns" in data:
        b = data["b_dns"][idx]
        out["b_dns"] = 0.5 * (b + np.swapaxes(b, -1, -2))
    return out


def read_latest_field(stage_path: Path, name: str) -> np.ndarray:
    """Read a latest-time ``nonuniform List<>`` field file.

    Returns ``(N,)`` for scalars, ``(N,3)`` for vectors and ``(N,3,3)``
    for tensors (OpenFOAM row-major order). Used for solver-native
    fields such as ``nut`` and ``grad(U)`` that ``read_fields`` does
    not cover.
    """
    import re

    stage_path = Path(stage_path)
    time_dirs = sorted(
        (d for d in stage_path.iterdir()
         if d.is_dir() and re.fullmatch(r"[0-9.]+", d.name)),
        key=lambda d: float(d.name),
    )
    assert time_dirs, f"no time directories under {stage_path}"
    text = (time_dirs[-1] / name).read_text(encoding="utf-8")
    header = re.search(r"nonuniform List<(\w+)>\s+(\d+)\s*\(", text)
    assert header, f"{name}: no nonuniform list found"
    kind, n = header.group(1), int(header.group(2))
    # The header pattern already consumed the list opener, so the first
    # values in the tail are the list itself (scalar lists pack several
    # values per line; only leading values are taken, never the
    # boundaryField keywords that follow). The number pattern requires
    # digit adjacency, so stray letters cannot match.
    tail = text[header.end():]
    num_re = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
    per_row = {"scalar": 1, "vector": 3, "tensor": 9, "symmTensor": 6}[kind]
    nums = [float(v) for v in num_re.findall(tail)][:n * per_row]
    assert len(nums) >= n * per_row, f"{name}: short list"
    if kind == "scalar":
        return np.asarray(nums[:n], dtype=float)
    rows = np.asarray(nums, dtype=float).reshape(n, per_row)
    if kind == "vector":
        return rows
    if kind == "tensor":
        return rows.reshape(n, 3, 3)
    full = np.zeros((n, 3, 3))
    idx = [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)]
    for k, (i, j) in enumerate(idx):
        full[:, i, j] = full[:, j, i] = rows[:, k]
    return full


def boussinesq_anisotropy(nut: np.ndarray, grad_u: np.ndarray,
                          k: np.ndarray) -> np.ndarray:
    """SST-implied anisotropy ``b = -nut*dev(S)/k`` on the solve's mesh."""
    nut = np.asarray(nut, dtype=float)
    k = np.maximum(np.asarray(k, dtype=float), 1e-12)
    strain = 0.5 * (grad_u + np.swapaxes(grad_u, -1, -2))
    trace = np.trace(strain, axis1=-2, axis2=-1)[:, None, None]
    dev = strain - trace / 3.0 * np.eye(3)
    b = -nut[:, None, None] * dev / k[:, None, None]
    b = 0.5 * (b + np.swapaxes(b, -1, -2))
    trace_b = np.trace(b, axis1=-2, axis2=-1)[:, None, None]
    return b - trace_b / 3.0 * np.eye(3)


def recalibrate(mapped: dict[str, np.ndarray], nut: np.ndarray,
                 grad_u: np.ndarray, k: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Oracle targets referenced to OUR baseline, not the dataset's RANS.

    ``mapped`` carries ``u_dns`` on our mesh. The anisotropy our SST
    actually implies (from its own nut/strain/k) replaces the foreign
    table's ``b_sst``, and the production target is rebuilt in solver
    units — no bulk-velocity rescaling guess is needed.
    """
    b_ours = boussinesq_anisotropy(nut, grad_u, k)
    b_dns = mapped["b_dns"] if "b_dns" in mapped else None
    if b_dns is None:
        raise KeyError("mapped needs 'b_dns': DNS anisotropy on our mesh")
    a_star = b_dns - b_ours
    a_star = 0.5 * (a_star + np.swapaxes(a_star, -1, -2))
    strain = 0.5 * (grad_u + np.swapaxes(grad_u, -1, -2))
    contraction = np.einsum("...ij,...ij->...", a_star, strain)
    pk_star = -2.0 * np.maximum(np.asarray(k, dtype=float), 0.0) * contraction
    return a_star, pk_star


def normalized_rms_error(u_sim: np.ndarray, u_ref: np.ndarray) -> float:
    """Scale-free RMS distance between two (N,3) velocity fields."""
    u_sim = np.asarray(u_sim, dtype=float)
    u_ref = np.asarray(u_ref, dtype=float)
    assert u_sim.shape == u_ref.shape and u_sim.ndim == 2, (
        f"shape mismatch {u_sim.shape} vs {u_ref.shape}"
    )
    ss, sr = (np.abs(u_sim).max(), np.abs(u_ref).max())
    assert ss > 0 and sr > 0, "cannot normalize a zero field"
    return float(np.sqrt(np.mean((u_sim / ss - u_ref / sr) ** 2)))

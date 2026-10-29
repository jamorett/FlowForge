"""Hill-geometry block mesh from dataset wall profile (S1/S2).

The flat template mesh cannot see separation physics, so any closure
correction is a second-order ripple on a geometry-dominated error. This
module builds the true periodic-hill mesh instead:

1. :func:`extract_wall_profile` bins the dataset cell centers by x and
   takes the floor envelope — the wall trace, periodic by construction
   (ends blended to a common value).
2. :func:`write_hill_block_mesh` writes a single-hex-block blockMeshDict
   whose lower edge is a ``splineEdge`` through that profile; the
   interior relaxes by transfinite interpolation. Patches keep the
   template names (walls/cyclicX1/cyclicX2/frontAndBack) so the rest of
   the case is untouched.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def extract_wall_profile(store_path: Path, n_bins: int = 360,
                         x_max: float = 9.0,
                         smooth: bool = True) -> np.ndarray:
    """Lower-wall ``(x, y)`` envelope from a processed case store.

    ``smooth=False`` keeps the raw windowed minimum: exact to the data
    (stair-steppy at bin width). Displacement meshing wants exact;
    spline meshing wanted smooth.
    """
    import zarr

    coords = np.asarray(
        zarr.open_group(str(store_path), mode="r")["coordinates"][:])
    edges = np.linspace(0.0, x_max, n_bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    # Windowed minimum (half-width 0.075): narrow bins can miss the wall
    # where the dataset grid is coarse, leaving interior points as a
    # false floor. A window wider than any data gap always sees the wall.
    xs, ys = coords[:, 0], coords[:, 1]
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    wall = np.full(n_bins, np.nan)
    half_width = 0.075
    for i, xc in enumerate(centers):
        lo = np.searchsorted(xs, xc - half_width, side="left")
        hi = np.searchsorted(xs, xc + half_width, side="right")
        if hi > lo:
            wall[i] = ys[lo:hi].min()
    # Edge bins can be empty (dataset spans a sub-interval of [0, 9]):
    # nearest-fill them so the spline covers the full period.
    valid = ~np.isnan(wall)
    assert valid.sum() >= 4, "too few populated x-bins for a wall profile"
    wall = np.interp(centers, centers[valid], wall[valid])
    if smooth:
        # The min-envelope is stair-step noisy; a spline through raw
        # bins folds faces. Periodic moving-average first (wrap).
        window, passes = 9, 3
        kernel = np.ones(window) / window
        padded = np.concatenate([wall[-window:], wall, wall[:window]])
        for _ in range(passes):
            padded = np.convolve(padded, kernel, mode="same")
        wall = padded[window:-window][:n_bins]
    # Exact periodicity: blend the ends to their mean.
    joint = 0.5 * (wall[0] + wall[-1])
    wall[0] = wall[-1] = joint
    return np.stack([centers, wall], axis=1)


def displace_hill_mesh(case_dir: Path, profile: np.ndarray,
                       height: float = 3.036, grade: float = 0.0,
                       ny: int = 30) -> Path:
    """Terrain-following hill mesh by displacing a flat blockMesh.

    Takes a meshed flat case (``constant/polyMesh`` present) and lifts
    every point: ``y' = yg + wall(x)*(1 - yg/height)`` — full wall
    profile at the bottom, untouched top. Deterministic and exact,
    unlike curved blockMesh edges (whose v2512 spline/polyLine fit
    attenuates sharp profiles instead of interpolating them).

    ``grade`` (default 0 = uniform) applies symmetric exponential
    clustering toward both walls first: ``grade=3.5`` puts the first
    cell at y+~7 on this rig. Grading is a pure function of the row
    index, so cyclic faces still match point-for-point.
    """
    import re

    points_path = Path(case_dir) / "constant" / "polyMesh" / "points"
    text = points_path.read_text(encoding="utf-8")
    header = re.search(r"\n(\d+)\s*\(", text)
    assert header, "points file: no point count found"
    n = int(header.group(1))
    tail = text[header.end():]
    num_re = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
    nums = [float(v) for v in num_re.findall(tail)][:n * 3]
    assert len(nums) >= n * 3, "points file: short list"
    pts = np.asarray(nums[:n * 3], dtype=float).reshape(n, 3)
    y_flat = pts[:, 1]
    if grade > 0:
        assert ny % 2 == 0, "grading needs an even row count"
        half = ny // 2
        rows = np.clip(np.round(y_flat / height * ny).astype(int), 0, ny)

        def one_side(frac: np.ndarray) -> np.ndarray:
            return (np.exp(grade * frac) - 1.0) / (np.exp(grade) - 1.0)

        yg = np.empty_like(y_flat)
        lower = rows <= half
        yg[lower] = (height / 2.0) * one_side(rows[lower] / half)
        yg[~lower] = height - (height / 2.0) * one_side(
            (ny - rows[~lower]) / half)
    else:
        yg = y_flat
    wall = np.interp(pts[:, 0], profile[:, 0], profile[:, 1],
                     left=profile[0, 1], right=profile[-1, 1])
    pts[:, 1] = yg + wall * (1.0 - yg / height)
    body = "\n".join(
        "(%.6f %.6f %.6f)" % (x, y, z) for x, y, z in pts)
    new_text = text[:header.end()] + "\n" + body + "\n)\n"
    points_path.write_text(new_text, encoding="utf-8")
    return points_path


def write_hill_block_mesh(case_dir: Path, profile: np.ndarray,
                          nx: int = 90, ny: int = 30, nz: int = 1,
                          height: float = 3.036, zmax: float = 0.1,
                          n_spline: int = 91) -> Path:
    """Write ``system/blockMeshDict`` with a spline lower wall."""
    assert profile.ndim == 2 and profile.shape[1] == 2
    assert len(profile) >= n_spline and n_spline >= 4
    # The mesh spans the full period: bin centers stop short of the
    # boundaries, but the pinned spline ends close it exactly.
    dx = float(profile[1, 0] - profile[0, 0]) if len(profile) > 1 else 0.0
    x_max = float(profile[:, 0].max()) + dx / 2.0
    pick = np.linspace(0, len(profile) - 1, n_spline).round().astype(int)
    pts = profile[pick].copy()
    # Pin the spline ends exactly at the period corners (== vertices):
    # an unpinned spline overshoots past the bin centers.
    pts[0, 0], pts[-1, 0] = 0.0, x_max
    joint = 0.5 * (pts[0, 1] + pts[-1, 1])
    pts[0, 1] = pts[-1, 1] = joint
    spline = "\n".join(
        f"        ({x:.6f} {y:.6f} 0)" for x, y in pts)
    # Spline edges are pinned at the corner vertices, so the corners
    # sit ON the wall (periodic: both ends share the joint value).
    y_end = float(pts[0, 1])
    assert abs(float(pts[-1, 1]) - y_end) < 1e-9, "wall must be periodic"
    text = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
// Periodic-hill mesh (S1 refinement): single hex block whose lower
// edge follows the dataset wall profile; interior relaxes by
// transfinite interpolation. Patches keep template names.
scale 1;
vertices
(
    (0 {y_end:.6f} 0) ({x_max} {y_end:.6f} 0) ({x_max} {height} 0) (0 {height} 0)
    (0 {y_end:.6f} {zmax}) ({x_max} {y_end:.6f} {zmax}) ({x_max} {height} {zmax}) (0 {height} {zmax})
);
blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);
edges
(
    // polyLine, not spline: a 91-point dense polyline is smooth at this
    // resolution, and blockMesh's spline fit attenuates sharp profiles
    // instead of interpolating them (measured: +0.33 wall lift).
    polyLine 0 1
    (
{spline}
    )
);
boundary
(
    walls
    {{
        type wall;
        faces ((0 1 5 4) (3 2 6 7));
    }}
    cyclicX1
    {{
        type cyclic;
        neighbourPatch cyclicX2;
        faces ((0 3 7 4));
    }}
    cyclicX2
    {{
        type cyclic;
        neighbourPatch cyclicX1;
        faces ((1 2 6 5));
    }}
    frontAndBack
    {{
        type empty;
        faces ((0 1 2 3) (4 5 6 7));
    }}
);
"""
    out = Path(case_dir) / "system" / "blockMeshDict"
    out.write_text(text, encoding="utf-8")
    return out

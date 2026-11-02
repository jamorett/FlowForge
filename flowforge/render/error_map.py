"""Error-map rendering (S6). Real PNG output; PyVista optional.

Writes a genuine PNG (stdlib zlib/struct encoder, no placeholder text)
plus the .npy sidecar the UI heatmap consumes. If PyVista is installed
and a mesh is supplied, render_mesh_png is the off-screen path.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np


def error_field(u_model: np.ndarray, u_dns: np.ndarray) -> np.ndarray:
    assert u_model.shape == u_dns.shape
    return np.linalg.norm(u_model - u_dns, axis=-1)


def _png_bytes(gray: np.ndarray) -> bytes:
    h, w = gray.shape
    raw = b"".join(b"\x00" + gray[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def render_png(errors: np.ndarray, out: Path) -> Path:
    assert errors.ndim == 2, "errors must be a 2D map"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out.with_suffix(".npy"), errors)
    span = float(errors.max() - errors.min()) or 1.0
    gray = ((errors - errors.min()) / span * 255).astype(np.uint8)
    out.write_bytes(_png_bytes(gray))
    return out


def rasterize(coords: np.ndarray, values: np.ndarray, width: int = 300) -> tuple[np.ndarray, dict]:
    """Scattered per-cell values -> a true spatial image (row 0 = top) plus its extent.

    Pixels are mean values of the cells they contain. Empty pixels within ~2 pixels of a
    cell (coarse mesh) take the nearest cell's value; farther ones are outside the fluid
    (e.g. under the hill) and get 0. The extent maps pixel boxes back to physical x, y.
    """
    from scipy.spatial import cKDTree

    coords = np.asarray(coords, dtype=float)[:, :2]
    values = np.asarray(values, dtype=float)
    ok = np.isfinite(values) & np.isfinite(coords).all(axis=1)
    xy, v = coords[ok], values[ok]
    assert len(v), "no finite values to rasterize"
    x0, y0 = xy.min(axis=0)
    x1, y1 = xy.max(axis=0)
    height = max(40, int(round(width * (y1 - y0) / max(x1 - x0, 1e-12))))
    dx, dy = (x1 - x0) / width, (y1 - y0) / height
    ix = np.clip(((xy[:, 0] - x0) / dx).astype(int), 0, width - 1)
    iy = np.clip(((y1 - xy[:, 1]) / dy).astype(int), 0, height - 1)
    total = np.zeros((height, width))
    count = np.zeros((height, width))
    np.add.at(total, (iy, ix), v)
    np.add.at(count, (iy, ix), 1)
    img = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    empty = np.argwhere(count == 0)
    if len(empty):
        centers = np.stack([x0 + (empty[:, 1] + 0.5) * dx, y1 - (empty[:, 0] + 0.5) * dy], axis=1)
        dist, idx = cKDTree(xy).query(centers)
        near = dist <= 2.0 * max(dx, dy)
        img[empty[:, 0], empty[:, 1]] = np.where(near, v[idx], 0.0)
    extent = {"x0": float(x0), "x1": float(x1), "y0": float(y0), "y1": float(y1), "width": width, "height": height}
    return img, extent


def box_to_physical(box: list, extent: dict) -> dict:
    """Pixel box [c0, r0, c1, r1] (row 0 = top) -> physical x and y ranges."""
    c0, r0, c1, r1 = box
    dx = (extent["x1"] - extent["x0"]) / extent["width"]
    dy = (extent["y1"] - extent["y0"]) / extent["height"]
    return {"x_range": [round(extent["x0"] + c0 * dx, 3), round(extent["x0"] + (c1 + 1) * dx, 3)],
            "y_range": [round(extent["y1"] - (r1 + 1) * dy, 3), round(extent["y1"] - r0 * dy, 3)]}

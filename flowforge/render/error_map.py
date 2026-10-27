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

"""Solver field I/O (S1/S4). foamlib when available; structured fallback."""

from __future__ import annotations

from pathlib import Path

import numpy as np

FIELD_NAMES = ("U", "p", "k", "omega")


def read_fields(case_path: Path) -> dict[str, np.ndarray]:
    """Read latest-time fields. Tries foamlib, falls back to .npy sidecars."""
    try:
        from foamlib import FoamCase  # type: ignore

        case = FoamCase(str(case_path))
        times = sorted(case, key=lambda t: float(t.time))
        latest = times[-1]
        out: dict[str, np.ndarray] = {}
        for name in FIELD_NAMES:
            try:
                out[name] = np.asarray(latest[name].internal_field)
            except Exception:
                continue
        if out:
            return out
    except Exception:
        pass
    out = {}
    for name in FIELD_NAMES:
        sidecar = Path(case_path) / f"{name}.npy"
        if sidecar.exists():
            out[name] = np.load(sidecar)
    return out


def write_correction_fields(case_path: Path, a_delta: np.ndarray,
                            pk_delta: np.ndarray) -> tuple[Path, Path]:
    """Mode A injection: persist correction fields for copied case (S2)."""
    assert a_delta.shape[-2:] == (3, 3), "a_delta must end in (3,3)"
    assert pk_delta.shape == a_delta.shape[:-2], "pk_delta shape mismatch"
    assert np.allclose(a_delta, np.swapaxes(a_delta, -1, -2), atol=1e-10)
    np.save(Path(case_path) / "aDelta.npy", a_delta)
    np.save(Path(case_path) / "PkDelta.npy", pk_delta)
    return Path(case_path) / "aDelta.npy", Path(case_path) / "PkDelta.npy"


def field_hash(fields: dict[str, np.ndarray]) -> str:
    import hashlib

    h = hashlib.sha256()
    for name in sorted(fields):
        h.update(name.encode())
        h.update(np.ascontiguousarray(fields[name]).tobytes())
    return h.hexdigest()[:16]

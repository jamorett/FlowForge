"""Solver field I/O (S1/S4). foamlib when available; structured fallback."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

FIELD_NAMES = ("U", "p", "k", "omega")


def _read_sidecars(case_path: Path) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for name in FIELD_NAMES:
        sidecar = case_path / f"{name}.npy"
        if sidecar.exists():
            try:
                out[name] = np.load(sidecar)
            except Exception as exc:
                logger.error(
                    "read_fields: failed to load sidecar %s (%s: %s)",
                    sidecar, type(exc).__name__, exc,
                )
                raise
    return out


def read_fields(case_path: Path) -> dict[str, np.ndarray]:
    """Read latest-time fields. Tries foamlib, falls back to .npy sidecars.

    Failure honesty (CH-09): failures are never silently swallowed.

    - A missing ``case_path`` raises :class:`FileNotFoundError`.
    - Per-field foamlib failures are logged (exception type included) and
      the remaining fields are still tried.
    - If foamlib itself cannot be imported and no ``.npy`` sidecar exists,
      the original :class:`ImportError` (e.g. ``ModuleNotFoundError``)
      is re-raised so a broken environment is distinguishable from a
      case that simply has no fields.  When sidecars do exist they are
      returned, but the import failure is still logged at ERROR level.
    - If foamlib raises at runtime and no sidecar exists, a
      :class:`RuntimeError` chained from the original exception is
      raised instead of silently returning ``{}``.
    - If foamlib succeeds but yields no fields and no sidecar exists,
      a :class:`RuntimeError` is raised instead of ``{}``.
    """
    case_path = Path(case_path)
    if not case_path.exists():
        logger.error(
            "read_fields: case path does not exist: %s (FileNotFoundError)",
            case_path,
        )
        raise FileNotFoundError(f"read_fields: case path does not exist: {case_path}")

    import_error: ImportError | None = None
    runtime_error: Exception | None = None

    try:
        from foamlib import FoamCase  # type: ignore
    except ImportError as exc:
        logger.error(
            "read_fields: foamlib import failed (%s: %s); "
            "falling back to .npy sidecars in %s",
            type(exc).__name__, exc, case_path,
        )
        import_error = exc
    else:
        try:
            case = FoamCase(str(case_path))
            times = sorted(case, key=lambda t: float(t.time))
            latest = times[-1]
            out: dict[str, np.ndarray] = {}
            for name in FIELD_NAMES:
                try:
                    out[name] = np.asarray(latest[name].internal_field)
                except ImportError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "read_fields: failed to read field %r from %s (%s: %s)",
                        name, case_path, type(exc).__name__, exc,
                    )
                    continue
            if out:
                return out
            logger.error(
                "read_fields: foamlib read no fields from %s; "
                "falling back to .npy sidecars",
                case_path,
            )
        except ImportError as exc:
            logger.error(
                "read_fields: foamlib import failed (%s: %s); "
                "falling back to .npy sidecars in %s",
                type(exc).__name__, exc, case_path,
            )
            import_error = exc
        except Exception as exc:
            logger.error(
                "read_fields: foamlib failed for %s (%s: %s); "
                "falling back to .npy sidecars",
                case_path, type(exc).__name__, exc,
            )
            runtime_error = exc

    sidecars = _read_sidecars(case_path)
    if sidecars:
        return sidecars

    if import_error is not None:
        raise import_error
    if runtime_error is not None:
        raise RuntimeError(
            f"read_fields: no fields readable from {case_path}: foamlib failed "
            f"({type(runtime_error).__name__}: {runtime_error}) and no .npy sidecars found"
        ) from runtime_error
    raise RuntimeError(
        f"read_fields: no fields readable from {case_path}: "
        "foamlib returned no fields and no .npy sidecars found"
    )


def write_correction_fields(case_path: Path, a_delta: np.ndarray,
                            pk_delta: np.ndarray) -> tuple[Path, Path]:
    """Mode A injection: persist correction fields for copied case (S2)."""
    assert a_delta.shape[-2:] == (3, 3), "a_delta must end in (3,3)"
    assert pk_delta.shape == a_delta.shape[:-2], "pk_delta shape mismatch"
    assert np.allclose(a_delta, np.swapaxes(a_delta, -1, -2), atol=1e-10)
    np.save(Path(case_path) / "aDelta.npy", a_delta)
    np.save(Path(case_path) / "PkDelta.npy", pk_delta)
    return Path(case_path) / "aDelta.npy", Path(case_path) / "PkDelta.npy"


def write_openfoam_correction_fields(
    case_dir: Path, a_delta: np.ndarray, pk_delta: np.ndarray
) -> tuple[Path, Path]:
    """Write Mode A correction fields as OpenFOAM ``0/`` field files.

    Unlike :func:`write_correction_fields` (unread ``.npy`` sidecars),
    these files are what the containerised solver actually reads: the
    model constructor ingests ``0/aDelta`` / ``0/PkDelta`` at start time.
    Arrays must be ordered like the mesh cells. Only the
    ``internalField`` entry is replaced; header, dimensions and
    ``boundaryField`` stay exactly as staged.
    """
    import re

    a_delta = np.asarray(a_delta, dtype=float)
    pk_delta = np.asarray(pk_delta, dtype=float)
    assert a_delta.ndim == 3 and a_delta.shape[1:] == (3, 3), (
        f"a_delta must be (N,3,3), got {a_delta.shape}"
    )
    n = a_delta.shape[0]
    assert pk_delta.shape == (n,), f"pk_delta must be ({n},), got {pk_delta.shape}"
    assert np.all(np.isfinite(a_delta)) and np.all(np.isfinite(pk_delta)), (
        "correction fields must be finite"
    )
    asym = np.abs(a_delta - np.swapaxes(a_delta, -1, -2)).max()
    assert asym < 1e-9, f"a_delta must be symmetric (max asym {asym:.3e})"

    sym = np.stack(
        [a_delta[:, 0, 0], a_delta[:, 0, 1], a_delta[:, 0, 2],
         a_delta[:, 1, 1], a_delta[:, 1, 2], a_delta[:, 2, 2]], axis=1,
    )
    body = "\n".join(
        "(" + " ".join(f"{v:.10g}" for v in row) + ")" for row in sym
    )
    a_block = (
        f"internalField   nonuniform List<symmTensor>\n{n}\n(\n{body}\n)\n;"
    )
    p_body = "\n".join(f"{v:.10g}" for v in pk_delta)
    p_block = (
        f"internalField   nonuniform List<scalar>\n{n}\n(\n{p_body}\n)\n;"
    )
    out = []
    for name, block in (("aDelta", a_block), ("PkDelta", p_block)):
        path = Path(case_dir) / "0" / name
        text = path.read_text(encoding="utf-8")
        new, count = re.subn(r"internalField\s+uniform[^;]*;",
                             block, text, count=1)
        assert count == 1, f"no uniform internalField in {path}"
        path.write_text(new, encoding="utf-8")
        out.append(path)
    return out[0], out[1]


def read_cell_centres(case_dir: Path) -> np.ndarray:
    """Cell centers from a ``writeCellCentres`` ``C`` field file.

    Ordering is whatever the mesh dictates (never assumed): the caller
    maps dataset fields onto exactly these points. The ``C`` file lives
    in the time directory ``writeCellCentres`` wrote to (``0/`` when
    run pre-solve, latest time otherwise).
    """
    import re

    case_dir = Path(case_dir)
    candidates = sorted(case_dir.glob("*/C"))
    assert candidates, f"no writeCellCentres C file under {case_dir}"
    lines = candidates[0].read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines)
        if re.fullmatch(r"\d+", line.strip()))
    n = int(lines[start].strip())
    assert lines[start + 1].strip() == "(", f"malformed C list in {candidates[0]}"
    rows = []
    for line in lines[start + 2:start + 2 + n]:
        triplet = line.strip().lstrip("(").rstrip(")").split()
        assert len(triplet) == 3, f"malformed C row: {line!r}"
        rows.append([float(v) for v in triplet])
    assert len(rows) == n, f"C list short: {len(rows)} != {n}"
    return np.asarray(rows, dtype=float)


def field_hash(fields: dict[str, np.ndarray]) -> str:
    import hashlib

    h = hashlib.sha256()
    for name in sorted(fields):
        h.update(name.encode())
        h.update(np.ascontiguousarray(fields[name]).tobytes())
    return h.hexdigest()[:16]

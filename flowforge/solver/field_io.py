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


def field_hash(fields: dict[str, np.ndarray]) -> str:
    import hashlib

    h = hashlib.sha256()
    for name in sorted(fields):
        h.update(name.encode())
        h.update(np.ascontiguousarray(fields[name]).tobytes())
    return h.hexdigest()[:16]

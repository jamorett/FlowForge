"""Data ingestion (S0/S4): raw arrays -> Zarr + derived frozen targets.

Validation on ingest: anisotropy symmetric + trace-free, DNS realizable.
Cases register via configs/cases.yaml splits; locked never ingested here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from flowforge.data.split_guard import guard_path
from flowforge.data.zarr_store import write_case
from flowforge.physics.frozen_rans import anisotropy_target, production_target
from flowforge.physics.tensors import invariants, is_realizable, normalized_tensors, tensor_basis


def validate_anisotropy(b: np.ndarray) -> None:
    assert np.allclose(b, np.swapaxes(b, -1, -2), atol=1e-8), "anisotropy must be symmetric"
    assert np.allclose(np.trace(b, axis1=-2, axis2=-1), 0, atol=1e-8), "anisotropy must be trace-free"
    assert bool(np.all(is_realizable(b))), "DNS anisotropy must be realizable"


def ingest_case(case_id: str, raw: dict[str, np.ndarray], out_dir: Path,
                role: str = "evaluator") -> Path:
    guard_path(Path(f"data/processed/{case_id}"), role=role)
    grad_u, omega = raw["grad_u"], raw["omega"]
    s, w = normalized_tensors(grad_u, omega)
    inv = invariants(s, w)
    basis = tensor_basis(s, w)
    arrays: dict[str, np.ndarray] = dict(raw)
    arrays.update({f"invariants/{k}": v for k, v in inv.items()})
    arrays.update({f"tensor_basis/{k}": v for k, v in basis.items()})
    if "b_dns" in raw and "b_sst" in raw:
        validate_anisotropy(raw["b_dns"])
        a_delta = anisotropy_target(raw["b_dns"], raw["b_sst"])
        strain = 0.5 * (grad_u + np.swapaxes(grad_u, -1, -2))
        arrays["targets/a_delta"] = a_delta
        arrays["targets/Pk_delta"] = production_target(a_delta, raw["k"], strain)
    return write_case(out_dir / case_id, arrays)

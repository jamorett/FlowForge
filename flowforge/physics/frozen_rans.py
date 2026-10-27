"""SpaRTA frozen-RANS targets (S3.2). Exact formulas from plan."""

from __future__ import annotations

import numpy as np


def anisotropy_target(b_dns: np.ndarray, b_sst: np.ndarray) -> np.ndarray:
    assert b_dns.shape == b_sst.shape and b_dns.shape[-2:] == (3, 3)
    return b_dns - b_sst


def production_target(a_delta: np.ndarray, k: np.ndarray, strain: np.ndarray) -> np.ndarray:
    """dPk = -2 k (a_delta : S). strain is dimensional S (1/s)."""
    assert a_delta.shape == strain.shape and a_delta.shape[-2:] == (3, 3), "a_delta/strain shape"
    assert np.all(k >= 0), "k must be non-negative"
    contraction = np.einsum("...ij,...ij->...", a_delta, strain)
    return -2.0 * k * contraction

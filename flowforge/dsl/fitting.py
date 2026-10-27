"""Constant fitting (S3): elastic net + snapping loop. Deterministic seed 42."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import ElasticNet

from flowforge.elegance.engine import SNAP_CANDIDATES


def fit_constants(features: np.ndarray, targets: np.ndarray, seed: int = 42) -> np.ndarray:
    assert features.ndim == 2 and targets.ndim == 1
    assert features.shape[0] == targets.shape[0], "row mismatch"
    model = ElasticNet(alpha=0.01, l1_ratio=0.5, random_state=seed, max_iter=5000)
    model.fit(features, targets)
    return model.coef_


def snap_constants(coefs: np.ndarray, error_fn) -> np.ndarray:
    """Snap one constant at a time if worst-case error rises <=1%."""
    out = coefs.astype(float).copy()
    base = error_fn(out)
    for i in range(len(out)):
        for cand in sorted(SNAP_CANDIDATES, key=lambda c: abs(c - out[i])):
            trial = out.copy()
            trial[i] = cand
            if error_fn(trial) <= 1.01 * base:
                if cand != out[i]:
                    out[i] = cand
                    base = error_fn(out)
                break
    return out

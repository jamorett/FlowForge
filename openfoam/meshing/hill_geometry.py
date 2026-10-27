"""Parametric periodic-hill wall profile (S1/S6).

Hill shape from the standard periodic-hills setup: smooth bumps on the
lower wall, period Lx=9H, height H=1. Used by blockMesh generation and
red-team slope sweeps (alpha scales steepness).
"""

from __future__ import annotations

import numpy as np


def hill_height(x: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    """Lower-wall y(x) for x in [0, 9]. alpha>1 steepens the hills."""
    assert np.all((x >= 0) & (x <= 9.0)), "x must be in [0, 9]"
    # Smooth bump pair per period (dataset-style cosine hills).
    phase = 2.0 * np.pi * x / 9.0
    base = 0.5 * (1.0 - np.cos(phase))
    return (base**alpha) * 1.0


def wall_points(n: int = 100, alpha: float = 1.0) -> np.ndarray:
    x = np.linspace(0.0, 9.0, n)
    y = hill_height(x, alpha=alpha)
    return np.stack([x, y], axis=1)

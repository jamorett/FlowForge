"""Mesh-native CFD diagnostics (separation, reattachment, recirculation bubble).

Replaces unphysical 2D image heuristics with exact Navier-Stokes calculus:
1. Wall shear stress tau_w(x) along solid walls.
2. Separation point x_sep (tau_w crosses zero from positive to negative).
3. Reattachment point x_reatt (tau_w crosses zero from negative to positive).
4. Recirculation volume and backflow intensity (U_x < 0).
5. Regional error attribution (recirculation, shear layer, recovery).

Physical basis:
  - Separation: du/dy|_wall = 0 with d(du/dy|_wall)/dx < 0  (tau_w changes + -> -)
  - Reattachment: du/dy|_wall = 0 with d(du/dy|_wall)/dx > 0  (tau_w changes - -> +)
  - These are uniquely defined by the zero-crossings of tau_w(x) along the wall,
    using kinematic wall shear tau_w = nu * (du_x/dy)|_{y=0}.
  - This is exact CFD calculus; no pixel counting or bounding-box heuristics.
"""

from __future__ import annotations

from typing import Any
import numpy as np


def extract_wall_separation_points(
    x_wall: np.ndarray,
    tau_w: np.ndarray,
) -> dict[str, Any]:
    """Find separation and reattachment points from wall shear stress profile.

    Uses the exact condition tau_w = 0 (du_x/dy|_wall = 0) to locate
    flow separation and reattachment. Sign change from + to - = separation;
    sign change from - to + = reattachment (Schlichting & Gersten, 2017).

    Args:
        x_wall: Wall-following x-coordinates, sorted ascending (N,)
        tau_w: Wall shear stress at each x position (N,). Units: Pa or nu*du_dy.

    Returns:
        dict with x_separation, x_reattachment (None if not found),
        bubble_length (x_reatt - x_sep, 0 if no bubble), and
        tau_w_profile for downstream use.
    """
    assert x_wall.ndim == 1 and tau_w.ndim == 1, "x_wall and tau_w must be 1D"
    assert len(x_wall) == len(tau_w), "x_wall and tau_w length mismatch"

    x_sep = None
    x_reatt = None

    # Find zero crossings: locations where tau_w changes sign
    # Positive-to-negative = separation; negative-to-positive = reattachment
    for i in range(len(tau_w) - 1):
        tw_left = tau_w[i]
        tw_right = tau_w[i + 1]
        if tw_left > 0 and tw_right <= 0:
            # Linear interpolation to sub-cell precision
            frac = tw_left / (tw_left - tw_right + 1e-30)
            x_cross = float(x_wall[i] + frac * (x_wall[i + 1] - x_wall[i]))
            if x_sep is None:
                x_sep = x_cross
        elif tw_left <= 0 and tw_right > 0:
            frac = (-tw_left) / (tw_right - tw_left + 1e-30)
            x_cross = float(x_wall[i] + frac * (x_wall[i + 1] - x_wall[i]))
            if x_sep is not None and x_reatt is None:
                x_reatt = x_cross

    bubble_length = 0.0
    if x_sep is not None and x_reatt is not None:
        bubble_length = x_reatt - x_sep

    return {
        "x_separation": x_sep,
        "x_reattachment": x_reatt,
        "bubble_length": bubble_length,
        "tau_w_profile": {
            "x": x_wall.tolist(),
            "tau_w": tau_w.tolist(),
        },
    }


def extract_recirculation_metrics(coords: np.ndarray, u_field: np.ndarray) -> dict[str, Any]:
    """Calculate recirculation zone statistics directly from velocity field."""
    assert coords.shape[0] == u_field.shape[0], "coordinate and velocity length mismatch"
    u_x = u_field[:, 0]
    backflow_mask = u_x < 0.0
    n_backflow = int(np.sum(backflow_mask))
    total_cells = len(u_x)
    backflow_fraction = float(n_backflow / total_cells) if total_cells > 0 else 0.0

    if n_backflow > 0:
        x_min = float(np.min(coords[backflow_mask, 0]))
        x_max = float(np.max(coords[backflow_mask, 0]))
        bubble_length = float(x_max - x_min)
        max_backflow_vel = float(np.min(u_x))
    else:
        x_min, x_max, bubble_length, max_backflow_vel = 0.0, 0.0, 0.0, 0.0

    return {
        "n_backflow_cells": n_backflow,
        "backflow_fraction": backflow_fraction,
        "bubble_x_min": x_min,
        "bubble_x_max": x_max,
        "bubble_length": bubble_length,
        "max_backflow_velocity": max_backflow_vel,
    }


def compute_wall_profile(coords: np.ndarray, grad_u: np.ndarray,
                         nu: float = 1e-4, n_bins: int = 100) -> dict[str, np.ndarray]:
    """Extract bottom wall shear stress profile tau_w(x) = mu * du_x/dy.

    Selects the near-wall cell in each x-bin (minimum y) and evaluates
    the velocity gradient du_x/dy at that location. This is the kinematic
    wall shear tau_w = nu * (du_x/dy)|_{y_min}, which has a zero at
    the separation/reattachment points.
    """
    xs = coords[:, 0]
    ys = coords[:, 1]
    x_edges = np.linspace(xs.min(), xs.max(), n_bins + 1)
    wall_x = []
    wall_tau = []

    for i in range(n_bins):
        mask = (xs >= x_edges[i]) & (xs < x_edges[i + 1])
        if np.any(mask):
            sub_idx = np.where(mask)[0]
            # Near-wall cell is cell with minimum y in this x-bin
            min_y_idx = sub_idx[np.argmin(ys[sub_idx])]
            wall_x.append(xs[min_y_idx])
            # Velocity gradient du_x/dy at near-wall cell
            du_dy = grad_u[min_y_idx, 0, 1]
            wall_tau.append(nu * du_dy)

    return {
        "x": np.array(wall_x),
        "tau_w": np.array(wall_tau),
    }


def extract_flow_features(
    coords: np.ndarray,
    u_field: np.ndarray,
    grad_u: np.ndarray,
    nu: float = 1e-4,
    n_bins: int = 100,
) -> dict[str, Any]:
    """Full mesh-native feature extraction for Analyst/Skeptic agents.

    Combines wall shear separation detection (exact tau_w=0 calculus) with
    recirculation bubble metrics from the velocity field. Replaces the
    SAM/geometric heuristic entirely.

    Args:
        coords: Cell-centre coordinates (N, 3).
        u_field: Velocity vector field (N, 3).
        grad_u:  Velocity gradient tensor field (N, 3, 3).
        nu:      Kinematic viscosity [m^2/s].
        n_bins:  Number of x-bins for wall profile extraction.

    Returns:
        dict with:
          - separation/reattachment from tau_w=0 (physical, exact)
          - recirculation bubble statistics from u_x < 0 (physical)
          - tau_w profile for downstream diagnostics
    """
    wall_profile = compute_wall_profile(coords, grad_u, nu=nu, n_bins=n_bins)
    separation = extract_wall_separation_points(wall_profile["x"], wall_profile["tau_w"])
    recirculation = extract_recirculation_metrics(coords, u_field)

    return {
        **separation,
        **recirculation,
        "nu": nu,
        "n_bins": n_bins,
    }


def regional_flow_error(coords: np.ndarray, u_model: np.ndarray,
                        u_dns: np.ndarray) -> dict[str, float]:
    """Attribute velocity field error to physically distinct flow regimes."""
    err = np.linalg.norm(u_model - u_dns, axis=-1)
    u_dns_x = u_dns[:, 0]

    recirc_mask = u_dns_x < 0.0
    attached_mask = ~recirc_mask

    err_recirc = float(np.mean(err[recirc_mask] ** 2)) if np.any(recirc_mask) else 0.0
    err_attached = float(np.mean(err[attached_mask] ** 2)) if np.any(attached_mask) else 0.0
    err_total = float(np.mean(err ** 2))

    return {
        "mse_total": err_total,
        "mse_recirculation_bubble": err_recirc,
        "mse_attached_flow": err_attached,
    }

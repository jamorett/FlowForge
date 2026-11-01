"""Unit tests for mesh-native CFD diagnostics (tau_w zero-crossing calculus).

Tests verify:
1. Recirculation metrics from velocity field (backflow cells, bubble extent).
2. Separation/reattachment detection via tau_w = 0 zero-crossings (exact calculus).
3. Regional error attribution across flow regimes.
4. The combined extract_flow_features() pipeline.
"""

import numpy as np
import pytest

from flowforge.physics.diagnostics import (
    compute_wall_profile,
    extract_recirculation_metrics,
    extract_wall_separation_points,
    extract_flow_features,
    regional_flow_error,
)


def test_extract_recirculation_metrics() -> None:
    # 10 cells in a line, 4 with reverse flow
    coords = np.column_stack([np.linspace(0, 9, 10), np.zeros(10), np.zeros(10)])
    u = np.column_stack([
        np.array([1.0, 1.0, -0.5, -1.0, -0.8, -0.2, 0.5, 1.0, 1.2, 1.5]),
        np.zeros(10),
        np.zeros(10),
    ])
    metrics = extract_recirculation_metrics(coords, u)
    assert metrics["n_backflow_cells"] == 4
    assert metrics["backflow_fraction"] == pytest.approx(0.4)
    assert metrics["bubble_x_min"] == pytest.approx(2.0)
    assert metrics["bubble_x_max"] == pytest.approx(5.0)
    assert metrics["bubble_length"] == pytest.approx(3.0)
    assert metrics["max_backflow_velocity"] == pytest.approx(-1.0)


def test_extract_recirculation_metrics_no_backflow() -> None:
    coords = np.column_stack([np.linspace(0, 9, 10), np.zeros(10), np.zeros(10)])
    u = np.column_stack([np.ones(10), np.zeros(10), np.zeros(10)])
    metrics = extract_recirculation_metrics(coords, u)
    assert metrics["n_backflow_cells"] == 0
    assert metrics["backflow_fraction"] == 0.0
    assert metrics["bubble_length"] == 0.0


class TestWallSeparationPoints:
    """Verify tau_w zero-crossing separation/reattachment detection."""

    def test_canonical_periodic_hill_separation(self) -> None:
        """Synthetic tau_w profile: positive upstream, negative over hill lee-side,
        positive downstream. Should detect separation and reattachment exactly.

        Physical setup: tau_w > 0 (attached), tau_w < 0 (separated bubble),
        tau_w > 0 (reattached). Separation at crossing + -> -, reattachment at - -> +.
        """
        x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
        # tau_w: positive (attached), then negative (separated), then positive (reattached)
        tau_w = np.array([0.5, 0.3, 0.1, -0.2, -0.4, -0.3, -0.1, 0.2, 0.4, 0.5])
        result = extract_wall_separation_points(x, tau_w)

        # Separation should be between x=2 and x=3 (tau_w: 0.1 -> -0.2)
        assert result["x_separation"] is not None
        assert 2.0 < result["x_separation"] < 3.0

        # Reattachment should be between x=6 and x=7 (tau_w: -0.1 -> 0.2)
        assert result["x_reattachment"] is not None
        assert 6.0 < result["x_reattachment"] < 7.0

        # Bubble length > 0
        assert result["bubble_length"] > 0.0
        assert result["bubble_length"] == pytest.approx(
            result["x_reattachment"] - result["x_separation"]
        )

    def test_no_separation_fully_attached(self) -> None:
        """Fully attached flow: tau_w > 0 everywhere -> no separation detected."""
        x = np.linspace(0, 9, 20)
        tau_w = np.full(20, 0.3)  # Constant positive wall shear
        result = extract_wall_separation_points(x, tau_w)
        assert result["x_separation"] is None
        assert result["x_reattachment"] is None
        assert result["bubble_length"] == 0.0

    def test_linear_interpolation_precision(self) -> None:
        """Test that linear interpolation gives sub-bin accuracy for zero crossing."""
        # Exact crossing at x=5.0: tau_w crosses zero at midpoint
        x = np.array([4.0, 6.0])  # 2 bins, crossing at x=5.0
        tau_w = np.array([2.0, -2.0])  # Linear: zero exactly at x=5.0
        result = extract_wall_separation_points(x, tau_w)
        assert result["x_separation"] == pytest.approx(5.0, abs=1e-10)

    def test_reattachment_requires_prior_separation(self) -> None:
        """Reattachment without prior separation is not reported."""
        # tau_w starts negative (already separated) and returns to positive
        # x_separation should be None (no + -> - crossing), x_reattachment set
        x = np.array([0.0, 1.0, 2.0, 3.0])
        tau_w = np.array([-0.3, -0.2, -0.1, 0.2])  # Only - -> + transition
        result = extract_wall_separation_points(x, tau_w)
        # No + -> - crossing, so x_separation is None and x_reattachment is also None
        assert result["x_separation"] is None
        assert result["x_reattachment"] is None


def test_regional_flow_error() -> None:
    coords = np.column_stack([np.linspace(0, 9, 4), np.zeros(4), np.zeros(4)])
    u_dns = np.column_stack([np.array([-1.0, -0.5, 1.0, 2.0]), np.zeros(4), np.zeros(4)])
    # Model underpredicts backflow in recirc zone: gives 0.0 instead of -1.0 and -0.5
    u_model = np.column_stack([np.array([0.0, 0.0, 1.0, 2.0]), np.zeros(4), np.zeros(4)])

    err = regional_flow_error(coords, u_model, u_dns)
    # Recirculation error: ((-1)^2 + (-0.5)^2)/2 = 1.25 / 2 = 0.625
    assert err["mse_recirculation_bubble"] == pytest.approx(0.625)
    # Attached error: 0.0
    assert err["mse_attached_flow"] == pytest.approx(0.0)
    # Total error: 1.25 / 4 = 0.3125
    assert err["mse_total"] == pytest.approx(0.3125)


def test_extract_flow_features_pipeline() -> None:
    """Integration test: extract_flow_features produces physically consistent output."""
    n = 50
    rng = np.random.default_rng(42)
    coords = np.column_stack([
        np.linspace(0, 9, n),
        rng.uniform(0.01, 0.1, n),  # Near-wall cells (small y)
        np.zeros(n),
    ])
    # Velocity: forward, then separated, then reattached
    u_x = np.array(
        [1.0] * 15 + [-0.3] * 20 + [0.8] * 15
    )
    u_field = np.column_stack([u_x, np.zeros(n), np.zeros(n)])

    # grad_u: du_x/dy positive (attached) then negative (separated) then positive
    # This directly encodes the wall shear via [0, 1] component
    grad_u = np.zeros((n, 3, 3))
    # du_x/dy: positive, negative, positive pattern (tau_w sign pattern)
    grad_u[:15, 0, 1] = 3.0     # Attached: tau_w > 0
    grad_u[15:35, 0, 1] = -2.0  # Separated: tau_w < 0
    grad_u[35:, 0, 1] = 3.0     # Reattached: tau_w > 0

    result = extract_flow_features(coords, u_field, grad_u, nu=1e-4, n_bins=30)

    # Should detect separation (tau_w goes positive -> negative)
    assert result["x_separation"] is not None
    # Should detect recirculation from velocity
    assert result["n_backflow_cells"] == 20
    assert result["backflow_fraction"] == pytest.approx(0.4)
    # Bubble length from velocity field
    assert result["bubble_length"] > 0.0

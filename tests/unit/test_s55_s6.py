import numpy as np
import pytest

from flowforge.composer.gates import compose
from flowforge.redteam.generator import FlowSpec, generate_attacks


def test_alpha_bounds_enforced() -> None:
    assert all(0.5 <= s.alpha <= 1.5 for s in generate_attacks())
    with pytest.raises(AssertionError):
        generate_attacks(alphas=(2.0,))
    with pytest.raises(AssertionError):
        FlowSpec("periodic_hill", 0.4, 5600)


def test_attacks_never_training() -> None:
    assert all(s.split == "validation" for s in generate_attacks())
    with pytest.raises(AssertionError):
        FlowSpec("periodic_hill", 1.0, 5600, split="train")


def test_gate_formula_and_penalty() -> None:
    out, pen = compose(np.ones((3, 3, 3)), np.zeros((3, 3, 3)), np.zeros(3), 1.0, 0.0)
    assert abs(float(out[0, 0, 0]) - 0.5) < 1e-12
    assert pen == 16.0


def test_api_routes_present() -> None:
    from flowforge.api.server import app, health, matrix, session_state

    paths = {r.path for r in app.routes}
    assert {"/health", "/api/session/state", "/api/matrix", "/ws/events"} <= paths
    assert health() == {"status": "ok"}
    assert session_state("default")["events_per_second"] == 20
    assert len(matrix("default")["flows"]["generated"]) == 12

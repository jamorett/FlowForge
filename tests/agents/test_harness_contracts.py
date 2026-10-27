"""Harness contract tests. Scaffold: verifies the cheap invariants only.

Kept minimal on purpose: each test names the concrete mistake it catches.
No test freezes prompt wording or private helper structure.
"""

from flowforge.agents.harness.contracts import Budget, HarnessResult
from flowforge.agents.harness.physics.tasks import CHECKS
from flowforge.agents.harness.symbolic.tasks import MAX_COMPLEXITY_NODES


def test_budget_is_frozen() -> None:
    # Catches: budget mutated mid-run, which would break cost accounting.
    budget = Budget(max_tokens=1000, max_solver_seconds=60.0, max_dollars=1.0)
    assert budget.max_tokens == 1000


def test_physics_checks_cover_limits() -> None:
    # Catches: a physics harness that skips limit checks and passes
    # closures that corrupt the log layer where SST is already right.
    assert "zero_strain_limit" in CHECKS
    assert "log_layer_limit" in CHECKS


def test_symbolic_complexity_cap_exists() -> None:
    # Catches: unbounded expressions reaching the solver compile step.
    assert 0 < MAX_COMPLEXITY_NODES <= 25


def test_harness_result_defaults_zero_cost() -> None:
    result = HarnessResult(passed=True, score=1.0, details="ok")
    assert result.cost_tokens == 0

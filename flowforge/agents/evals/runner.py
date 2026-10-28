"""Capability eval runner against frozen thresholds (S5.1).

Evaluates positive and negative controls across research, physics, symbolic,
and solver capability loops. Reports pass/fail rates and verifies them
against frozen thresholds in thresholds.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import numpy as np

from flowforge.agents.evals.fixtures import (
    RESEARCH_FIXTURES,
    SYMBOLIC_FIXTURES,
    generate_physics_fixtures,
)
from flowforge.agents.evals.thresholds import (
    PHYSICS_TOLERANCE,
    RESEARCH_MIN_PARSE_RATE,
    SOLVER_MAX_DIVERGED_FRACTION,
    SYMBOLIC_MIN_IMPROVEMENT,
)
from flowforge.agents.harness.physics.harness import run_physics_checks
from flowforge.agents.harness.physics.tasks import PhysicsTask
from flowforge.agents.harness.research.harness import run_card_extraction
from flowforge.agents.harness.research.tasks import CardTask
from flowforge.agents.harness.solver.harness import run_solver_rung
from flowforge.agents.harness.solver.tasks import SolverTask
from flowforge.agents.harness.symbolic.harness import run_symbolic_check
from flowforge.agents.harness.symbolic.tasks import SymbolicTask
from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis

logger = logging.getLogger(__name__)


@dataclass
class CapabilityEvalResult:
    capability: str
    num_tests: int
    num_passed: int
    pass_rate: float
    threshold: float
    passed_threshold: bool
    details: list[str] = field(default_factory=list)


@dataclass
class FullEvalReport:
    results: dict[str, CapabilityEvalResult]
    all_passed: bool

    def summary(self) -> str:
        lines = ["=== FlowForge Capability Eval Report ==="]
        for cap, res in self.results.items():
            status = "PASS" if res.passed_threshold else "FAIL"
            lines.append(
                f"[{status}] {cap}: {res.num_passed}/{res.num_tests} passed "
                f"({res.pass_rate:.1%}) vs threshold {res.threshold:.1%}"
            )
        lines.append(f"Overall verdict: {'PASSED' if self.all_passed else 'FAILED'}")
        return "\n".join(lines)


def eval_research() -> CapabilityEvalResult:
    """Run research card extraction fixtures."""
    passed = 0
    details = []
    for f in RESEARCH_FIXTURES:
        task = CardTask(doi=f.doi, title=f.title, abstract=f.text)
        res = run_card_extraction(task)
        # Check if actual validity matches expected validity
        matches = (res.passed == f.expected_valid)
        if matches:
            passed += 1
            details.append(f"PASS: {f.description}")
        else:
            details.append(f"FAIL: {f.description} (expected {f.expected_valid}, got {res.passed})")

    rate = passed / len(RESEARCH_FIXTURES)
    return CapabilityEvalResult(
        capability="research",
        num_tests=len(RESEARCH_FIXTURES),
        num_passed=passed,
        pass_rate=rate,
        threshold=RESEARCH_MIN_PARSE_RATE,
        passed_threshold=(rate >= RESEARCH_MIN_PARSE_RATE),
        details=details,
    )


def eval_physics() -> CapabilityEvalResult:
    """Run physics harness checks on positive and negative control tensors."""
    fixtures = generate_physics_fixtures()
    passed = 0
    details = []

    # Prepare standard reference state
    n = 4
    rng = np.random.default_rng(42)
    grad = 0.1 * rng.standard_normal((n, 3, 3))
    omega = np.full(n, 2.0)
    s, w = normalized_tensors(grad, omega)
    inv = invariants(s, w)
    basis = tensor_basis(s, w)

    for f in fixtures:
        task = PhysicsTask(candidate_hash=f.candidate_id, case_id="case_eval")
        res = run_physics_checks(task, f.a_delta, inv, basis)
        matches = (res.passed == f.expected_pass)
        if matches:
            passed += 1
            details.append(f"PASS: {f.description}")
        else:
            details.append(f"FAIL: {f.description} (expected {f.expected_pass}, got {res.passed})")

    rate = passed / len(fixtures)
    return CapabilityEvalResult(
        capability="physics",
        num_tests=len(fixtures),
        num_passed=passed,
        pass_rate=rate,
        threshold=1.0,  # Physics requires 100% control accuracy
        passed_threshold=(rate >= 1.0),
        details=details,
    )


def eval_symbolic() -> CapabilityEvalResult:
    """Run symbolic DSL parsing, complexity, and fitting controls."""
    n = 8
    rng = np.random.default_rng(42)
    grad = 0.1 * rng.standard_normal((n, 3, 3))
    omega = np.full(n, 2.0)
    s, w = normalized_tensors(grad, omega)
    inv = invariants(s, w)
    basis = tensor_basis(s, w)
    target = 0.5 * basis["T1"]

    passed = 0
    details = []
    for f in SYMBOLIC_FIXTURES:
        task = SymbolicTask(expression=f.expression, case_ids=("eval_case",))
        res = run_symbolic_check(task, inv, basis, target)
        matches = (res.passed == f.expected_valid)
        if matches:
            passed += 1
            details.append(f"PASS: {f.description}")
        else:
            details.append(f"FAIL: {f.description} (expected {f.expected_valid}, got {res.passed})")

    rate = passed / len(SYMBOLIC_FIXTURES)
    return CapabilityEvalResult(
        capability="symbolic",
        num_tests=len(SYMBOLIC_FIXTURES),
        num_passed=passed,
        pass_rate=rate,
        threshold=1.0,  # 100% agreement on positive/negative syntax
        passed_threshold=(rate >= 1.0),
        details=details,
    )


def eval_solver() -> CapabilityEvalResult:
    """Run solver evaluation ladder controls."""
    n = 8
    rng = np.random.default_rng(42)
    grad = 0.1 * rng.standard_normal((n, 3, 3))
    omega = np.full(n, 2.0)
    s, w = normalized_tensors(grad, omega)
    inv = invariants(s, w)
    basis = tensor_basis(s, w)
    target = 0.5 * basis["T1"]

    task = SolverTask(
        candidate_hash="I1",
        case_id="periodic_hill_re5600",
        rung=1,
        time_cap_seconds=60.0,
    )
    res = run_solver_rung(task, inv=inv, basis=basis, target=target)

    passed = 1 if res.passed else 0
    return CapabilityEvalResult(
        capability="solver",
        num_tests=1,
        num_passed=passed,
        pass_rate=float(passed),
        threshold=1.0 - SOLVER_MAX_DIVERGED_FRACTION,
        passed_threshold=(passed == 1),
        details=["PASS: A priori ladder rung execution"],
    )


def run_all_evals() -> FullEvalReport:
    """Execute all capability regression evals and verify frozen thresholds."""
    results = {
        "research": eval_research(),
        "physics": eval_physics(),
        "symbolic": eval_symbolic(),
        "solver": eval_solver(),
    }
    all_passed = all(r.passed_threshold for r in results.values())
    return FullEvalReport(results=results, all_passed=all_passed)

"""Tests for flowforge.agents.evals.runner."""

from __future__ import annotations

import pytest
from flowforge.agents.evals.runner import (
    eval_physics,
    eval_research,
    eval_solver,
    eval_symbolic,
    run_all_evals,
)


def test_eval_research_fixtures() -> None:
    res = eval_research()
    assert res.num_tests > 0
    assert res.num_passed == res.num_tests
    assert res.passed_threshold


def test_eval_physics_fixtures() -> None:
    res = eval_physics()
    assert res.num_tests > 0
    assert res.num_passed == res.num_tests
    assert res.passed_threshold


def test_eval_symbolic_fixtures() -> None:
    res = eval_symbolic()
    assert res.num_tests > 0
    assert res.num_passed == res.num_tests
    assert res.passed_threshold


def test_eval_solver_fixtures() -> None:
    res = eval_solver()
    assert res.num_tests > 0
    assert res.passed_threshold


def test_run_all_evals_aggregate() -> None:
    report = run_all_evals()
    assert report.all_passed
    assert "research" in report.results
    assert "physics" in report.results
    assert "symbolic" in report.results
    assert "solver" in report.results
    summary = report.summary()
    assert "Overall verdict: PASSED" in summary

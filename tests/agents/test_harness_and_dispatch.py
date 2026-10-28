"""Tests for prompt_loader, dispatcher, and harness modules."""

from __future__ import annotations

import json

import numpy as np
import pytest


# ─────────────────────────── prompt_loader ───────────────────────────


class TestPromptLoader:
    def test_list_roles(self):
        from flowforge.agents.prompt_loader import list_roles
        roles = list_roles()
        assert "board" in roles
        assert "theorist" in roles
        assert "coder" in roles
        assert "analyst" in roles
        assert "skeptic" in roles
        assert "redteam" in roles
        assert "composer" in roles
        assert len(roles) >= 7

    def test_prompt_config_board(self):
        from flowforge.agents.prompt_loader import prompt_config
        cfg = prompt_config("board")
        assert cfg["role"] == "board"
        assert cfg["schema"] == "RoundPlan"
        assert "model" in cfg
        assert "prompt" in cfg

    def test_model_for_role(self):
        from flowforge.agents.prompt_loader import model_for_role
        assert model_for_role("board") == "muse-spark-1.3"
        assert model_for_role("coder") == "muse-code"

    def test_schema_name_for_role(self):
        from flowforge.agents.prompt_loader import schema_name_for_role
        assert schema_name_for_role("board") == "RoundPlan"
        assert schema_name_for_role("theorist") == "CandidateProposal"

    def test_build_prompt_no_context(self):
        from flowforge.agents.prompt_loader import build_prompt
        prompt = build_prompt("board")
        assert "Role: board" in prompt
        assert "RoundPlan" in prompt
        assert len(prompt) > 50

    def test_build_prompt_with_context(self):
        from flowforge.agents.prompt_loader import build_prompt
        ctx = {"findings": ["finding1"], "scores": {"test": 0.5}}
        prompt = build_prompt("board", ctx)
        assert "Context" in prompt
        assert "findings" in prompt
        assert "finding1" in prompt

    def test_prompt_hash_deterministic(self):
        from flowforge.agents.prompt_loader import prompt_hash
        h1 = prompt_hash("test prompt")
        h2 = prompt_hash("test prompt")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_unknown_role_raises(self):
        from flowforge.agents.prompt_loader import prompt_config
        with pytest.raises(FileNotFoundError):
            prompt_config("nonexistent_role")


# ─────────────────────────── dispatcher ───────────────────────────


class TestDispatcher:
    def test_mock_dispatch_all_roles(self):
        from flowforge.agents.dispatcher import dispatch_role_mock
        for role in ("board", "theorist", "coder", "analyst",
                     "skeptic", "redteam", "composer"):
            result = dispatch_role_mock(role)
            assert hasattr(result, "risk_audit")
            assert result.risk_audit.strip()

    def test_mock_board_returns_round_plan(self):
        from flowforge.agents.dispatcher import dispatch_role_mock
        from flowforge.agents.schemas import RoundPlan
        result = dispatch_role_mock("board")
        assert isinstance(result, RoundPlan)
        assert len(result.mechanisms) > 0
        assert sum(result.budget_split.values()) <= 1.0

    def test_mock_theorist_returns_proposal(self):
        from flowforge.agents.dispatcher import dispatch_role_mock
        from flowforge.agents.schemas import CandidateProposal
        result = dispatch_role_mock("theorist")
        assert isinstance(result, CandidateProposal)
        assert 1 <= len(result.expressions) <= 3

    def test_mock_coder_returns_fit_result(self):
        from flowforge.agents.dispatcher import dispatch_role_mock
        from flowforge.agents.schemas import FitResult
        result = dispatch_role_mock("coder")
        assert isinstance(result, FitResult)
        assert result.apriori_mse >= 0.0

    def test_mock_redteam_returns_attack_spec(self):
        from flowforge.agents.dispatcher import dispatch_role_mock
        from flowforge.agents.schemas import AttackSpec
        result = dispatch_role_mock("redteam")
        assert isinstance(result, AttackSpec)
        assert len(result.flows) >= 1

    def test_unknown_role_raises(self):
        from flowforge.agents.dispatcher import dispatch_role_mock
        with pytest.raises(ValueError, match="Unknown role"):
            dispatch_role_mock("nonexistent")


# ─────────────────────────── harness: research ───────────────────────────


class TestResearchHarness:
    def test_card_extraction_good_paper(self):
        from flowforge.agents.harness.research.harness import run_card_extraction
        from flowforge.agents.harness.research.tasks import CardTask

        task = CardTask(
            doi="10.1017/jfm.2020.123",
            title="A curvature correction model for turbulence closure",
            abstract="We present a rotation-curvature correction to the eddy "
                     "viscosity closure for separated flows with strong pressure "
                     "gradient effects.",
        )
        result = run_card_extraction(task)
        assert result.passed
        assert result.score >= 0.5

    def test_card_extraction_bad_paper(self):
        from flowforge.agents.harness.research.harness import run_card_extraction
        from flowforge.agents.harness.research.tasks import CardTask

        task = CardTask(
            doi="",
            title="Cooking recipes for beginners",
            abstract="Learn how to make pasta and salads.",
        )
        result = run_card_extraction(task)
        assert not result.passed
        assert result.score < 0.5

    def test_validate_card_result(self):
        from flowforge.agents.harness.research.harness import validate_card_result
        from flowforge.agents.harness.research.tasks import CardResult

        good = CardResult(parses_in_sympy=True, mechanism_cited=True, prediction_testable=True)
        assert validate_card_result(good).passed

        bad = CardResult(parses_in_sympy=False, mechanism_cited=False, prediction_testable=False)
        assert not validate_card_result(bad).passed


# ─────────────────────────── harness: physics ───────────────────────────


class TestPhysicsHarness:
    def _make_correction(self, n=10):
        """Create a physically valid correction tensor (symmetric, trace-free)."""
        rng = np.random.default_rng(42)
        raw = 0.01 * rng.standard_normal((n, 3, 3))
        # Make symmetric
        sym = 0.5 * (raw + np.transpose(raw, (0, 2, 1)))
        # Make trace-free
        trace = np.trace(sym, axis1=1, axis2=2)
        for i in range(3):
            sym[:, i, i] -= trace / 3.0
        return sym

    def test_valid_correction_passes(self):
        from flowforge.agents.harness.physics.harness import run_physics_checks
        from flowforge.agents.harness.physics.tasks import PhysicsTask

        task = PhysicsTask(candidate_hash="test_valid", case_id="test_case")
        correction = self._make_correction()
        inv = {"I1": np.ones(10), "I2": np.zeros(10)}
        basis = {"T1": np.eye(3)[None].repeat(10, axis=0)}

        result = run_physics_checks(task, correction, inv, basis)
        # At least symmetry and trace-free should pass
        assert result.score >= 0.5

    def test_asymmetric_correction_fails(self):
        from flowforge.agents.harness.physics.harness import run_physics_checks
        from flowforge.agents.harness.physics.tasks import PhysicsTask

        task = PhysicsTask(candidate_hash="test_asym", case_id="test_case")
        # Deliberately asymmetric
        correction = np.random.default_rng(42).standard_normal((5, 3, 3))
        inv = {"I1": np.ones(5)}
        basis = {"T1": np.eye(3)[None].repeat(5, axis=0)}

        result = run_physics_checks(task, correction, inv, basis)
        assert "symmetry: FAIL" in result.details


# ─────────────────────────── harness: symbolic ───────────────────────────


class TestSymbolicHarness:
    def _make_fields(self, n=8):
        from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis
        rng = np.random.default_rng(42)
        grad = 0.1 * rng.standard_normal((n, 3, 3))
        omega = np.full(n, 2.0)
        s, w = normalized_tensors(grad, omega)
        inv = invariants(s, w)
        basis = tensor_basis(s, w)
        target = 0.5 * basis["T1"]
        return inv, basis, target

    def test_valid_expression(self):
        from flowforge.agents.harness.symbolic.harness import run_symbolic_check
        from flowforge.agents.harness.symbolic.tasks import SymbolicTask

        inv, basis, target = self._make_fields()
        task = SymbolicTask(expression="I1", case_ids=("test",))
        result = run_symbolic_check(task, inv, basis, target)
        assert result.score >= 0.5
        assert "parse: PASS" in result.details

    def test_invalid_expression(self):
        from flowforge.agents.harness.symbolic.harness import run_symbolic_check
        from flowforge.agents.harness.symbolic.tasks import SymbolicTask

        inv, basis, target = self._make_fields()
        task = SymbolicTask(expression="!!!invalid!!!", case_ids=("test",))
        result = run_symbolic_check(task, inv, basis, target)
        assert not result.passed
        assert "parse: FAIL" in result.details


# ─────────────────────────── harness: solver ───────────────────────────


class TestSolverHarness:
    def test_apriori_rung(self):
        from flowforge.agents.harness.solver.harness import run_solver_rung
        from flowforge.agents.harness.solver.tasks import SolverTask
        from flowforge.physics.tensors import invariants, normalized_tensors, tensor_basis

        rng = np.random.default_rng(42)
        grad = 0.1 * rng.standard_normal((8, 3, 3))
        omega = np.full(8, 2.0)
        s, w = normalized_tensors(grad, omega)
        inv = invariants(s, w)
        basis = tensor_basis(s, w)
        target = 0.5 * basis["T1"]

        task = SolverTask(candidate_hash="I1", case_id="test", rung=1, time_cap_seconds=10)
        result = run_solver_rung(task, inv, basis, target)
        # A priori should at least not crash
        assert "a_priori_mse" in result.details or "ERROR" in result.details


# ─────────────────────────── round loop ───────────────────────────


class TestRoundLoop:
    def test_mock_round_still_works(self, tmp_path):
        """Verify that the upgraded round loop still passes mock mode."""
        from flowforge.orchestrator.round import run_round

        result = run_round(1, mock=True, session_dir=str(tmp_path))
        assert result["status"] in ("ok", "all_rejected")
        assert result["mock"] is True
        assert "champion" in result
        assert result["event_count"] > 0

"""Role dispatcher — connects prompt loader + ModelRuntime (S5.3).

Dispatches a role call: loads the prompt YAML, builds the full prompt
with injected context, calls ModelRuntime.complete_structured() with
the matching Pydantic schema, logs events, and returns the validated
output.

This is the single entry point for all agent interactions.  The
orchestrator round loop calls ``dispatch_role()`` and never touches
ModelRuntime or prompt files directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from flowforge.agents.prompt_loader import build_prompt, model_for_role, prompt_hash
from flowforge.agents.runtime.client import ModelRuntime, ModelValidationError
from flowforge.agents.schemas import ROLE_SCHEMAS

logger = logging.getLogger(__name__)


class RoleDispatchError(RuntimeError):
    """A role dispatch failed after retries and repair attempts."""


def dispatch_role(
    role: str,
    runtime: ModelRuntime,
    context: dict[str, Any] | None = None,
    *,
    max_tokens: int = 8192,
) -> BaseModel:
    """Dispatch a single role call and return the validated Pydantic output.

    Parameters
    ----------
    role : str
        One of the 7 agent roles (board, theorist, coder, analyst,
        skeptic, redteam, composer).
    runtime : ModelRuntime
        The shared model runtime with budget tracking.
    context : dict, optional
        Role-specific context to inject into the prompt.
    max_tokens : int
        Max tokens for the completion (reasoning-heavy models need room;
        default leaves space for chain-of-thought plus the answer).

    Returns
    -------
    BaseModel
        The validated Pydantic schema instance for this role.

    Raises
    ------
    RoleDispatchError
        If validation fails after ModelRuntime's repair retry.
    """
    if role not in ROLE_SCHEMAS:
        raise ValueError(f"Unknown role {role!r}; known: {sorted(ROLE_SCHEMAS)}")

    schema = ROLE_SCHEMAS[role]
    model = model_for_role(role)
    full_prompt = build_prompt(role, context)
    p_hash = prompt_hash(full_prompt)

    logger.info("Dispatching role=%s model=%s schema=%s prompt_hash=%s",
                role, model, schema.__name__, p_hash[:12])

    # Sampling settings live in configs/budgets.yaml (roles.<role>):
    # `temperature` and `reasoning` (sent as reasoning_effort). A role
    # without an entry keeps the API defaults.
    from flowforge.config import load_budgets

    role_cfg = load_budgets()["roles"].get(role, {})

    try:
        result = runtime.complete_structured(
            model=model,
            prompt=full_prompt,
            schema=schema,
            max_tokens=max_tokens,
            temperature=role_cfg.get("temperature"),
            reasoning_effort=role_cfg.get("reasoning"),
        )
    except ModelValidationError as exc:
        logger.error("Role %s failed validation: %s", role, exc)
        raise RoleDispatchError(
            f"Role {role!r} failed schema validation: {exc}"
        ) from exc

    logger.info("Role %s returned successfully: %s", role, type(result).__name__)
    return result


def dispatch_role_mock(
    role: str,
    context: dict[str, Any] | None = None,
) -> BaseModel:
    """Return a minimal valid mock output for a role, for testing.

    This never calls the LLM.  Used by the round loop in mock mode
    to exercise the schema validation and downstream pipeline without
    spending API credits.
    """
    if role not in ROLE_SCHEMAS:
        raise ValueError(f"Unknown role {role!r}; known: {sorted(ROLE_SCHEMAS)}")

    schema = ROLE_SCHEMAS[role]
    mock_data = _MOCK_DATA.get(role)
    if mock_data is None:
        raise ValueError(f"No mock data defined for role {role!r}")

    return schema.model_validate(mock_data)


# Minimal valid payloads for each role, for mock/test mode.
_MOCK_DATA: dict[str, dict[str, Any]] = {
    "board": {
        "risk_audit": "Mock round: no real API calls, no budget risk.",
        "mechanisms": ["curvature_correction", "pressure_gradient_sensitization"],
        "budget_split": {"theorist": 0.4, "coder": 0.2, "analyst": 0.2, "redteam": 0.2},
    },
    "theorist": {
        "risk_audit": "Mock proposals: synthetic expressions only.",
        "expressions": ["I1", "tanh(I1)"],
        "mechanisms": ["strain_rate_sensitivity"],
    },
    "coder": {
        "risk_audit": "Mock fit: constants are synthetic.",
        "constants": [0.5, -0.3],
        "apriori_mse": 0.012,
    },
    "analyst": {
        "risk_audit": "Mock analysis: no real error maps.",
        "failure_regions": ["separation_bubble", "reattachment_zone"],
        "next_hypothesis": "Increase curvature correction near separation point.",
    },
    "skeptic": {
        "risk_audit": "Mock skeptic: no real objections.",
        "objections": ["Curvature term may overfit to hill geometry."],
        "requested_tests": ["Test on flat plate to verify baseline preservation."],
    },
    "redteam": {
        "risk_audit": "Mock redteam: no solver runs.",
        "flows": [{"kind": "periodic_hill", "alpha": 1.5, "reynolds": 10595}],
    },
    "composer": {
        "risk_audit": "Mock composition: no gate fitting.",
        "modules": ["I1", "tanh(I1)"],
        "gates": [{"feature": "I2", "threshold": 0.5}],
    },
}

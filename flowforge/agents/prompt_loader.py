"""Load versioned role prompts from prompts/*.yaml (S5.1).

Each YAML file defines: role, version, model, schema, prompt.
The loader injects context (findings, scores, candidates, library
cards, error maps) into the base prompt to build the full prompt
sent to ModelRuntime.  Prompt hash is computed from the full text
and logged with every event for reproducibility.

The prompt files are kept simple and declarative; all context
formatting lives here so prompt templates stay version-controlled
and diffable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# Cache loaded raw configs keyed by role name.
_CACHE: dict[str, dict[str, Any]] = {}


def _load_raw(role: str) -> dict[str, Any]:
    """Load and cache a single prompt YAML file."""
    if role in _CACHE:
        return _CACHE[role]
    path = _PROMPTS_DIR / f"{role}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file for role {role!r} at {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), f"prompt file for {role!r} must be a YAML mapping"
    assert data.get("role") == role, f"role mismatch in {path}: expected {role!r}"
    _CACHE[role] = data
    return data


def prompt_config(role: str) -> dict[str, Any]:
    """Return the raw prompt config dict for a role."""
    return dict(_load_raw(role))


def model_for_role(role: str) -> str:
    """Return the model name specified in the prompt YAML."""
    return str(_load_raw(role)["model"])


def schema_name_for_role(role: str) -> str:
    """Return the schema class name referenced in the prompt YAML."""
    return str(_load_raw(role)["schema"])


def build_prompt(role: str, context: dict[str, Any] | None = None) -> str:
    """Build the full prompt text for a role, with context injected.

    Context keys depend on the role:
      board:    findings, scores, budget_left
      theorist: mechanism, closure_cards, group_history
      coder:    candidate, training_cases
      analyst:  error_maps, velocity_profiles, sam_regions
      skeptic:  candidate, evidence
      redteam:  champions, attack_suite
      composer: modules, regime_features
    """
    raw = _load_raw(role)
    base = str(raw.get("prompt", ""))
    schema = raw.get("schema", "")

    sections: list[str] = []
    sections.append(f"# Role: {role} (schema: {schema})")
    sections.append("")
    sections.append(base.strip())

    if context:
        sections.append("")
        sections.append("## Context")
        for key, value in context.items():
            sections.append(f"\n### {key}")
            if isinstance(value, (list, dict)):
                import json
                sections.append(f"```json\n{json.dumps(value, indent=2, default=str)}\n```")
            else:
                sections.append(str(value))

    return "\n".join(sections)


def prompt_hash(text: str) -> str:
    """SHA-256 of the full prompt text, for event-log reproducibility."""
    assert isinstance(text, str) and text, "prompt must be a non-empty string"
    return hashlib.sha256(text.encode()).hexdigest()


def list_roles() -> list[str]:
    """Return all role names that have prompt YAML files."""
    return sorted(
        p.stem for p in _PROMPTS_DIR.glob("*.yaml")
        if p.stem != ".gitkeep"
    )

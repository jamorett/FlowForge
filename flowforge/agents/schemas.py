"""Pydantic v2 role schemas (S5.2). One repair retry, then drop.

Every role output must carry a non-empty ``risk_audit``. Extra keys are
forbidden so a model cannot smuggle unvalidated fields past the schema.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _RoleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_audit: str = Field(min_length=1)

    @field_validator("risk_audit", mode="before")
    @classmethod
    def _risk_audit_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("risk_audit must be non-empty")
        return v


class CandidateProposal(_RoleOutput):
    expressions: list[str] = Field(min_length=1, max_length=3)
    mechanisms: list[str] = Field(min_length=1)


class RoundPlan(_RoleOutput):
    mechanisms: list[str] = Field(min_length=1)
    budget_split: dict[str, float]

    @field_validator("budget_split")
    @classmethod
    def _budget_split_valid(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("budget_split must not be empty")
        for role, frac in v.items():
            if not 0.0 <= frac <= 1.0:
                raise ValueError(f"budget_split[{role!r}]={frac} outside [0, 1]")
        total = sum(v.values())
        if total > 1.0 + 1e-9:
            raise ValueError(f"budget_split sums to {total:.4f} > 1.0")
        return v


class FitResult(_RoleOutput):
    constants: list[float]
    apriori_mse: float = Field(ge=0.0)


class AnalysisReport(_RoleOutput):
    failure_regions: list[str]
    next_hypothesis: str = Field(min_length=1)

    @field_validator("next_hypothesis", mode="before")
    @classmethod
    def _hypothesis_nonblank(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            raise ValueError("next_hypothesis must be non-empty")
        return v


class SkepticCritique(_RoleOutput):
    objections: list[str]
    requested_tests: list[str]


class AttackSpec(_RoleOutput):
    flows: list[dict] = Field(min_length=1)


class CompositionPlan(_RoleOutput):
    modules: list[str] = Field(min_length=1)
    gates: list[dict]


ROLE_SCHEMAS: dict[str, type[BaseModel]] = {
    "board": RoundPlan,
    "theorist": CandidateProposal,
    "coder": FitResult,
    "analyst": AnalysisReport,
    "skeptic": SkepticCritique,
    "redteam": AttackSpec,
    "composer": CompositionPlan,
}

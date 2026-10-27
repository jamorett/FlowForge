"""Shared harness contracts. Stdlib only until pydantic lands.

Every harness task must carry: typed input/output, a success threshold
fixed before the run, a hard budget, locked-data isolation, and one
events.jsonl trace (prompt hash, response, tool calls, scores, cost).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    max_tokens: int
    max_solver_seconds: float
    max_dollars: float


@dataclass(frozen=True)
class HarnessResult:
    passed: bool
    score: float
    details: str
    cost_tokens: int = 0
    cost_dollars: float = 0.0

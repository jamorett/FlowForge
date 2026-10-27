"""Solver harness tasks. Scaffold only."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SolverTask:
    """Run one candidate on one case through the evaluation ladder."""

    candidate_hash: str
    case_id: str
    rung: int  # 1 = a priori, 2 = short run, 3 = full RANS
    time_cap_seconds: float

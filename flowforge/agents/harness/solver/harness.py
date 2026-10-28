"""Solver harness — evaluation ladder through OpenFOAM (S5.1).

Runs a candidate through the evaluation ladder:
- Rung 1: a priori (precomputed features, no solver, seconds/case).
- Rung 2: short run (coarse mesh, time-capped RANS, catch divergence).
- Rung 3: full RANS (converged solves on all training cases + physics checks).

Each rung reports: exit code, convergence, field hashes, time and cost.
Without Docker/OpenFOAM, this harness runs in a priori-only mode and
logs the limitation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from flowforge.agents.harness.contracts import Budget, HarnessResult
from flowforge.agents.harness.solver.tasks import SolverTask

logger = logging.getLogger(__name__)


def _content_hash(data: bytes) -> str:
    """SHA-256 content hash for caching."""
    return hashlib.sha256(data).hexdigest()


def _candidate_hash(expression: str) -> str:
    """Content hash for a candidate expression."""
    return _content_hash(expression.encode())


def run_solver_rung(
    task: SolverTask,
    inv: dict[str, np.ndarray] | None = None,
    basis: dict[str, np.ndarray] | None = None,
    target: np.ndarray | None = None,
    budget: Budget | None = None,
    cache_dir: Path | None = None,
) -> HarnessResult:
    """Run a single rung of the evaluation ladder.

    Parameters
    ----------
    task : SolverTask
        Candidate hash, case ID, rung number, and time cap.
    inv, basis, target : arrays, optional
        Precomputed fields for a priori evaluation (rung 1).
    budget : Budget, optional
        Budget constraints.
    cache_dir : Path, optional
        Directory for content-addressed result caching.

    Returns
    -------
    HarnessResult
        Whether the candidate passed this rung.
    """
    budget = budget or Budget(max_tokens=0, max_solver_seconds=task.time_cap_seconds,
                               max_dollars=0)
    start_time = time.monotonic()
    details: list[str] = []

    if task.rung == 1:
        # A priori evaluation: no solver needed
        return _run_apriori(task, inv, basis, target, details)

    elif task.rung == 2:
        # Short run: requires OpenFOAM Docker
        return _run_short(task, budget, details)

    elif task.rung == 3:
        # Full RANS: requires OpenFOAM Docker
        return _run_full(task, budget, details)

    else:
        return HarnessResult(
            passed=False,
            score=0.0,
            details=f"Unknown rung {task.rung}",
        )


def _run_apriori(
    task: SolverTask,
    inv: dict[str, np.ndarray] | None,
    basis: dict[str, np.ndarray] | None,
    target: np.ndarray | None,
    details: list[str],
) -> HarnessResult:
    """Rung 1: a priori evaluation on precomputed features."""
    if inv is None or basis is None or target is None:
        return HarnessResult(
            passed=False,
            score=0.0,
            details="a priori: FAIL (no precomputed fields available)",
        )

    try:
        from flowforge.dsl.evaluate import candidate_anisotropy
        from flowforge.ladder.ladder import apriori_mse

        # Resolve the expression from the hash (in practice, the hash
        # would be looked up from a registry; here we pass through).
        # For now, this only works if candidate_hash IS the expression.
        prediction = candidate_anisotropy(task.candidate_hash, inv, basis)
        mse = apriori_mse(prediction, target)

        passed = np.isfinite(mse)
        details.append(f"a_priori_mse={mse:.6f}")
        details.append(f"rung=1, case={task.case_id}")

        return HarnessResult(
            passed=passed,
            score=1.0 - min(mse, 1.0),  # Normalize to [0, 1]
            details="; ".join(details),
        )
    except Exception as exc:
        return HarnessResult(
            passed=False,
            score=0.0,
            details=f"a priori: ERROR ({exc})",
        )


def _run_short(
    task: SolverTask,
    budget: Budget,
    details: list[str],
) -> HarnessResult:
    """Rung 2: short, coarse-mesh solver run.

    Requires Docker + OpenFOAM. If not available, logs and fails gracefully.
    """
    try:
        # Check if Docker is available
        import subprocess
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            details.append("rung2: Docker not available")
            return HarnessResult(
                passed=False, score=0.0,
                details="; ".join(details) + "; Docker not available for short run",
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        details.append("rung2: Docker not found")
        return HarnessResult(
            passed=False, score=0.0,
            details="; ".join(details) + "; Docker not found on system",
        )

    # If Docker is available, run coarse solver
    details.append(f"rung=2, case={task.case_id}, time_cap={task.time_cap_seconds}s")
    details.append("rung2: OpenFOAM solver run (placeholder - requires case setup)")

    # Placeholder: in production, this would:
    # 1. Generate C++ correction code from candidate
    # 2. Compile in Docker container
    # 3. Run coarse mesh with time cap
    # 4. Check convergence and field validity

    return HarnessResult(
        passed=False, score=0.0,
        details="; ".join(details) + "; solver run not yet wired to Docker",
    )


def _run_full(
    task: SolverTask,
    budget: Budget,
    details: list[str],
) -> HarnessResult:
    """Rung 3: full converged RANS solve.

    Requires Docker + OpenFOAM. If not available, logs and fails gracefully.
    """
    details.append(f"rung=3, case={task.case_id}, time_cap={task.time_cap_seconds}s")
    details.append("rung3: Full RANS solve (requires Docker + compiled correction)")

    # Same Docker dependency as rung 2
    return HarnessResult(
        passed=False, score=0.0,
        details="; ".join(details) + "; full solver run requires Docker setup",
    )

"""OpenFOAM solver runner (S1).

Runs simpleFoam in Docker with a hard timeout, content-addressed caching,
and explicit convergence flags. Fields are read via foamlib when available;
parsing never uses ad-hoc string splitting.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RESIDUAL_TOL = 1e-4
SHORT_TIMEOUT_SECONDS = 60.0
FULL_TIMEOUT_SECONDS = 300.0


def timeout_for_mode(mode: str) -> float:
    """Hard wall-clock caps from the plan: 60s short, 300s full."""
    if mode == "short":
        return SHORT_TIMEOUT_SECONDS
    if mode == "full":
        return FULL_TIMEOUT_SECONDS
    raise ValueError(f"unknown run mode: {mode!r} (expected 'short' or 'full')")


def parse_residuals(log_text: str) -> dict[str, float]:
    """Last residual per field from simpleFoam log. Empty if none found."""
    import re

    found: dict[str, float] = {}
    for field_name, value in re.findall(
        r"Solving for (\w+), Initial residual = [\d.eE+-]+, Final residual = ([\d.eE+-]+)",
        log_text,
    ):
        try:
            found[field_name] = float(value)
        except ValueError:
            continue
    return found


def count_iterations(log_text: str) -> int:
    """Number of solver steps. Anchored: ExecutionTime/ClockTime lines
    also contain 'Time = ' and must not be counted."""
    import re

    return len(re.findall(r"^Time = ", log_text, re.MULTILINE))


def residuals_converged(residuals: dict[str, float], tol: float = RESIDUAL_TOL) -> bool:
    """Hard gate (S1): pressure and velocity residuals must be < 1e-4.

    simpleFoam logs velocity as U or as Ux/Uy/Uz; both spellings count.
    Missing p or U means not converged, never a pass.
    """
    assert tol == RESIDUAL_TOL, "residual tolerance is frozen at 1e-4"
    if not residuals or "p" not in residuals:
        return False
    velocity = [v for name, v in residuals.items() if name.startswith("U")]
    if not velocity:
        return False
    return residuals["p"] < tol and all(v < tol for v in velocity)


@dataclass
class SolverRunResult:
    case_path: Path
    converged: bool
    iterations: int
    wall_time_seconds: float
    fields: dict[str, np.ndarray] = field(default_factory=dict)
    run_hash: str = ""
    error_message: str | None = None
    # Solved stage dir (post-fork): latest-time fields, mesh and logs
    # live here. None for cache hits whose stage was cleaned by hand.
    stage_path: Path | None = None


def compute_run_hash(case_name: str, mesh_hash: str, solver_settings: dict) -> str:
    payload = case_name + mesh_hash + json.dumps(solver_settings, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# Built from docker/openfoam.Dockerfile. The stock OpenCFD image lacks
# libcorrectedKOmegaSST, so every corrected run would fail on it.
DEFAULT_IMAGE = "flowforge-openfoam:local"


def default_image() -> str:
    """Image for solver runs. Override with FLOWFORGE_OPENFOAM_IMAGE."""
    import os

    return os.environ.get("FLOWFORGE_OPENFOAM_IMAGE", DEFAULT_IMAGE)


class OpenFOAMSolverRunner:
    def __init__(self, cache_dir: Path = Path("runs/cache"), image: str | None = None):
        self.cache_dir = cache_dir
        self.image = image or default_image()

    def run(
        self,
        case_path: Path,
        case_name: str,
        mesh_hash: str,
        solver_settings: dict,
        timeout_seconds: float = 300.0,
        mesh: bool = True,
    ) -> SolverRunResult:
        assert timeout_seconds > 0, "solver timeout must be positive"
        assert timeout_seconds <= 300.0, "full runs are capped at 300s per plan"
        # mesh=False skips the in-container blockMesh for pre-meshed cases
        # (e.g. displaced hill meshes, which blockMesh would flatten).
        run_hash = compute_run_hash(case_name, mesh_hash, solver_settings)
        cache_file = self.cache_dir / f"{run_hash}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            # A cache hit replays the verdict AND the fields: the solved
            # stage dir is recorded in the cache entry, so callers never
            # see a converged-but-fieldless result. A missing stage
            # (cleaned by hand) yields {} rather than a crash.
            fields: dict[str, np.ndarray] = {}
            stage = data.get("stage")
            stage_path = Path(stage) if stage and Path(stage).exists() else None
            if data.get("converged") and stage_path is not None:
                try:
                    from flowforge.solver.field_io import read_fields

                    fields = read_fields(stage_path)
                except Exception:
                    fields = {}
            return SolverRunResult(
                case_path=case_path, converged=data["converged"],
                iterations=data["iterations"], wall_time_seconds=0.0,
                fields=fields, run_hash=run_hash,
                error_message=data.get("error_message"),
                stage_path=stage_path,
            )
        # Isolated staging: a unique directory per run. Recycled paths
        # risk stale bind-mount dentries on Windows (solver then reads
        # ghost state and reports a plausible-but-wrong trajectory), so
        # the run hash keys the result cache, never the stage path.
        import shutil
        import uuid

        stage_dir = self.cache_dir / "cases" / f"{run_hash}-{uuid.uuid4().hex[:8]}"
        shutil.copytree(case_path.resolve(), stage_dir)
        start = time.time()
        solve_cmd = ("blockMesh && simpleFoam" if mesh
                     else "test -d constant/polyMesh && simpleFoam")
        try:
            proc = subprocess.run(
                ["docker", "run", "--rm", "-v", f"{stage_dir.resolve()}:/case",
                 self.image, "bash", "-lc", f"cd /case && {solve_cmd}"],
                capture_output=True, text=True, timeout=timeout_seconds,
            )
            elapsed = time.time() - start
            residuals = parse_residuals(proc.stdout)
            converged = (
                proc.returncode == 0 and "End" in proc.stdout
                and residuals_converged(residuals)
            )
            fields: dict[str, np.ndarray] = {}
            if converged:
                from flowforge.solver.field_io import read_fields

                fields = read_fields(stage_dir)
            result = SolverRunResult(
                case_path=case_path, converged=converged,
                iterations=count_iterations(proc.stdout),
                wall_time_seconds=elapsed, fields=fields, run_hash=run_hash,
                stage_path=stage_dir.resolve(),
                error_message=None if converged else (
                    "STDERR: " + (proc.stderr or "")[-1500:]
                    + " STDOUT: " + (proc.stdout or "")[-1500:]
                ),
            )
        except subprocess.TimeoutExpired:
            result = SolverRunResult(
                case_path=case_path, converged=False, iterations=0,
                wall_time_seconds=timeout_seconds, run_hash=run_hash,
                error_message=f"Timed out after {timeout_seconds}s",
            )
        except FileNotFoundError as exc:
            result = SolverRunResult(
                case_path=case_path, converged=False, iterations=0,
                wall_time_seconds=time.time() - start, run_hash=run_hash,
                error_message=f"docker not available: {exc}",
            )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "converged": result.converged, "iterations": result.iterations,
            "error_message": result.error_message,
            "stage": str(stage_dir.resolve()),
        }), encoding="utf-8")
        if not result.converged:
            # proc is unbound when docker itself failed or timed out.
            completed = locals().get("proc")
            (self.cache_dir / f"{run_hash}.fail.log").write_text(
                (completed.stdout if completed else "") or "",
                encoding="utf-8", errors="replace")
        return result

    async def run_async(
        self,
        case_path: Path,
        case_name: str,
        mesh_hash: str,
        solver_settings: dict,
        timeout_seconds: float = FULL_TIMEOUT_SECONDS,
        mode: str | None = None,
        mesh: bool = True,
    ) -> SolverRunResult:
        """Async-compatible entry point; the blocking Docker call runs in
        a worker thread so the event loop is never stalled. ``mode`` is
        'short' (60s) or 'full' (300s) and overrides timeout_seconds."""
        if mode is not None:
            timeout_seconds = timeout_for_mode(mode)
        assert 0 < timeout_seconds <= FULL_TIMEOUT_SECONDS, (
            "solver timeout must be in (0, 300] seconds"
        )
        return await asyncio.to_thread(
            self.run, case_path, case_name, mesh_hash, solver_settings,
            timeout_seconds, mesh,
        )

"""Run an experiment config. Baseline: SST on periodic hills (S1)."""

from __future__ import annotations

import argparse
from pathlib import Path

from flowforge.solver.runner import OpenFOAMSolverRunner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiments/baseline.yaml")
    args = parser.parse_args()
    print(f"Config: {args.config}")
    runner = OpenFOAMSolverRunner()
    result = runner.run(
        case_path=Path("openfoam/templates/periodicHill"),
        case_name="periodic_hill_re5600",
        mesh_hash="template-v1",
        solver_settings={"model": "kOmegaSST"},
    )
    print(f"converged={result.converged} hash={result.run_hash} "
          f"time={result.wall_time_seconds:.1f}s err={result.error_message}")
    if not result.converged:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

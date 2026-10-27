"""S1/S2 temporal probe (Phase 3 of the atomic loop).

Pre-flight audit (hallucination risks):
- OpenFOAM patch names / cyclic pairing in blockMeshDict may be wrong.
- Docker / simpleFoam may be absent; this probe must report that, never fake it.
- Residual parsing must require p and U below 1e-4 (plan S1 guardrail).

Run: uv run python scratch/probe_solver.py
Prints exact exit codes. Exit 0 only if docker simpleFoam -help succeeds
AND the template case files exist. Otherwise exit 2 (BLOCKED, not a pass).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "openfoam" / "templates" / "periodicHill"
REQUIRED = [
    "0/U", "0/p", "0/k", "0/omega", "0/aDelta", "0/PkDelta",
    "constant/turbulenceProperties", "constant/transportProperties",
    "system/blockMeshDict", "system/controlDict",
    "system/fvSchemes", "system/fvSolution",
]


def main() -> int:
    missing = [p for p in REQUIRED if not (CASE / p).exists()]
    print(f"case={CASE} missing={missing}")
    assert not missing, f"template case incomplete: {missing}"

    sys.path.insert(0, str(ROOT))
    from flowforge.solver.runner import residuals_converged

    sample = "Solving for p, Initial residual = 1, Final residual = 1e-5\n" \
             "Solving for Ux, Initial residual = 1, Final residual = 1e-5\n"
    from flowforge.solver.runner import parse_residuals

    res = parse_residuals(sample)
    print(f"parsed_residuals={res} converged={residuals_converged(res)}")
    assert residuals_converged(res), "p/U residual gate failed on probe log"

    try:
        proc = subprocess.run(
            ["docker", "run", "--rm", "opencfd/openfoam-default:latest",
             "simpleFoam", "-help"],
            capture_output=True, text=True, timeout=120,
        )
        print(f"docker_exit={proc.returncode}")
        print((proc.stdout or proc.stderr)[:500])
        if proc.returncode != 0:
            print("BLOCKED: docker simpleFoam -help failed; solver unverified")
            return 2
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"BLOCKED: docker unavailable: {exc!r}; solver unverified")
        return 2
    print("PROBE_OK: docker simpleFoam -help exit 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

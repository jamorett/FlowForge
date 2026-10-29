"""Oracle gate (S2): DNS-derived corrections injected through the real
fixed-field path must move the solution toward DNS.

Sources (never locked data): ``data/processed/periodic_hill_re10595``
(Re_h ~ 10595 matches the template's Ub=1/h=1/nu=9.44e-5).

Geometry: the flat template mesh cannot see separation, so its error
vs hill DNS is geometry-dominated and no closure can dent it. The gate
therefore runs on the data-derived hill mesh
(:mod:`flowforge.solver.hill_mesh`, spline wall from the DNS grid) with
cell centers read back from the meshed case (never assumed order).

Gate (spec Integration row, ``oracle_ratio`` frozen in
``configs/tolerances.yaml``):

    err(corrected vs DNS) <= oracle_ratio * err(baseline vs DNS)

Errors are scale-free (each field self-normalized), so the dataset's
bulk-velocity convention never enters the verdict.
"""
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from flowforge.solver.field_io import (
    read_cell_centres,
    write_openfoam_correction_fields,
)
from flowforge.solver.hill_mesh import displace_hill_mesh, extract_wall_profile
from flowforge.solver.oracle import (
    load_oracle_fields,
    map_to_mesh,
    normalized_rms_error,
    read_latest_field,
    recalibrate,
)
from flowforge.solver.runner import OpenFOAMSolverRunner, default_image

STAGE_ROOT = Path("runs/cache/test-stages")
TEMPLATE = Path("openfoam/templates/periodicHill")
STORE = Path("data/processed/periodic_hill_re10595")
TOLERANCES = Path("configs/tolerances.yaml")


def _image() -> str:
    import os

    return os.environ.get("FLOWFORGE_OPENFOAM_IMAGE", default_image())


def _docker_ok() -> bool:
    try:
        if subprocess.run(["docker", "info"], capture_output=True,
                          timeout=30).returncode != 0:
            return False
        return subprocess.run(
            ["docker", "image", "inspect", _image()],
            capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False


needs_docker = pytest.mark.skipif(
    not _docker_ok(), reason="no Docker daemon: oracle gate unverifiable here")


def _oracle_ratio() -> float:
    import re

    text = TOLERANCES.read_text(encoding="utf-8")
    match = re.search(r"^oracle_ratio:\s*([0-9.]+)", text, re.MULTILINE)
    assert match, "oracle_ratio missing from frozen tolerances"
    return float(match.group(1))


def _stage_hill(path: Path, model: str) -> Path:
    """Stage a hill-mesh case: dataset wall + correctors for skewness."""
    case = path / "case"
    shutil.copytree(TEMPLATE, case)
    fv = case / "system" / "fvSolution"
    text = fv.read_text(encoding="utf-8")
    fv.write_text(text.replace("nNonOrthogonalCorrectors 0",
                               "nNonOrthogonalCorrectors 4"), encoding="utf-8")
    props = case / "constant" / "turbulenceProperties"
    text = props.read_text(encoding="utf-8")
    assert "RASModel" in text
    props.write_text(
        text.replace("RASModel        kOmegaSST;", f"RASModel        {model};"),
        encoding="utf-8",
    )
    if model != "kOmegaSST":
        ctrl = case / "system" / "controlDict"
        text = ctrl.read_text(encoding="utf-8")
        if "libs (" not in text:
            ctrl.write_text(text + '\nlibs ("libcorrectedKOmegaSST.so");\n',
                            encoding="utf-8")
    return case


def _container(case: Path, script: str) -> None:
    """Run a shell snippet on a staged case in a throwaway container."""
    proc = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{case.resolve()}:/case",
         _image(), "bash", "-lc", script],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"container helper failed: {proc.stderr[-500:]}"


def _mesh_hill(case: Path):
    """Flat blockMesh, Python displacement to the dataset wall, centers.

    Curved blockMesh edges attenuate sharp profiles in v2512, so the
    hill shape is imposed by displacing flat-mesh points instead —
    deterministic and exact. ``-time 0`` pins writeCellCentres output
    (``-latestTime`` falls back to ``constant/`` pre-solve).
    """
    _container(case, "cd /case && blockMesh >/dev/null 2>&1")
    # Exact (unsmoothed) wall: displacement is exact, so any smoothing
    # would only offset our wall from the DNS grid and inflate both
    # errors with a shared floor.
    profile = extract_wall_profile(STORE, smooth=False)
    displace_hill_mesh(case, profile)
    _container(case, "cd /case && postProcess -func writeCellCentres "
                    "-time 0 >/dev/null 2>&1")
    centers = read_cell_centres(case)
    assert len(centers) == 90 * 30 * 1
    wall_min = float(centers[:, 1].min())
    assert wall_min < 0.1, f"hill displacement failed: ymin {wall_min}"
    return centers


def _baseline_state(stage: Path):
    """Solver-native nut + grad(U) from a converged stage (postProcess)."""
    _container(stage, "cd /case && postProcess -func 'grad(U)' -latestTime "
                      ">/dev/null 2>&1")
    nut = read_latest_field(stage, "nut")
    grad_u = read_latest_field(stage, "grad(U)")
    assert nut.shape == grad_u.shape[:1]
    assert grad_u.shape[1:] == (3, 3)
    return nut, grad_u


def _run(case: Path, name: str):
    # Pre-meshed (displaced) hill cases must skip the runner's blockMesh,
    # which would flatten the displaced mesh back to a channel.
    runner = OpenFOAMSolverRunner(image=_image())
    return runner.run(case, f"{name}-{uuid.uuid4().hex[:8]}", "oracle-gate",
                      {"model": "oracle-hill"}, timeout_seconds=300.0,
                      mesh=False)


@needs_docker
def test_oracle_dns_injection_moves_toward_dns() -> None:
    """DNS-derived a_delta/Pk_delta on the hill mesh -> closer to DNS."""
    import numpy as np

    ratio = _oracle_ratio()
    data = load_oracle_fields(STORE)

    work = STAGE_ROOT / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    try:
        base_case = _stage_hill(work / "base", "kOmegaSST")
        centers = _mesh_hill(base_case)
        mapped = map_to_mesh(data, centers)

        base = _run(base_case, "base")
        assert base.converged, base.error_message
        assert base.stage_path is not None
        err_base = normalized_rms_error(base.fields["U"], mapped["u_dns"])

        # Outer loop (spec fallback): each pass references the DNS
        # anisotropy to the CURRENT solve's implied stress and re-solves.
        # The fixed point is DNS; every pass must compound the gain.
        current, current_err = base, err_base
        for it in range(3):
            assert current.stage_path is not None
            nut, grad_u = _baseline_state(current.stage_path)
            a_star, pk_star = recalibrate(
                mapped, nut, grad_u, current.fields["k"])
            corr_case = _stage_hill(work / f"corr{it}", "correctedKOmegaSST")
            corr_centers = _mesh_hill(corr_case)
            assert np.allclose(corr_centers, centers), "hill meshes diverged"
            write_openfoam_correction_fields(corr_case, a_star, pk_star)
            corr = _run(corr_case, f"corr{it}")
            assert corr.converged, corr.error_message
            current_err = normalized_rms_error(
                corr.fields["U"], mapped["u_dns"])
            print(f"\nORACLE it={it} err={current_err:.4f} "
                  f"ratio={current_err / err_base:.3f} (gate<={ratio})")
            current = corr

        assert current_err <= ratio * err_base, (
            f"oracle gate violated: {current_err:.4f} > "
            f"{ratio} * {err_base:.4f}")
    except Exception:
        print(f"\nGATE STAGE PRESERVED FOR DEBUG: {work}")
        raise
    else:
        shutil.rmtree(work, ignore_errors=True)

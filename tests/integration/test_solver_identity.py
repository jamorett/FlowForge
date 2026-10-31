"""Solver-level S2 gates: identity (zero correction == baseline) and injection.

Needs a Docker daemon with an image containing libcorrectedKOmegaSST
(see docker/openfoam.Dockerfile; point FLOWFORGE_OPENFOAM_IMAGE at it).
Skips loudly when Docker is unreachable — the skip is reported, not
presented as a pass.

Staging lives under runs/cache/test-stages (git-ignored), never pytest
tmp: Docker Desktop's Windows bind mount leaves pytest tmp dirs
locked/unlistable, which starves the field reader.
"""
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from flowforge.solver.runner import OpenFOAMSolverRunner, default_image

STAGE_ROOT = Path("runs/cache/test-stages")

TEMPLATE = Path("openfoam/templates/periodicHill")


def _image() -> str:
    import os

    from flowforge.solver.runner import default_image

    return os.environ.get("FLOWFORGE_OPENFOAM_IMAGE", default_image())


def _docker_state() -> str:
    """'ok', 'no-cli' (no Docker here, e.g. CI), 'daemon-down' or 'no-image'."""
    try:
        if subprocess.run(["docker", "info"], capture_output=True,
                          timeout=30).returncode != 0:
            return "daemon-down"
        if subprocess.run(["docker", "image", "inspect", _image()],
                          capture_output=True, timeout=30).returncode != 0:
            return "no-image"
        return "ok"
    except FileNotFoundError:
        return "no-cli"
    except subprocess.TimeoutExpired:
        return "daemon-down"


_DOCKER = _docker_state()
needs_docker = pytest.mark.skipif(
    _DOCKER in ("no-cli", "no-image"),
    reason=f"solver gate unverifiable here ({_DOCKER}: no Docker CLI or image not built)")


@pytest.fixture(autouse=True)
def _docker_daemon_must_run() -> None:
    # Docker installed but stopped is a local setup error, not a reason to
    # skip: a silent skip exits 0 and reads like a pass.
    if _DOCKER == "daemon-down":
        pytest.fail("Docker CLI found but the daemon is not running: start Docker Desktop")


def _stage(tmp_path: Path, model: str) -> Path:
    case = tmp_path / "case"
    shutil.copytree(TEMPLATE, case)
    props = case / "constant" / "turbulenceProperties"
    text = props.read_text(encoding="utf-8")
    assert "RASModel" in text
    text = text.replace("RASModel        kOmegaSST;",
                        f"RASModel        {model};")
    props.write_text(text, encoding="utf-8")
    if model != "kOmegaSST":
        ctrl = case / "system" / "controlDict"
        text = ctrl.read_text(encoding="utf-8")
        if "libs (" not in text:
            text += '\nlibs ("libcorrectedKOmegaSST.so");\n'
            ctrl.write_text(text, encoding="utf-8")
    return case


def _run(case: Path, name: str):
    # Unique case_name per call: the runner's content-addressed cache would
    # otherwise replay a stale converged verdict and skip the real solve,
    # leaving the fresh stage dir without time directories to read.
    runner = OpenFOAMSolverRunner(image=_image())
    return runner.run(case, f"{name}-{uuid.uuid4().hex[:8]}", "identity-gate",
                      {"model": "corrected-gate"}, timeout_seconds=300.0)


def _velocity(result, label: str):
    # Fields travel on the run result: the runner solves in its own
    # isolated stage dir (runs/cache/cases/...) and reads the fields
    # there. The input case dir is never solved in place, so reading
    # fields from it would hit a pristine, unmeshed template.
    assert "U" in result.fields, f"U not read by runner for {label}"
    return result.fields["U"]


def _workdir() -> Path:
    root = STAGE_ROOT / uuid.uuid4().hex[:8]
    root.mkdir(parents=True, exist_ok=True)
    return root


@needs_docker
def test_zero_correction_is_identity() -> None:
    """Zero aDelta/PkDelta through correctedKOmegaSST == baseline SST."""
    import numpy as np

    work = _workdir()
    try:
        base = _run(_stage(work / "base", "kOmegaSST"), "base")
        assert base.converged, base.error_message
        corr = _run(_stage(work / "corr", "correctedKOmegaSST"), "corr")
        assert corr.converged, corr.error_message
        diff = float(np.abs(_velocity(corr, "corr") - _velocity(base, "base")).max())
        assert diff < 1e-6, f"identity gate violated: max U diff {diff:.3e}"
    except Exception:
        print(f"\nGATE STAGE PRESERVED FOR DEBUG: {work}")
        raise
    else:
        shutil.rmtree(work, ignore_errors=True)


@needs_docker
def test_nonzero_correction_injects() -> None:
    """A nonzero correction must change the solution (hook is live)."""
    import numpy as np

    work = _workdir()
    try:
        base = _run(_stage(work / "base", "kOmegaSST"), "base")
        assert base.converged, base.error_message
        case = _stage(work / "corr", "correctedKOmegaSST")
        adelta = case / "0" / "aDelta"
        text = adelta.read_text(encoding="utf-8")
        # Valid 6-component symmTensor (xx xy xz yy yz zz), trace-free,
        # magnitude ~0.02: large enough to move the solution, small
        # enough to stay converged.
        text = text.replace("uniform (0 0 0 0 0 0)",
                            "uniform (0.01 0 0 0.01 0 -0.02)")
        adelta.write_text(text, encoding="utf-8")
        corr = _run(case, "corr")
        assert corr.converged, corr.error_message
        diff = float(np.abs(_velocity(corr, "corr") - _velocity(base, "base")).max())
        assert diff > 1e-9, "correction had no effect: injection path dead"
    except Exception:
        print(f"\nGATE STAGE PRESERVED FOR DEBUG: {work}")
        raise
    else:
        shutil.rmtree(work, ignore_errors=True)

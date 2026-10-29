"""Solver image selection: single default, env override (S1 compat)."""


def test_default_image_and_env_override(monkeypatch) -> None:
    from flowforge.solver.runner import DEFAULT_IMAGE, OpenFOAMSolverRunner, default_image

    monkeypatch.delenv("FLOWFORGE_OPENFOAM_IMAGE", raising=False)
    assert default_image() == DEFAULT_IMAGE
    assert OpenFOAMSolverRunner().image == DEFAULT_IMAGE

    monkeypatch.setenv("FLOWFORGE_OPENFOAM_IMAGE", "flowforge-openfoam:local")
    assert default_image() == "flowforge-openfoam:local"
    assert OpenFOAMSolverRunner().image == "flowforge-openfoam:local"
    assert OpenFOAMSolverRunner(image="custom:1").image == "custom:1"

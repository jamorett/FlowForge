"""Unit tests for hill mesh + field helpers (synthetic files, no Docker)."""
import numpy as np

from flowforge.solver.hill_mesh import displace_hill_mesh
from flowforge.solver.oracle import read_latest_field


def _write_points(case, nx=4, ny=4, h=3.0):
    from pathlib import Path

    d = Path(case) / "constant" / "polyMesh"
    d.mkdir(parents=True, exist_ok=True)
    xs = np.linspace(0, 9, nx + 1)
    ys = np.linspace(0, h, ny + 1)
    pts = [(x, y, 0.0) for y in ys for x in xs]
    body = "\n".join("(%.6f %.6f %.6f)" % p for p in pts)
    (d / "points").write_text(
        "FoamFile\n{\n    version 2.0;\n}\n%d\n(\n%s\n)\n"
        % (len(pts), body),
        encoding="utf-8",
    )
    return np.array(pts)


def _read_pts(case) -> np.ndarray:
    import re
    from pathlib import Path

    text = (Path(case) / "constant" / "polyMesh" / "points").read_text()
    body = text.split("(", 1)[1]
    num_re = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
    return np.array([float(v) for v in num_re.findall(body)]).reshape(-1, 3)


def test_displace_pins_wall_and_top(tmp_path) -> None:
    prof = np.array([[0.0, 0.5], [4.5, 0.0], [9.0, 0.5]])
    _write_points(tmp_path, nx=4, ny=4, h=3.0)
    displace_hill_mesh(tmp_path, prof, height=3.0)
    pts = _read_pts(tmp_path)
    assert len(pts) == 25
    # Bottom row follows the wall, top row untouched.
    assert pts[:5, 1].tolist() == [0.5, 0.25, 0.0, 0.25, 0.5]
    assert (pts[20:, 1] == 3.0).all()
    # Cyclic columns match.
    assert (pts[[0, 5, 10, 15, 20], 1] == pts[[4, 9, 14, 19, 24], 1]).all()


def test_displace_grading_clusters_walls(tmp_path) -> None:
    prof = np.array([[0.0, 0.0], [9.0, 0.0]])
    _write_points(tmp_path, nx=2, ny=30, h=3.036)
    displace_hill_mesh(tmp_path, prof, height=3.036, grade=3.5, ny=30)
    ys = _read_pts(tmp_path)[:, 1]
    rows = ys.reshape(31, 3)[:, 0]
    dys = np.diff(rows)
    assert (dys > 0).all()
    assert dys[0] < 0.02  # wall-clustered
    assert dys[0] < dys[15]  # mid coarser than wall


def _write_field(path, kind, n, per_row):
    lines = ["FoamFile", "{", "}"]
    lines += [f"internalField nonuniform List<{kind}>", str(n), "("]
    if kind == "scalar":
        lines += [" ".join("0.5" for _ in range(n))]
    else:
        lines += ["(" + " ".join(["1.0"] * per_row) + ")" for _ in range(n)]
    lines += [")", "boundaryField", "{", "}"]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_read_latest_field_kinds(tmp_path) -> None:
    d = tmp_path / "case" / "100"
    d.mkdir(parents=True)
    _write_field(d / "nut", "scalar", 4, 1)
    _write_field(d / "U", "vector", 4, 3)
    _write_field(d / "gradU", "tensor", 4, 9)
    assert read_latest_field(tmp_path / "case", "nut").shape == (4,)
    assert read_latest_field(tmp_path / "case", "U").shape == (4, 3)
    assert read_latest_field(tmp_path / "case", "gradU").shape == (4, 3, 3)
    assert float(read_latest_field(tmp_path / "case", "nut")[0]) == 0.5

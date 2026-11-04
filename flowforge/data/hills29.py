"""Parameterized periodic hills (Xiao et al. 2020, 29 DNS at Re_H 5600) -> frozen-RANS stores.

The dataset has DNS only, so the baseline is computed here: for each geometry a terrain-following
mesh is built from the DNS wall (the DNS uses an immersed boundary on a Cartesian grid, so solid
points hold exact zeros), k-omega SST is solved with OpenFOAM (simpleFoam, Docker image
``flowforge-openfoam:local``), and the DNS statistics are interpolated onto the RANS cell centres.
Arrays follow ``ingest_csv.extract_case_arrays`` (same keys and definitions); the features of
``flowforge.data.features`` are computed from the same RANS fields.

Flow: Re = Ub H / nu = 5600 with Ub the bulk velocity above the crest (H = 1), so nu = 1/5600 and
the mean-velocity forcing targets a domain-averaged U of Ub (Ly - 1) Lx / A.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path

import numpy as np

NU = 1.0 / 5600.0
TEMPLATE = Path("openfoam/templates/periodicHill")
COLUMNS = ("x", "y", "u", "v", "w", "p", "eps", "vort", "uu", "vv", "ww", "uv", "uw", "vw", "pp")


def case_name(path: Path) -> str:
    return "hill29_" + Path(path).stem.replace("-", "_")


def parse_dns(path: Path) -> dict:
    """DNS fields as (J, I) arrays plus the Cartesian axes; solid points are NaN."""
    import pandas as pd

    text = Path(path).read_text(encoding="utf-8", errors="ignore")[:2000]
    m = re.search(r"I=(\d+),\s*J=(\d+)", text)
    ni, nj = int(m.group(1)), int(m.group(2))
    skip = next(i for i, line in enumerate(text.splitlines()) if line.strip().startswith("DT=")) + 1
    data = pd.read_csv(path, sep=r"\s+", skiprows=skip, header=None, names=COLUMNS,
                       dtype=float, engine="c").to_numpy()
    assert data.shape[0] == ni * nj, f"{path}: {data.shape[0]} rows, expected {ni}x{nj}"
    grid = {c: data[:, i].reshape(nj, ni) for i, c in enumerate(COLUMNS)}
    solid = (grid["u"] == 0) & (grid["uu"] == 0) & (grid["vv"] == 0)
    for c in COLUMNS[2:]:
        grid[c] = np.where(solid, np.nan, grid[c])
    x, y = grid["x"][0], grid["y"][:, 0]
    assert np.allclose(grid["x"], x[None, :]) and np.allclose(grid["y"], y[:, None]), "grid is not Cartesian"
    return {"x": x, "y": y, "solid": solid, **{c: grid[c] for c in COLUMNS[2:]}}


def wall_profile(dns: dict) -> np.ndarray:
    """Lower wall (x, y): midpoint between the last solid and first fluid point per column."""
    x, y, solid = dns["x"], dns["y"], dns["solid"]
    yw = np.empty(len(x))
    for i in range(len(x)):
        j = int(np.argmax(~solid[:, i]))  # first fluid row
        yw[i] = 0.0 if j == 0 else 0.5 * (y[j - 1] + y[j])
    dx = x[1] - x[0]
    xs = np.append(x, x[-1] + dx)  # close the period: x = Lx repeats x = 0
    ys = np.append(yw, yw[0])
    return np.stack([xs, ys], axis=1)


def _sub(text: str, pattern: str, repl: str) -> str:
    new, n = re.subn(pattern, repl, text)
    assert n == 1, f"pattern {pattern!r} matched {n} times"
    return new


def build_case(case_dir: Path, lx: float, ly: float, ubar: float, nx: int, ny: int, end_time: int = 8000):
    """Template copy with a flat block (lx x ly), nu, forcing and low-Re wall conditions."""
    shutil.copytree(TEMPLATE, case_dir)
    for junk in ("0/aDelta", "0/PkDelta", ".gitkeep"):
        (case_dir / junk).unlink(missing_ok=True)
    shutil.rmtree(case_dir / "constant" / "polyMesh", ignore_errors=True)
    bm = (case_dir / "system/blockMeshDict").read_text(encoding="utf-8")
    bm = _sub(bm, r"\(0 0 0\) \(9 0 0\) \(9 3\.036 0\) \(0 3\.036 0\)", f"(0 0 0) ({lx} 0 0) ({lx} {ly} 0) (0 {ly} 0)")
    bm = _sub(bm, r"\(0 0 0\.1\) \(9 0 0\.1\) \(9 3\.036 0\.1\) \(0 3\.036 0\.1\)",
              f"(0 0 0.1) ({lx} 0 0.1) ({lx} {ly} 0.1) (0 {ly} 0.1)")
    bm = _sub(bm, r"\(90 30 1\)", f"({nx} {ny} 1)")
    (case_dir / "system/blockMeshDict").write_text(bm, encoding="utf-8")
    tp = (case_dir / "constant/transportProperties").read_text(encoding="utf-8")
    (case_dir / "constant/transportProperties").write_text(_sub(tp, r"nu\s+[0-9.eE+-]+;", f"nu              {NU:.8e};"), encoding="utf-8")
    fo = (case_dir / "system/fvOptions").read_text(encoding="utf-8")
    (case_dir / "system/fvOptions").write_text(_sub(fo, r"Ubar\s+\(1 0 0\);", f"Ubar            ({ubar:.6f} 0 0);"), encoding="utf-8")
    cd = (case_dir / "system/controlDict").read_text(encoding="utf-8")
    cd = _sub(cd, r"endTime\s+2000;", f"endTime         {end_time};")
    cd = _sub(cd, r"writeInterval\s+500;", f"writeInterval   {end_time};")
    (case_dir / "system/controlDict").write_text(cd, encoding="utf-8")
    fs = (case_dir / "system/fvSolution").read_text(encoding="utf-8")
    (case_dir / "system/fvSolution").write_text(
        _sub(fs, r"residualControl \{[^}]*\}", "residualControl { p 1e-5; U 1e-6; k 1e-6; omega 1e-6; }"), encoding="utf-8")
    walls = {"0/k": "walls { type fixedValue; value uniform 1e-10; }",
             "0/nut": "walls { type nutLowReWallFunction; value uniform 0; }",
             "0/omega": "walls { type omegaWallFunction; value uniform 1e3; }"}
    for f, bc in walls.items():
        t = (case_dir / f).read_text(encoding="utf-8")
        (case_dir / f).write_text(_sub(t, r"walls\s*\{[^}]*\}", bc), encoding="utf-8")


def docker(case_dir: Path, cmd: str, timeout: float, image: str = "flowforge-openfoam:local") -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "run", "--rm", "-v", f"{case_dir.resolve()}:/case", image, "bash", "-lc",
                           f"cd /case && {cmd}"], capture_output=True, text=True, timeout=timeout)


def domain_area(profile: np.ndarray, ly: float) -> float:
    return float(np.trapz(ly - profile[:, 1], profile[:, 0]))


def solve(dns_path: Path, work: Path, nx_per_h: float = 20.0, ny: int = 80, grade: float = 4.0,
          timeout: float = 3600.0) -> Path:
    """Mesh + SST solve + gradient post-processing for one geometry; returns the case dir."""
    from flowforge.solver.hill_mesh import displace_hill_mesh

    dns = parse_dns(dns_path)
    prof = wall_profile(dns)
    lx, ly = float(prof[-1, 0]), float(dns["y"][-1])
    crest = float(prof[:, 1].max())
    ubar = (ly - crest) * lx / domain_area(prof, ly)
    case_dir = work / f"{case_name(dns_path)}-{uuid.uuid4().hex[:6]}"
    nx = int(round(nx_per_h * lx))
    build_case(case_dir, lx, ly, ubar, nx, ny)
    np.save(case_dir / "wall_profile.npy", prof)
    r = docker(case_dir, "blockMesh > log.blockMesh 2>&1", 600)
    assert r.returncode == 0, (case_dir / "log.blockMesh").read_text()[-2000:]
    displace_hill_mesh(case_dir, prof, height=ly, grade=grade, ny=ny)
    r = docker(case_dir, "checkMesh > log.checkMesh 2>&1; simpleFoam > log.simpleFoam 2>&1 && "
               "simpleFoam -postProcess -latestTime -funcs '(grad(U) grad(p) grad(k) writeCellCentres)' "
               "> log.post 2>&1", timeout)
    assert r.returncode == 0, f"{case_dir}: solver failed\n" + (case_dir / "log.simpleFoam").read_text()[-3000:]
    return case_dir


def _read_latest(case_dir: Path) -> dict[str, np.ndarray]:
    from foamlib import FoamCase

    latest = sorted(FoamCase(str(case_dir)), key=lambda t: float(t.time))[-1]
    names = {"U": "U", "p": "p", "k": "k", "omega": "omega", "nut": "nut", "gradU": "grad(U)",
             "gradp": "grad(p)", "gradk": "grad(k)", "C": "C"}
    return {k: np.asarray(latest[v].internal_field, dtype=float) for k, v in names.items()}


def wall_distance(C: np.ndarray, prof: np.ndarray, ly: float) -> np.ndarray:
    from scipy.spatial import cKDTree

    xs = np.linspace(prof[0, 0], prof[-1, 0], 40000)
    ys = np.interp(xs, prof[:, 0], prof[:, 1])
    period = prof[-1, 0] - prof[0, 0]
    pts = np.concatenate([np.stack([xs + s, ys], 1) for s in (-period, 0.0, period)])
    d_bottom, _ = cKDTree(pts).query(C[:, :2])
    return np.minimum(d_bottom, ly - C[:, 1])


def to_frame(case_dir: Path, dns_path: Path):
    """McConkey-style rows (komegasst_* / REF_* columns) from the solved case and the DNS."""
    import pandas as pd
    from scipy.interpolate import RegularGridInterpolator

    f = _read_latest(case_dir)
    prof = np.load(case_dir / "wall_profile.npy")
    dns = parse_dns(dns_path)
    C = f["C"]
    n = len(C)
    gradU = f["gradU"].reshape(n, 3, 3)  # OpenFOAM grad(U)_ij = d u_j / d x_i
    gradU = np.swapaxes(gradU, 1, 2)     # -> d u_i / d x_j, the dataset convention
    S = 0.5 * (gradU + np.swapaxes(gradU, 1, 2))
    k, omega, nut = f["k"], f["omega"], f["nut"]
    tau = (2.0 / 3.0) * k[:, None, None] * np.eye(3) - 2.0 * nut[:, None, None] * S  # Boussinesq (SST is linear)
    U = f["U"]
    dudt = np.einsum("nij,nj->ni", gradU, U)
    row = {"komegasst_U_%d" % (i + 1): U[:, i] for i in range(3)}
    row.update({"komegasst_k": k, "komegasst_omega": omega, "komegasst_nut": nut, "komegasst_p": f["p"],
                "komegasst_epsilon": 0.09 * k * omega, "komegasst_wallDistance": wall_distance(C, prof, dns["y"][-1])})
    row.update({f"komegasst_gradU_{i + 1}{j + 1}": gradU[:, i, j] for i in range(3) for j in range(3)})
    row.update({f"komegasst_turbR_{i + 1}{j + 1}": tau[:, i, j] for i in range(3) for j in range(3)})
    row.update({f"komegasst_gradp_{i + 1}": f["gradp"][:, i] for i in range(3)})
    row.update({f"komegasst_gradk_{i + 1}": f["gradk"][:, i] for i in range(3)})
    row.update({f"komegasst_DUDt_{i + 1}": dudt[:, i] for i in range(3)})
    row.update({f"komegasst_C_{i + 1}": C[:, i] for i in range(3)})
    # DNS onto RANS cell centres (period closed by repeating the first column at x = Lx)
    x = np.append(dns["x"], dns["x"][-1] + (dns["x"][1] - dns["x"][0]))
    ref = {}
    for c in ("u", "v", "w", "uu", "vv", "ww", "uv", "uw", "vw"):
        grid = np.concatenate([dns[c], dns[c][:, :1]], axis=1)
        interp = RegularGridInterpolator((dns["y"], x), grid, bounds_error=False, fill_value=np.nan)
        ref[c] = interp(np.stack([C[:, 1], C[:, 0]], 1))
    kd = 0.5 * (ref["uu"] + ref["vv"] + ref["ww"])
    b = {"11": ref["uu"], "12": ref["uv"], "13": ref["uw"], "22": ref["vv"], "23": ref["vw"], "33": ref["ww"]}
    refrow = {f"REF_b_{ij}": v / (2.0 * kd) - (1.0 / 3.0 if ij[0] == ij[1] else 0.0) for ij, v in b.items()}
    refrow.update({"REF_U_1": ref["u"], "REF_U_2": ref["v"], "REF_U_3": ref["w"]})
    df_k, df_r = pd.DataFrame(row), pd.DataFrame(refrow)
    keep = np.isfinite(df_r.to_numpy()).all(axis=1) & (kd > 1e-8)
    return df_k[keep].reset_index(drop=True), df_r[keep].reset_index(drop=True), int((~keep).sum())


def ingest(case_dir: Path, dns_path: Path, processed_dir: Path = Path("data/processed"),
           features_dir: Path = Path("data/features")) -> dict:
    """Write the processed store and the feature file for one solved geometry."""
    from flowforge.data.features import standard_features
    from flowforge.data.ingest_csv import extract_case_arrays
    from flowforge.data.split_guard import guard_swarm_path
    from flowforge.data.zarr_store import write_case

    name = case_name(dns_path)
    df_k, df_r, dropped = to_frame(case_dir, dns_path)
    target = processed_dir / name
    guard_swarm_path(target, role="swarm")
    write_case(target, extract_case_arrays(df_k, df_r))
    features_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(features_dir / f"{name}.npz", **standard_features(df_k))
    return {"case": name, "points": len(df_k), "dropped_near_wall": dropped}
